import json
import os
import time

from . import plataforma

SEND_ID = 0x80
RECV_ID = 0x81
SIZE = 64
DEVICE_SYSTEM = 0x01
ACTION_READ_SERIAL = 0x13
STATUS_COMPLETE = 0x02
MIN_HARDWARE = 777
MIN_FIRMWARE = 65655

CACHE = os.path.join(plataforma.data_dir(), "controles.json")

COLORS = {
    "00": ("White", "Branco", "#f1f2f4"),
    "01": ("Midnight Black", "Preto Meia-Noite", "#1c1d22"),
    "02": ("Cosmic Red", "Vermelho Cósmico", "#9b1b24"),
    "03": ("Nova Pink", "Rosa Nova", "#f4b9c9"),
    "04": ("Galactic Purple", "Roxo Galáctico", "#4a2a7d"),
    "05": ("Starlight Blue", "Azul Estelar", "#9fc4e8"),
    "06": ("Grey Camouflage", "Camuflado Cinza", "#8b8f94"),
    "07": ("Volcanic Red", "Vermelho Vulcânico", "#a8161c"),
    "08": ("Sterling Silver", "Prata Esterlina", "#c3c7cc"),
    "09": ("Cobalt Blue", "Azul Cobalto", "#1f50a6"),
    "10": ("Chroma Teal", "Chroma Turquesa", "#2aa8a4"),
    "11": ("Chroma Indigo", "Chroma Índigo", "#3d409f"),
    "12": ("Chroma Pearl", "Chroma Pérola", "#e9e4ef"),
    "30": ("30th Anniversary", "Edição 30 anos", "#b9bcc2"),
    "Z1": ("God of War Ragnarok", "Edição God of War Ragnarök", "#7fa6c9"),
    "Z2": ("Spider-Man 2", "Edição Spider-Man 2", "#b3141c"),
    "Z3": ("Astro Bot", "Edição Astro Bot", "#2a6fdb"),
    "Z4": ("Fortnite", "Edição Fortnite", "#3c7be0"),
    "Z6": ("The Last of Us", "Edição The Last of Us", "#4f5a4a"),
    "ZB": ("Icon Blue Limited Edition", "Edição Icon Blue", "#1b4fd6"),
    "ZE": ("Genshin Impact", "Edição Genshin Impact", "#e9e1d3"),
}
BOARDS = {"1": "BDM-010", "2": "BDM-020", "3": "BDM-030", "4": "BDM-040", "5": "BDM-050"}


def supported(hardware, firmware):
    try:
        return (int(hardware, 16) & 0xFFFF) >= MIN_HARDWARE and int(firmware, 16) >= MIN_FIRMWARE
    except (TypeError, ValueError):
        return False


def decode(serial):
    serial = (serial or "").strip()
    if len(serial) < 6:
        return None
    code = serial[4:6]
    english, portuguese, swatch = COLORS.get(code, (None, None, None))
    return {
        "serial": serial,
        "colorCode": code,
        "color": english,
        "colorPt": portuguese,
        "colorHex": swatch,
        "board": BOARDS.get(serial[1:2]),
    }


def read_serial(send_feature, get_feature, attempts=20, wait=0.05):
    send = bytearray(SIZE)
    send[0], send[1], send[2] = SEND_ID, DEVICE_SYSTEM, ACTION_READ_SERIAL
    send_feature(bytes(send))
    for _ in range(attempts):
        time.sleep(wait)
        try:
            buf = bytes(get_feature(RECV_ID, SIZE))
        except OSError:
            continue
        if len(buf) > 36 and buf[1] == DEVICE_SYSTEM and buf[2] == ACTION_READ_SERIAL and buf[3] == STATUS_COMPLETE:
            raw = buf[4:36].split(b"\x00", 1)[0]
            return raw.decode("ascii", "replace")
    return None


def load_cache(path=CACHE):
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def remember(mac, info, path=CACHE):
    if not mac or not info:
        return
    data = load_cache(path)
    data[mac] = info
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w") as f:
            json.dump(data, f, indent=2)
        os.replace(path + ".tmp", path)
    except OSError:
        pass
