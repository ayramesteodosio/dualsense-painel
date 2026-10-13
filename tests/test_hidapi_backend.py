import importlib
import struct
import sys
import types
import unittest
from unittest import mock


def fake_hid_module(entries, features):
    mod = types.ModuleType("hid")
    mod.__file__ = "/nonexistent/hid.so"
    written = []

    class Device:
        def open_path(self, path):
            self.path = path

        def get_feature_report(self, rid, size):
            return list(features.get(rid, bytes([rid]) + bytes(size - 1)))[:size]

        def send_feature_report(self, data):
            written.append(("feature", bytes(data)))
            return len(data)

        def write(self, data):
            written.append(("out", bytes(data)))
            return len(data)

        def read(self, size, timeout=0):
            return []

        def close(self):
            pass

    mod.device = Device
    mod.enumerate = lambda vid=0, pid=0: entries
    return mod, written


def firmware_report():
    buf = bytearray(64)
    buf[0] = 0x20
    buf[1:12] = b"Jul  4 2025"
    buf[12:20] = b"10:10:32"
    struct.pack_into("<I", buf, 24, 0x513)
    struct.pack_into("<I", buf, 28, 0x0110002A)
    struct.pack_into("<H", buf, 44, 0x0630)
    return bytes(buf)


class HidapiBackendTest(unittest.TestCase):
    def load(self, entries):
        mac = bytes([0x09, 0x56, 0x34, 0x12, 0xEF, 0xCD, 0xAB]) + bytes(13)
        mod, written = fake_hid_module(entries, {0x20: firmware_report(), 0x09: mac})
        with mock.patch.dict(sys.modules, {"hid": mod}):
            sys.modules.pop("dualsense_painel.backends.hidapi_backend", None)
            hidapi_backend = importlib.import_module("dualsense_painel.backends.hidapi_backend")
        return hidapi_backend, written

    def tearDown(self):
        sys.modules.pop("dualsense_painel.backends.hidapi_backend", None)

    def test_usb_device_info_and_output_size(self):
        entry = {"path": b"\\\\?\\HID#VID_054C&PID_0CE6&MI_03#7&abc&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}",
                 "product_id": 0x0CE6, "bus_type": 1, "interface_number": 3, "serial_number": ""}
        backend_mod, written = self.load([entry, {"product_id": 0x1234}])
        backend = backend_mod.HidapiBackend()
        ref = backend.find()
        self.assertFalse(ref.bluetooth)
        self.assertEqual(ref.model, "DualSense")
        dev = backend.open(ref)
        info = dev.read_info()
        self.assertEqual((info["firmware"], info["hardware"], info["mac"]),
                         ("0x0110002a", "0x00000513", "AB:CD:EF:12:34:56"))
        self.assertEqual(info["build"], "Jul  4 2025 10:10:32")
        from dualsense_painel.protocol import OutputState
        dev.send(OutputState())
        out = [d for kind, d in written if kind == "out"][-1]
        self.assertEqual((len(out), out[0]), (48, 0x02))

    def test_bluetooth_uses_full_report_and_mac_from_serial(self):
        entry = {"path": b"bt", "product_id": 0x0CE6, "bus_type": 2, "interface_number": -1,
                 "serial_number": "abcdef123456"}
        backend_mod, written = self.load([entry])
        dev = backend_mod.HidapiBackend().open(backend_mod.HidapiBackend().find())
        self.assertTrue(dev.ref.bluetooth)
        self.assertEqual(dev.read_info()["mac"], "AB:CD:EF:12:34:56")
        from dualsense_painel.protocol import OutputState
        dev.send(OutputState())
        out = [d for kind, d in written if kind == "out"][-1]
        self.assertEqual((len(out), out[0]), (78, 0x31))
        self.assertIsNone(dev.read_serial())


class HidHideTest(unittest.TestCase):
    def test_instance_id_from_windows_path(self):
        from dualsense_painel.backends import hidhide
        path = b"\\\\?\\hid#vid_054c&pid_0ce6&mi_03#7&2d5a8c3b&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}"
        self.assertEqual(hidhide.instance_id(path), "HID\\VID_054C&PID_0CE6&MI_03\\7&2D5A8C3B&0&0000")


if __name__ == "__main__":
    unittest.main()


class SessionDuplicadoTest(unittest.TestCase):
    def test_relatorio_repetido_nao_conta(self):
        from dualsense_painel.session import Session
        s = Session.__new__(Session)
        s._raw, s._raw_count = None, 0
        a, b = bytes([1, 2, 3]), bytes([1, 2, 4])
        for r in (a, a, b, b, a):
            s._on_report(r)
        self.assertEqual(s._raw_count, 3)
