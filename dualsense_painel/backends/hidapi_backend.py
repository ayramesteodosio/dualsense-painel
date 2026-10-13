import ctypes
import threading

import hid

from .. import factory, firmware, plataforma
from ..protocol import build_report
from . import hidhide

SONY = 0x054C
PRODUCTS = {0x0CE6: "DualSense", 0x0DF2: "DualSense Edge"}
BUS_BLUETOOTH = 2
USB_OUTPUT_SIZE = 48
CALIBRATION_REPORT = 0x05
CALIBRATION_SIZE = 41
BT_INPUT_ID = 0x31


def _set_darwin_exclusive(on):
    try:
        lib = ctypes.CDLL(hid.__file__)
        fn = lib.hid_darwin_set_open_exclusive
    except (OSError, AttributeError):
        return False
    fn.argtypes = [ctypes.c_int]
    fn(1 if on else 0)
    return True


IOCTL_BTH_DISCONNECT_DEVICE = 0x41000C


def _desligar_windows(mac):
    from ctypes import wintypes

    class Parametros(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD)]

    bth = ctypes.WinDLL("bthprops.cpl")
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    bth.BluetoothFindFirstRadio.restype = ctypes.c_void_p
    bth.BluetoothFindFirstRadio.argtypes = [ctypes.POINTER(Parametros), ctypes.POINTER(wintypes.HANDLE)]
    bth.BluetoothFindNextRadio.restype = wintypes.BOOL
    bth.BluetoothFindNextRadio.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.HANDLE)]
    bth.BluetoothFindRadioClose.argtypes = [ctypes.c_void_p]
    k32.DeviceIoControl.restype = wintypes.BOOL
    k32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
                                    wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    endereco = ctypes.c_ulonglong(int(mac.replace(":", "").replace("-", ""), 16))
    parametros = Parametros(ctypes.sizeof(Parametros))
    radio = wintypes.HANDLE()
    busca = bth.BluetoothFindFirstRadio(ctypes.byref(parametros), ctypes.byref(radio))
    if not busca:
        return False
    desligou = False
    try:
        while True:
            lidos = wintypes.DWORD()
            if k32.DeviceIoControl(radio, IOCTL_BTH_DISCONNECT_DEVICE, ctypes.byref(endereco), 8, None, 0,
                                   ctypes.byref(lidos), None):
                desligou = True
            k32.CloseHandle(radio)
            if desligou:
                break
            radio = wintypes.HANDLE()
            if not bth.BluetoothFindNextRadio(busca, ctypes.byref(radio)):
                break
    finally:
        bth.BluetoothFindRadioClose(busca)
    return desligou


def _desligar_macos(mac):
    objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
    ctypes.cdll.LoadLibrary("/System/Library/Frameworks/IOBluetooth.framework/IOBluetooth")
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    endereco_envio = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value

    def enviar(retorno, *argumentos):
        return ctypes.CFUNCTYPE(retorno, ctypes.c_void_p, ctypes.c_void_p, *argumentos)(endereco_envio)

    texto = enviar(ctypes.c_void_p, ctypes.c_char_p)(
        objc.objc_getClass(b"NSString"), objc.sel_registerName(b"stringWithUTF8String:"),
        mac.replace(":", "-").lower().encode())
    aparelho = enviar(ctypes.c_void_p, ctypes.c_void_p)(
        objc.objc_getClass(b"IOBluetoothDevice"), objc.sel_registerName(b"deviceWithAddressString:"), texto)
    if not aparelho:
        return False
    return enviar(ctypes.c_int)(aparelho, objc.sel_registerName(b"closeConnection")) == 0


class HidapiRef:
    def __init__(self, entry):
        self.entry = entry
        self.path = entry["path"]
        self.key = self.path.decode("utf-8", "replace") if isinstance(self.path, bytes) else str(self.path)
        bus = entry.get("bus_type")
        self.bluetooth = bus == BUS_BLUETOOTH if bus is not None else entry.get("interface_number", -1) == -1
        self.model = PRODUCTS.get(entry["product_id"], "DualSense")
        self.serial_string = entry.get("serial_number") or ""
        self.usb_id = None if self.bluetooth else self.key


