import os
import struct
import tempfile
import unittest

from dualsense_painel import config, inputs, profiles
from dualsense_painel.history import BatteryHistory


def usb_report(**over):
    data = bytearray(64)
    data[0] = 0x01
    p = data[1:]
    p[0:4] = bytes([10, 20, 250, 128])
    p[4], p[5] = 99, 200
    p[7] = 0x08 | 0x20 | 0x80
    p[8] = 0x01 | 0x20
    p[9] = 0x01 | 0x04
    struct.pack_into("<hhh", p, 15, 1024, -2048, 0)
    struct.pack_into("<hhh", p, 21, 0, 8192, -4096)
    p[32] = 0x05
    p[33], p[34], p[35] = 0x34, 0x12 | 0x50, 0x2A
    p[36] = 0x80
    p[52] = 0x16
    for k, v in over.items():
        p[int(k[1:])] = v
    data[1:] = p
    return bytes(data)


class InputsTest(unittest.TestCase):
    def test_parse_usb(self):
        d = inputs.parse(usb_report())
        self.assertEqual(d["sticks"], {"lx": 10, "ly": 20, "rx": 250, "ry": 128})
        self.assertEqual(d["triggers"], {"l2": 99, "r2": 200})
        pressed = {k for k, v in d["buttons"].items() if v}
        self.assertEqual(pressed, {"cross", "triangle", "l1", "options", "ps", "mic"})
        self.assertEqual(d["gyro"], [1.0, -2.0, 0.0])
        self.assertEqual(d["accel"], [0.0, 1.0, -0.5])
        self.assertEqual(d["touch"][0], {"active": True, "id": 5, "x": 0x234, "y": 0x2A5})
        self.assertFalse(d["touch"][1]["active"])
        self.assertEqual(d["battery"], (65, "Charging"))

    def test_dpad_diagonal(self):
        d = inputs.parse(usb_report(p7=0x01))
        self.assertTrue(d["buttons"]["up"] and d["buttons"]["right"])
        self.assertFalse(d["buttons"]["down"] or d["buttons"]["left"])

    def test_bluetooth_offset(self):
        usb = usb_report()
        bt = bytes([0x31, 0x00]) + usb[1:] + bytes(78 - 65)
        self.assertEqual(inputs.parse(bt)["sticks"], inputs.parse(usb)["sticks"])

    def test_rejects_other_reports(self):
        self.assertIsNone(inputs.parse(b"\x05" + bytes(63)))
        self.assertIsNone(inputs.parse(b""))

    def test_full_battery(self):
        self.assertEqual(inputs.battery_from_status(0x2A), (100, "Full"))


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.now = 1_000_000.0
        self.path = os.path.join(self.dir.name, "b.csv")

    def tearDown(self):
        self.dir.cleanup()

    def hist(self):
        return BatteryHistory(self.path, clock=lambda: self.now)

    def test_records_changes_and_persists(self):
        h = self.hist()
        self.assertTrue(h.record(15, "Charging"))
        self.assertFalse(h.record(15, "Charging"))
        self.now += 600
        self.assertTrue(h.record(15, "Charging"))
        self.assertEqual(len(self.hist().points), 2)

    def test_estimate_charging(self):
        h = self.hist()
        h.record(20, "Charging")
        self.now += 30 * 60
        h.record(50, "Charging")
        self.assertEqual(h.estimate(), {"kind": "full", "minutes": 50})

    def test_estimate_discharging_uses_current_segment(self):
        h = self.hist()
        h.record(10, "Charging")
        self.now += 60
        h.record(90, "Discharging")
        self.now += 60 * 60
        h.record(80, "Discharging")
        self.assertEqual(h.estimate(), {"kind": "empty", "minutes": 480})

    def test_no_estimate_without_change(self):
        h = self.hist()
        h.record(15, "Charging")
        self.now += 3600
        h.record(15, "Charging")
        self.assertIsNone(h.estimate())


class ProfilesTest(unittest.TestCase):
    def test_save_apply_delete(self):
        cfg = config.load("/nonexistent")
        cfg["color"] = [1, 2, 3]
        self.assertEqual(profiles.save(cfg, "  Corrida   noturna "), "Corrida noturna")
        cfg["color"] = [9, 9, 9]
        self.assertTrue(profiles.apply(cfg, "Corrida noturna"))
        self.assertEqual(cfg["color"], [1, 2, 3])
        self.assertEqual(profiles.summary(cfg)[0]["name"], "Corrida noturna")
        self.assertTrue(profiles.delete(cfg, "Corrida noturna"))
        self.assertFalse(profiles.apply(cfg, "Corrida noturna"))

    def test_empty_name_rejected(self):
        self.assertIsNone(profiles.save(config.load("/nonexistent"), "   "))


if __name__ == "__main__":
    unittest.main()


class SimpleReportTest(unittest.TestCase):
    def test_bluetooth_simple_report(self):
        report = bytes([0x01, 10, 250, 128, 128, 0x24, 0x01, 0x01, 40, 200])
        data = inputs.parse(report)
        self.assertEqual(data["sticks"], {"lx": 10, "ly": 250, "rx": 128, "ry": 128})
        self.assertEqual(data["triggers"], {"l2": 40, "r2": 200})
        self.assertTrue(data["buttons"]["cross"])
        self.assertTrue(data["buttons"]["l1"])
        self.assertTrue(data["buttons"]["ps"])
        self.assertTrue(data["buttons"]["down"])
        self.assertFalse(any(t["active"] for t in data["touch"]))
        self.assertEqual(data["battery"], (None, None))
