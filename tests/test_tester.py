import math
import unittest

from dualsense_painel.tester import BUTTONS, Tester


def frame(buttons=(), lx=128, ly=128, rx=128, ry=128, l2=0, r2=0, touch=0, gyro=(0, 0, 0), accel=(0, 1, 0)):
    return {
        "buttons": {k: k in buttons for k, _ in BUTTONS},
        "sticks": {"lx": lx, "ly": ly, "rx": rx, "ry": ry},
        "triggers": {"l2": l2, "r2": r2},
        "touch": [{"active": i < touch, "id": i, "x": 0, "y": 0} for i in range(2)],
        "gyro": list(gyro), "accel": list(accel),
    }


class TesterTest(unittest.TestCase):
    def test_buttons_are_remembered(self):
        t = Tester()
        self.assertEqual(t.record(frame(("cross", "ps"))), {"cross", "ps"})
        self.assertEqual(t.record(frame(("cross",))), set())
        self.assertEqual(t.tested, {"cross", "ps"})

    def test_triggers_max_and_touch(self):
        t = Tester()
        t.record(frame(l2=120, r2=255, touch=2, buttons=("touchpad",)))
        t.record(frame(l2=40))
        self.assertEqual(t.max, {"l2": 120, "r2": 255})
        self.assertEqual(t.touch_seen, 2)
        self.assertTrue(t.click_seen)

    def test_rest_drift_detection(self):
        t = Tester()
        for _ in range(200):
            t.record(frame(lx=128, ly=128, rx=145, ry=128))
        self.assertEqual(t.sticks["l"].drift(), "ok")
        self.assertEqual(t.sticks["r"].drift(), "bad")

    def test_circularity_full_circle(self):
        t = Tester()
        for i in range(720):
            a = 2 * math.pi * i / 720
            t.record(frame(lx=round(128 + 127 * math.cos(a)), ly=round(128 + 127 * math.sin(a))))
        coverage, error = t.sticks["l"].circularity()
        self.assertGreater(coverage, 0.95)
        self.assertLess(error, 0.02)

    def test_motion_seen(self):
        t = Tester()
        t.record(frame(gyro=(0, 45, 0), accel=(0.1, 0.98, 0.1)))
        self.assertTrue(t.gyro_seen and t.accel_seen)

    def test_report_mentions_missing_and_info(self):
        t = Tester()
        t.record(frame(("cross",)))
        text = t.report({"model": "DualSense", "colorPt": "Branco", "board": "BDM-030"}, "50%", 250)
        self.assertIn("Testados: 1 de 19", text)
        self.assertIn("Placa: BDM-030", text)
        self.assertIn("Cor de fábrica: Branco", text)
        self.assertIn("Triângulo", text)


if __name__ == "__main__":
    unittest.main()
