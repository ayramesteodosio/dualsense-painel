import os
import socket
import sys
import tempfile

APP = "dualsense-painel"
LOCK_PORT = 47833
WINDOWS = sys.platform.startswith("win")
MACOS = sys.platform == "darwin"
LINUX = sys.platform.startswith("linux")


def config_dir():
    if WINDOWS:
        base = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
    elif MACOS:
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, APP)


def data_dir():
    if WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
    elif MACOS:
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, APP)


def acquire_lock():
    if LINUX:
        import fcntl
        path = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir(), APP + ".lock")
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return None
        return fd
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if WINDOWS:
        sock.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_EXCLUSIVEADDRUSE", socket.SO_REUSEADDR), 1)
    try:
        sock.bind(("127.0.0.1", LOCK_PORT))
    except OSError:
        sock.close()
        return None
    return sock
