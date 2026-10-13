import os
import subprocess
import sys

CANDIDATES = (
    r"Nefarius Software Solutions\HidHide\x64\HidHideCLI.exe",
    r"Nefarius Software Solutions e.U\HidHide\x64\HidHideCLI.exe",
    r"Nefarius Software Solutions\HidHide\x86\HidHideCLI.exe",
)
CREATE_NO_WINDOW = 0x08000000


def cli_path():
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432"), os.environ.get("ProgramFiles(x86)")):
        if not base:
            continue
        for rel in CANDIDATES:
            path = os.path.join(base, rel)
            if os.path.isfile(path):
                return path
    return None


def available():
    return cli_path() is not None


def instance_id(hid_path):
    path = hid_path.decode("utf-8", "replace") if isinstance(hid_path, bytes) else str(hid_path)
    if path.startswith("\\\\?\\"):
        path = path[4:]
    path = path.split("#{", 1)[0]
    return path.replace("#", "\\").upper()


def _run(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15, creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _run_elevated(cli, commands):
    script = "; ".join(
        "& '{}' {}".format(cli, " ".join("'{}'".format(a.replace("'", "''")) for a in cmd)) for cmd in commands)
    ps = ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command",
          "Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList "
          "'-NoProfile','-Command',\"{}\"".format(script.replace('"', '`"'))]
    return _run(ps)


def _apply(commands):
    cli = cli_path()
    if not cli:
        return False
    if all(_run([cli] + cmd) for cmd in commands):
        return True
    return _run_elevated(cli, commands)


def hide(hid_path):
    exe = sys.executable
    return _apply([["--app-reg", exe], ["--dev-hide", instance_id(hid_path)], ["--cloak-on"]])


def unhide(hid_path):
    return _apply([["--dev-unhide", instance_id(hid_path)]])
