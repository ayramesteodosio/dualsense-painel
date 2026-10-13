import select
import subprocess
import threading

from .. import factory
from ..device import (Controller, UsbLink, find_controller, hidraw_get_feature, hidraw_send_feature, read_battery,
                      reconnect_orphans, usb_target)


class LinuxRef:
    def __init__(self, info):
        self.info = info
        self.key = info.hidraw
        self.bluetooth = info.bluetooth
        self.model = info.model
        target = usb_target(info)
        self.usb_id = target.node if target else None


class LinuxDevice:
    can_hide_bluetooth = False

    def __init__(self, ref):
        self.ref = ref
        self.info = ref.info
        self.controller = Controller(ref.info)
        self.link = None
        self._on_report = None
        self._stop = threading.Event()
        self._thread = None
        self._failed = False

    @property
    def hidden(self):
        return self.link is not None

    @property
    def failed(self):
        return self._failed or (self.link is not None and self.link.failed)

    def open(self):
        self.controller.open()

    def start(self, on_report):
        self._on_report = on_report
        self._start_reader()

    def _start_reader(self):
        self._stop.clear()
        fd = self.controller.hid_fd

        def loop():
            while not self._stop.is_set():
                try:
                    ready, _, _ = select.select([fd], [], [], 0.1)
                    if not ready:
                        continue
                    reports = self.controller.read_reports()
                except (OSError, ValueError):
                    if not self._stop.is_set():
                        self._failed = True
                    return
                for report in reports:
                    self._on_report(report)
        self._thread = threading.Thread(target=loop, name="dualsense-hidraw", daemon=True)
        self._thread.start()

    def _stop_reader(self):
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)
        self._thread = None

    def send(self, state):
        (self.link or self.controller).send(state)

    def read_info(self):
        return self.controller.read_info()

    def read_serial(self):
        fd = self.controller.hid_fd
        if fd is None or self.ref.bluetooth:
            return None
        return factory.read_serial(lambda data: hidraw_send_feature(fd, data),
                                   lambda rid, size: hidraw_get_feature(fd, rid, size))

    def battery(self):
        if self.link:
            return None, None
        return read_battery(self.info)

    def hide(self):
        target = usb_target(self.info)
        if not target:
            return False
        self._stop_reader()
        self.controller.close()
        link = UsbLink(target)
        try:
            link.detach()
        except OSError:
            self.controller = Controller(self.info)
            self.controller.open()
            self._start_reader()
            return False
        self.link = link
        link.start_reader(lambda report: report is not None and self._on_report(report))
        return True

    def unhide(self):
        if not self.link:
            return None
        self.link.reattach()
        self.link = None
        return "rediscover"

    def grab(self):
        return self.controller.grab()

    def release(self):
        self.controller.release()

    def disconnect_bluetooth(self, mac):
        if not self.ref.bluetooth or not mac:
            return False
        try:
            subprocess.Popen(["bluetoothctl", "disconnect", mac], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            return False
        return True

    def close(self):
        self._stop_reader()
        if self.link:
            self.link.reattach()
            self.link = None
        self.controller.close()


class LinuxBackend:
    name = "linux"

    def startup(self):
        return reconnect_orphans()

    def find(self):
        info = find_controller()
        return LinuxRef(info) if info else None

    def open(self, ref):
        device = LinuxDevice(ref)
        device.open()
        return device