class HidapiDevice:
    can_hide_bluetooth = plataforma.MACOS
    can_disconnect_bluetooth = plataforma.WINDOWS or plataforma.MACOS

    def __init__(self, ref):
        self.ref = ref
        self.dev = None
        self._lock = threading.Lock()
        self._seq = 0
        self._on_report = None
        self._stop = threading.Event()
        self._thread = None
        self.failed = False
        self.hidden = False
        self._exclusive = False
        self._liberar = 3

    def open(self):
        if plataforma.MACOS:
            _set_darwin_exclusive(self._exclusive)
        dev = hid.device()
        dev.open_path(self.ref.path)
        if plataforma.MACOS and self._exclusive:
            _set_darwin_exclusive(False)
        self.dev = dev
        try:
            dev.get_feature_report(CALIBRATION_REPORT, CALIBRATION_SIZE)
        except (OSError, ValueError):
            pass

    def start(self, on_report):
        self._on_report = on_report
        self._start_reader()

    def _start_reader(self):
        self._stop.clear()
        dev = self.dev

        def loop():
            while not self._stop.is_set():
                try:
                    data = dev.read(128, 100)
                except (OSError, ValueError):
                    if not self._stop.is_set():
                        self.failed = True
                    return
                if data:
                    if data[0] == BT_INPUT_ID and not self.ref.bluetooth:
                        self.ref.bluetooth = True
                        self.ref.usb_id = None
                        self._liberar = 3
                    self._on_report(bytes(data))
        self._thread = threading.Thread(target=loop, name="dualsense-hidapi", daemon=True)
        self._thread.start()

    def _stop_reader(self):
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)
        self._thread = None

    def send(self, state):
        report = build_report(state, self.ref.bluetooth, self._seq, setup=self._liberar > 0)
        self._liberar = max(0, self._liberar - 1)
        self._seq = (self._seq + 1) & 0x0F
        if not self.ref.bluetooth:
            report = report[:USB_OUTPUT_SIZE]
        with self._lock:
            if self.dev.write(report) < 0:
                raise OSError("falha ao escrever no controle")

    def read_info(self):
        info = {"model": self.ref.model, "connection": "bluetooth" if self.ref.bluetooth else "usb",
                "mac": None, "firmware": None, "hardware": None, "update": None, "build": None}
        try:
            info.update(firmware.parse(self.dev.get_feature_report(firmware.REPORT_ID, firmware.SIZE)))
        except (OSError, ValueError):
            pass
        if not self.ref.bluetooth:
            try:
                info["mac"] = firmware.parse_mac(self.dev.get_feature_report(firmware.MAC_REPORT_ID, firmware.MAC_SIZE))
            except (OSError, ValueError):
                pass
        if not info["mac"] and len(self.ref.serial_string.replace(":", "").replace("-", "")) == 12:
            raw = self.ref.serial_string.replace(":", "").replace("-", "").upper()
            info["mac"] = ":".join(raw[i:i + 2] for i in range(0, 12, 2))
        return info

    def read_serial(self):
        if self.ref.bluetooth:
            return None
        return factory.read_serial(lambda data: self.dev.send_feature_report(data),
                                   lambda rid, size: self.dev.get_feature_report(rid, size))

    def battery(self):
        return None, None

    def _reopen(self, exclusive):
        self._stop_reader()
        with self._lock:
            try:
                self.dev.close()
            except (OSError, ValueError):
                pass
            self._exclusive = exclusive
            self.open()
        self._start_reader()

    def hide(self):
        if plataforma.WINDOWS:
            if self.ref.bluetooth or not hidhide.available():
                return False
            self.hidden = hidhide.hide(self.ref.path)
            return self.hidden
        if plataforma.MACOS:
            try:
                self._reopen(True)
            except (OSError, ValueError):
                self._reopen(False)
                return False
            self.hidden = True
            return True
        return False

    def unhide(self):
        if not self.hidden:
            return None
        if plataforma.WINDOWS:
            hidhide.unhide(self.ref.path)
        elif plataforma.MACOS:
            try:
                self._reopen(False)
            except (OSError, ValueError):
                self.failed = True
        self.hidden = False
        return None

    def grab(self):
        return []

    def release(self):
        pass

    def disconnect_bluetooth(self, mac):
        if not (self.can_disconnect_bluetooth and self.ref.bluetooth and mac):
            return False
        try:
            return _desligar_windows(mac) if plataforma.WINDOWS else _desligar_macos(mac)
        except (OSError, ValueError, AttributeError):
            return False

    def close(self):
        if self.hidden:
            self.unhide()
        self._stop_reader()
        if self.dev:
            try:
                self.dev.close()
            except (OSError, ValueError):
                pass
            self.dev = None


class HidapiBackend:
    name = "hidapi"

    def startup(self):
        return 0

    def find(self):
        for entry in hid.enumerate(SONY, 0):
            if entry.get("product_id") in PRODUCTS:
                return HidapiRef(entry)
        return None

    def open(self, ref):
        device = HidapiDevice(ref)
        device.open()
        return device
