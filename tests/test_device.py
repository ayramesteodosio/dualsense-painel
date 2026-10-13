import os
import sys
import tempfile
import unittest

if sys.platform.startswith("linux"):
    from dualsense_painel.device import find_controller, read_battery


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


@unittest.skipUnless(sys.platform.startswith("linux"), "só no Linux")
class FindControllerTest(unittest.TestCase):
    def make_sys(self, root, hid_id, name="0005:054C:0CE6.0007"):
        hid = os.path.join(root, "devices", name)
        write(os.path.join(hid, "uevent"), f"DRIVER=playstation\nHID_ID={hid_id}\n")
        for n, suffix in ((15, ""), (16, " Motion Sensors"), (17, " Touchpad")):
            write(os.path.join(hid, f"input/input{n}/name"),
                  "Sony Interactive Entertainment DualSense Wireless Controller" + suffix)
            os.makedirs(os.path.join(hid, f"input/input{n}/event{n}"))
        write(os.path.join(hid, "power_supply/ps-controller-battery-aa/capacity"), "80\n")
        write(os.path.join(hid, "power_supply/ps-controller-battery-aa/status"), "Discharging\n")
        os.makedirs(os.path.join(root, "class/hidraw/hidraw3"))
        os.symlink(hid, os.path.join(root, "class/hidraw/hidraw3/device"))

    def test_bluetooth_dualsense(self):
        with tempfile.TemporaryDirectory() as root:
            self.make_sys(root, "0005:0000054C:00000CE6")
            info = find_controller(root, "/dev")
            self.assertEqual(info.hidraw, "/dev/hidraw3")
            self.assertTrue(info.bluetooth)
            self.assertEqual(info.event_nodes, {"gamepad": "/dev/input/event15",
                                                "motion": "/dev/input/event16",
                                                "touchpad": "/dev/input/event17"})
            self.assertEqual(read_battery(info), (80, "Discharging"))

    def test_ignores_other_devices(self):
        with tempfile.TemporaryDirectory() as root:
            self.make_sys(root, "0018:000006CB:0000CD41")
            self.assertIsNone(find_controller(root, "/dev"))


if __name__ == "__main__":
    unittest.main()
