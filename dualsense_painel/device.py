import ctypes
import errno
import fcntl
import glob
import os
import struct
import threading
from dataclasses import dataclass, field

from . import firmware
from .protocol import build_report

SONY = 0x054C
PRODUCTS = {0x0CE6: "DualSense", 0x0DF2: "DualSense Edge"}
BUS_USB = 0x03
BUS_BLUETOOTH = 0x05

EVIOCGRAB = 0x40044590
FIRMWARE_REPORT = 0x20
FIRMWARE_REPORT_SIZE = 64


def hidiocgfeature(length):
    return (3 << 30) | (length << 16) | (ord("H") << 8) | 0x07


def hidiocsfeature(length):
    return (3 << 30) | (length << 16) | (ord("H") << 8) | 0x06


def hidraw_get_feature(fd, report_id, size):
    buf = bytearray(size)
    buf[0] = report_id
    fcntl.ioctl(fd, hidiocgfeature(size), buf, True)
    return bytes(buf)


def hidraw_send_feature(fd, data):
    buf = bytearray(data)
    fcntl.ioctl(fd, hidiocsfeature(len(buf)), buf)


@dataclass
class ControllerInfo:
    hidraw: str
    sys_hid: str
    bluetooth: bool
    model: str
    event_nodes: dict = field(default_factory=dict)
    battery_dir: str = None


def _read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def _parse_hid_id(uevent):
    for line in uevent.splitlines():
        if line.startswith("HID_ID="):
            bus, vendor, product = line[7:].split(":")
            return int(bus, 16), int(vendor, 16), int(product, 16)
    return None


def find_controller(sys_root="/sys", dev_root="/dev"):
    for hidraw in sorted(glob.glob(os.path.join(sys_root, "class/hidraw/hidraw*"))):
        hid_dir = os.path.realpath(os.path.join(hidraw, "device"))
        ids = _parse_hid_id(_read(os.path.join(hid_dir, "uevent")))
        if not ids or ids[1] != SONY or ids[2] not in PRODUCTS:
            continue
        info = ControllerInfo(
            hidraw=os.path.join(dev_root, os.path.basename(hidraw)),
            sys_hid=hid_dir,
            bluetooth=ids[0] == BUS_BLUETOOTH,
            model=PRODUCTS[ids[2]],
        )
        for event in glob.glob(os.path.join(hid_dir, "input/input*/event*")):
            name = _read(os.path.join(os.path.dirname(event), "name"))
            kind = "touchpad" if name.endswith("Touchpad") else (
                "motion" if name.endswith("Motion Sensors") else "gamepad")
            info.event_nodes[kind] = os.path.join(dev_root, "input", os.path.basename(event))
        batteries = glob.glob(os.path.join(hid_dir, "power_supply/*"))
        info.battery_dir = batteries[0] if batteries else None
        return info
    return None


def _uniq(info):
    for line in _read(os.path.join(info.sys_hid, "uevent")).splitlines():
        if line.startswith("HID_UNIQ="):
            return line[9:].upper() or None
    return None


def read_info(info, hid_fd=None):
    result = {
        "model": info.model,
        "connection": "bluetooth" if info.bluetooth else "usb",
        "mac": _uniq(info),
        "firmware": None,
        "hardware": None,
        "update": None,
        "build": None,
    }
    fw = _read(os.path.join(info.sys_hid, "firmware_version"))
    hw = _read(os.path.join(info.sys_hid, "hardware_version"))
    result["firmware"] = fw or None
    result["hardware"] = hw or None
    if hid_fd is None:
        return result
    try:
        parsed = firmware.parse(hidraw_get_feature(hid_fd, FIRMWARE_REPORT, FIRMWARE_REPORT_SIZE + (4 if info.bluetooth else 0)))
    except OSError:
        return result
    result["build"] = parsed.get("build")
    result["hardware"] = result["hardware"] or parsed.get("hardware")
    result["firmware"] = result["firmware"] or parsed.get("firmware")
    result["update"] = parsed.get("update")
    return result
    date = bytes(buf[1:12]).decode("ascii", "replace").strip("\x00 ")
    clock = bytes(buf[12:20]).decode("ascii", "replace").strip("\x00 ")
    result["build"] = f"{date} {clock}".strip() or None
    result["hardware"] = result["hardware"] or f"0x{struct.unpack_from('<I', buf, 24)[0]:08x}"
    result["firmware"] = result["firmware"] or f"0x{struct.unpack_from('<I', buf, 28)[0]:08x}"
    result["update"] = f"0x{struct.unpack_from('<H', buf, 44)[0]:04x}"
    return result


