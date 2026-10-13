import array
import math
import os
import subprocess
import tempfile
import wave

from gi.repository import Gio, GLib

RATE = 48000
MATCH = ("dualsense", "sony_interactive")
SPEAKER = "speaker"
HEADPHONES = "headphones"


def _short_list(kind):
    try:
        out = subprocess.run(["pactl", "list", "short", kind], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.split("\t")[1] for line in out.splitlines() if "\t" in line]


def find_devices():
    sink = next((n for n in _short_list("sinks")
                 if any(m in n.lower() for m in MATCH) and not n.endswith(".monitor")), None)
    source = next((n for n in _short_list("sources")
                   if any(m in n.lower() for m in MATCH) and ".monitor" not in n), None)
    return {"sink": sink, "source": source}


def tone_file(target, seconds=1.2, freq=660):
    frames = int(RATE * seconds)
    fade = int(RATE * 0.05)
    data = array.array("h")
    rear = target == SPEAKER
    for i in range(frames):
        env = min(1.0, i / fade, (frames - i) / fade)
        beep = 0.0 if (i // int(RATE * 0.3)) % 2 else 1.0
        v = int(12000 * env * beep * math.sin(2 * math.pi * freq * i / RATE))
        data.extend((0, 0, v, v) if rear else (v, v, 0, 0))
    fd, path = tempfile.mkstemp(prefix="dualsense-tom-", suffix=".wav")
    os.close(fd)
    with wave.open(path, "wb") as w:
        w.setnchannels(4)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data.tobytes())
    return path


def play_tone(target, on_done=None):
    sink = find_devices()["sink"]
    if not sink:
        return False
    path = tone_file(target)
    try:
        proc = Gio.Subprocess.new(["paplay", f"--device={sink}", path],
                                  Gio.SubprocessFlags.STDERR_SILENCE)
    except GLib.Error:
        os.unlink(path)
        return False

    def finished(p, res):
        try:
            p.wait_finish(res)
        except GLib.Error:
            pass
        try:
            os.unlink(path)
        except OSError:
            pass
        if on_done:
            on_done()
    proc.wait_async(None, finished)
    return True


class MicMeter:
    def __init__(self, on_level):
        self.on_level = on_level
        self._proc = None
        self._stream = None
        self._cancel = None

    @property
    def running(self):
        return self._proc is not None

    def start(self):
        source = find_devices()["source"]
        if not source or self._proc:
            return bool(self._proc)
        try:
            self._proc = Gio.Subprocess.new(
                ["parec", f"--device={source}", "--format=s16le", "--rate=16000", "--channels=1",
                 "--latency-msec=50", "--raw"],
                Gio.SubprocessFlags.STDOUT_PIPE)
        except GLib.Error:
            self._proc = None
            return False
        self._stream = self._proc.get_stdout_pipe()
        self._cancel = Gio.Cancellable()
        self._read()
        return True

    def _read(self):
        self._stream.read_bytes_async(1600, GLib.PRIORITY_DEFAULT, self._cancel, self._got)

    def _got(self, stream, res):
        try:
            chunk = stream.read_bytes_finish(res).get_data()
        except GLib.Error:
            return
        if not chunk:
            self.stop()
            return
        samples = array.array("h")
        samples.frombytes(chunk[: len(chunk) - len(chunk) % 2])
        if samples:
            rms = math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768
            self.on_level(min(1.0, rms * 4))
        if self._proc:
            self._read()

    def stop(self):
        if self._cancel:
            self._cancel.cancel()
        if self._proc:
            self._proc.force_exit()
        self._proc = self._stream = self._cancel = None
