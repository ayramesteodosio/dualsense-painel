import struct

REPORT_ID = 0x20
SIZE = 64
MAC_REPORT_ID = 0x09
MAC_SIZE = 20


def parse(buf):
    buf = bytes(buf)
    if len(buf) < 48 or buf[0] != REPORT_ID:
        return {}
    date = buf[1:12].decode("ascii", "replace").strip("\x00 ")
    clock = buf[12:20].decode("ascii", "replace").strip("\x00 ")
    return {
        "build": f"{date} {clock}".strip() or None,
        "hardware": f"0x{struct.unpack_from('<I', buf, 24)[0]:08x}",
        "firmware": f"0x{struct.unpack_from('<I', buf, 28)[0]:08x}",
        "update": f"0x{struct.unpack_from('<H', buf, 44)[0]:04x}",
    }


def parse_mac(buf):
    buf = bytes(buf)
    if len(buf) < 7 or buf[0] != MAC_REPORT_ID:
        return None
    return ":".join(f"{b:02X}" for b in reversed(buf[1:7]))