def read_battery(info):
    if not info or not info.battery_dir:
        return None, None
    capacity = _read(os.path.join(info.battery_dir, "capacity"))
    status = _read(os.path.join(info.battery_dir, "status"))
    return (int(capacity) if capacity.isdigit() else None), (status or None)


class Controller:
    def __init__(self, info):
        self.info = info
        self._hid_fd = None
        self._seq = 0
        self._grabbed = {}
        self.gamepad_fd = None

    def open(self):
        self._hid_fd = os.open(self.info.hidraw, os.O_RDWR | os.O_NONBLOCK)
        node = self.info.event_nodes.get("gamepad")
        if node:
            try:
                self.gamepad_fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                self.gamepad_fd = None

    def send(self, state):
        report = build_report(state, self.info.bluetooth, self._seq)
        self._seq = (self._seq + 1) & 0x0F
        os.write(self._hid_fd, report)

    def grab(self):
        failed = []
        for kind, node in self.info.event_nodes.items():
            if kind in self._grabbed:
                continue
            try:
                fd = self.gamepad_fd if kind == "gamepad" and self.gamepad_fd is not None else os.open(
                    node, os.O_RDONLY | os.O_NONBLOCK)
                fcntl.ioctl(fd, EVIOCGRAB, 1)
                self._grabbed[kind] = fd
            except OSError:
                failed.append(kind)
        return failed

    def release(self):
        for kind, fd in list(self._grabbed.items()):
            try:
                fcntl.ioctl(fd, EVIOCGRAB, 0)
            except OSError:
                pass
            if fd != self.gamepad_fd:
                os.close(fd)
        self._grabbed.clear()

    @property
    def grabbed(self):
        return set(self._grabbed)

    @property
    def hid_fd(self):
        return self._hid_fd

    def read_reports(self):
        reports = []
        while True:
            try:
                data = os.read(self._hid_fd, 128)
            except BlockingIOError:
                break
            if not data:
                break
            reports.append(data)
        return reports

    def read_info(self):
        return read_info(self.info, self._hid_fd)

    def close(self):
        self.release()
        for fd in (self.gamepad_fd, self._hid_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        self.gamepad_fd = self._hid_fd = None


USBDEVFS_BULK = 0xC0185502
USBDEVFS_RELEASEINTERFACE = 0x80045510
USBDEVFS_IOCTL = 0xC0105512
USBDEVFS_CONNECT = 0x5517
USBDEVFS_DISCONNECT_CLAIM = 0x8108551B
BULK = struct.Struct("IIIxxxxP")
DISCONNECT_CLAIM = struct.Struct("II256s")
USB_IOCTL = struct.Struct("iiP")



@dataclass
class UsbTarget:
    node: str
    interface: int
    ep_in: int
    ep_out: int


def usb_target(info):
    if info.bluetooth:
        return None
    iface_dir = os.path.dirname(info.sys_hid)
    dev_dir = os.path.dirname(iface_dir)
    try:
        bus, dev = int(_read(os.path.join(dev_dir, "busnum"))), int(_read(os.path.join(dev_dir, "devnum")))
        iface = int(_read(os.path.join(iface_dir, "bInterfaceNumber")), 16)
    except ValueError:
        return None
    eps = [int(os.path.basename(e)[3:], 16) for e in glob.glob(os.path.join(iface_dir, "ep_*"))]
    ep_in = next((e for e in eps if e & 0x80), None)
    ep_out = next((e for e in eps if not e & 0x80), None)
    if ep_in is None or ep_out is None:
        return None
    return UsbTarget(f"/dev/bus/usb/{bus:03d}/{dev:03d}", iface, ep_in, ep_out)


class UsbLink:

    def __init__(self, target):
        self.target = target
        self._fd = None
        self._reader = None
        self._stop = threading.Event()
        self.last_report = None
        self.reports = 0
        self.failed = False

    def detach(self):
        self._fd = os.open(self.target.node, os.O_RDWR)
        try:
            arg = DISCONNECT_CLAIM.pack(self.target.interface, 0, b"")
            fcntl.ioctl(self._fd, USBDEVFS_DISCONNECT_CLAIM, arg)
        except OSError:
            os.close(self._fd)
            self._fd = None
            raise

    def write(self, report):
        buf = ctypes.create_string_buffer(bytes(report), len(report))
        fcntl.ioctl(self._fd, USBDEVFS_BULK,
                    BULK.pack(self.target.ep_out, len(report), 500, ctypes.addressof(buf)))

    def send(self, state):
        self.write(build_report(state, bluetooth=False))

    def read_report(self, timeout_ms=200):
        buf = ctypes.create_string_buffer(64)
        fcntl.ioctl(self._fd, USBDEVFS_BULK,
                    BULK.pack(self.target.ep_in, 64, timeout_ms, ctypes.addressof(buf)))
        return buf.raw

    def start_reader(self, on_report):
        self._stop.clear()

        def loop():
            while not self._stop.is_set():
                try:
                    report = self.read_report(100)
                except OSError as e:
                    if e.errno == errno.ETIMEDOUT:
                        continue
                    self.failed = True
                    on_report(None)
                    return
                if report and report[0] == 0x01:
                    self.last_report = report
                    self.reports += 1
                    if on_report:
                        on_report(report)
        self._reader = threading.Thread(target=loop, daemon=True)
        self._reader.start()

    def stop_reader(self):
        self._stop.set()
        if self._reader and self._reader is not threading.current_thread():
            self._reader.join(timeout=1)
        self._reader = None

    def reattach(self):
        self.stop_reader()
        if self._fd is None:
            return
        try:
            fcntl.ioctl(self._fd, USBDEVFS_RELEASEINTERFACE, struct.pack("I", self.target.interface))
        except OSError:
            pass
        try:
            fcntl.ioctl(self._fd, USBDEVFS_IOCTL, USB_IOCTL.pack(self.target.interface, USBDEVFS_CONNECT, 0))
        except OSError:
            pass
        os.close(self._fd)
        self._fd = None

    @property
    def active(self):
        return self._fd is not None


def orphaned_targets(sys_root="/sys"):
    found = []
    for dev_dir in glob.glob(os.path.join(sys_root, "bus/usb/devices/*")):
        if _read(os.path.join(dev_dir, "idVendor")) != f"{SONY:04x}":
            continue
        if int(_read(os.path.join(dev_dir, "idProduct"), "0"), 16) not in PRODUCTS:
            continue
        for iface_dir in glob.glob(os.path.join(dev_dir, os.path.basename(dev_dir) + ":*")):
            if _read(os.path.join(iface_dir, "bInterfaceClass")) != "03":
                continue
            if os.path.exists(os.path.join(iface_dir, "driver")):
                continue
            bus, dev = int(_read(os.path.join(dev_dir, "busnum"))), int(_read(os.path.join(dev_dir, "devnum")))
            found.append(UsbTarget(f"/dev/bus/usb/{bus:03d}/{dev:03d}",
                                   int(_read(os.path.join(iface_dir, "bInterfaceNumber")), 16), 0, 0))
    return found


def reconnect_orphans(sys_root="/sys"):
    count = 0
    for target in orphaned_targets(sys_root):
        try:
            fd = os.open(target.node, os.O_RDWR)
        except OSError:
            continue
        try:
            fcntl.ioctl(fd, USBDEVFS_IOCTL, USB_IOCTL.pack(target.interface, USBDEVFS_CONNECT, 0))
            count += 1
        except OSError:
            pass
        finally:
            os.close(fd)
    return count
