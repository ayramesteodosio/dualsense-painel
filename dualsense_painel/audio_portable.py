import math
import threading

RATE = 48000
SPEAKER = "speaker"
HEADPHONES = "headphones"
MATCH = ("dualsense", "wireless controller")


def _sd():
    import sounddevice
    return sounddevice


def _find(kind):
    try:
        sd = _sd()
        devices = sd.query_devices()
    except Exception:
        return None
    key = "max_output_channels" if kind == "output" else "max_input_channels"
    for index, d in enumerate(devices):
        if d[key] > 0 and any(m in d["name"].lower() for m in MATCH):
            return index
    return None


def find_devices():
    return {"sink": _find("output"), "source": _find("input")}


def _tone(channels, target, seconds=1.2, freq=660):
    import array
    frames = int(RATE * seconds)
    fade = int(RATE * 0.05)
    data = array.array("f")
    if channels >= 4:
        lanes = (2, 3) if target == SPEAKER else (0, 1)
    else:
        lanes = (0, 1) if channels > 1 else (0,)
    for i in range(frames):
        env = min(1.0, i / fade, (frames - i) / fade)
        beep = 0.0 if (i // int(RATE * 0.3)) % 2 else 1.0
        v = 0.35 * env * beep * math.sin(2 * math.pi * freq * i / RATE)
        data.extend(v if c in lanes else 0.0 for c in range(channels))
    return data


def play_tone(target, on_done=None):
    device = _find("output")
    if device is None:
        return False
    sd = _sd()
    channels = min(4, int(sd.query_devices(device)["max_output_channels"]))
    samples = _tone(channels, target)

    def run():
        import numpy
        try:
            sd.play(numpy.frombuffer(samples, dtype="float32").reshape(-1, channels), RATE, device=device, blocking=True)
        except Exception:
            pass
        if on_done:
            on_done()
    threading.Thread(target=run, daemon=True).start()
    return True


class MicMeter:
    def __init__(self, on_level):
        self.on_level = on_level
        self._stream = None

    @property
    def running(self):
        return self._stream is not None

    def start(self):
        device = _find("input")
        if device is None or self._stream:
            return bool(self._stream)
        sd = _sd()

        def callback(indata, _frames, _time, _status):
            total = 0.0
            count = 0
            for row in indata:
                total += float(row[0]) ** 2
                count += 1
            if count:
                self.on_level(min(1.0, math.sqrt(total / count) * 4))
        try:
            self._stream = sd.InputStream(device=device, channels=1, samplerate=16000, blocksize=800,
                                          dtype="float32", callback=callback)
            self._stream.start()
        except Exception:
            self._stream = None
            return False
        return True

    def stop(self):
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
        self._stream = None
