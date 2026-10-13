import struct

USB_INPUT_ID = 0x01
BT_INPUT_ID = 0x31
ACCEL_PER_G = 8192
GYRO_PER_DEG_S = 1024
TOUCH_W = 1920
TOUCH_H = 1080

HAT = {0: (True, False, False, False), 1: (True, False, False, True), 2: (False, False, False, True),
       3: (False, True, False, True), 4: (False, True, False, False), 5: (False, True, True, False),
       6: (False, False, True, False), 7: (True, False, True, False)}

BUTTON_NAMES = ("up", "down", "left", "right", "square", "cross", "circle", "triangle",
                "l1", "r1", "l2", "r2", "create", "options", "l3", "r3", "ps", "touchpad", "mic")


def payload_of(report):
    if not report:
        return None
    if report[0] == USB_INPUT_ID and len(report) >= 64:
        return report[1:]
    if report[0] == BT_INPUT_ID and len(report) >= 78:
        return report[2:]
    return None


def _touch(data, off):
    contact = data[off]
    x = data[off + 1] | ((data[off + 2] & 0x0F) << 8)
    y = (data[off + 2] >> 4) | (data[off + 3] << 4)
    return {"active": not contact & 0x80, "id": contact & 0x7F, "x": x, "y": y}


def parse(report):
    data = payload_of(report)
    if data is None:
        return None
    b0, b1, b2 = data[7], data[8], data[9]
    up, down, left, right = HAT.get(b0 & 0x0F, (False, False, False, False))
    gyro = struct.unpack_from("<hhh", data, 15)
    accel = struct.unpack_from("<hhh", data, 21)
    status = data[52]
    return {
        "sticks": {"lx": data[0], "ly": data[1], "rx": data[2], "ry": data[3]},
        "triggers": {"l2": data[4], "r2": data[5]},
        "buttons": {
            "up": up, "down": down, "left": left, "right": right,
            "square": bool(b0 & 0x10), "cross": bool(b0 & 0x20),
            "circle": bool(b0 & 0x40), "triangle": bool(b0 & 0x80),
            "l1": bool(b1 & 0x01), "r1": bool(b1 & 0x02), "l2": bool(b1 & 0x04), "r2": bool(b1 & 0x08),
            "create": bool(b1 & 0x10), "options": bool(b1 & 0x20),
            "l3": bool(b1 & 0x40), "r3": bool(b1 & 0x80),
            "ps": bool(b2 & 0x01), "touchpad": bool(b2 & 0x02), "mic": bool(b2 & 0x04),
        },
        "touch": [_touch(data, 32), _touch(data, 36)],
        "gyro": [round(v / GYRO_PER_DEG_S, 2) for v in gyro],
        "accel": [round(v / ACCEL_PER_G, 3) for v in accel],
        "timestamp": struct.unpack_from("<I", data, 27)[0],
        "battery": battery_from_status(status),
        "headphones": bool(data[53] & 0x01),
        "mic_plugged": bool(data[53] & 0x02),
    }


def battery_from_status(status):
    level = status & 0x0F
    charge = status >> 4
    kind = {0x0: "Discharging", 0x1: "Charging", 0x2: "Full"}.get(charge)
    pct = 100 if kind == "Full" else min(level * 10 + 5, 100)
    return pct, kind
