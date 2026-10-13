import sys
import threading
import time

from . import charge_light, config, factory, inputs, plataforma
from .history import BatteryHistory
from .idioma import _
from .protocol import MODES_BY_KEY, OutputState, dark_state

SHORTCUT_SECONDS = 2.0
ACTIVITY_STICK = 24
BATTERY_COLORS = ((60, (0, 255, 40)), (25, (255, 200, 0)), (0, (255, 0, 0)))
RETURN_GRACE = 4



def registrar(texto):
    try:
        print(time.strftime("%H:%M:%S"), texto, file=sys.stderr, flush=True)
    except Exception:
        pass

class Listener:
    def status_changed(self):
        pass

    def mode_changed(self):
        pass

    def input(self, data):
        pass

    def info_changed(self):
        pass

    def history_changed(self):
        pass

    def toast(self, text):
        pass

    def charged(self):
        pass

    def low_battery(self, pct):
        pass


def acquire_lock():
    return plataforma.acquire_lock()


def battery_color(pct):
    for limit, rgb in BATTERY_COLORS:
        if (pct or 0) >= limit:
            return rgb
    return BATTERY_COLORS[-1][1]


def is_active(data):
    if not data:
        return False
    if any(data["buttons"].values()) or any(t["active"] for t in data["touch"]):
        return True
    return any(abs(v - 128) > ACTIVITY_STICK for v in data["sticks"].values())


class Session:
    def __init__(self, cfg, listener, history=None, backend=None, loop=None):
        if loop is None:
            from .loop import GLibLoop
            loop = GLibLoop()
        if backend is None:
            from .backends import default_backend
            backend = default_backend()
        self.cfg = cfg
        self.listener = listener
        self.loop = loop
        self.backend = backend
        self.history = history if history is not None else BatteryHistory()
        self.device = None
        self.charging_mode = False
        self.grab_failed = []
        self.battery_pct = None
        self.battery_status = None
        self.input = None
        self.info = None
        self.report_hz = 0
        self._last_model = None
        self._grace_until = 0.0
        self._auto_block = None
        self._started = False
        self._pulse_source = None
        self._save_source = None
        self._poll_source = None
        self._input_source = None
        self._was_full = False
        self._low_warned = False
        self._raw = None
        self._raw_count = 0
        self._raw_seen = 0
        self._registrou = False
        self._aviso_cheio = -100.0
        self._hz_mark = (time.monotonic(), 0)
        self._combo_since = None
        self._combo_fired = False
        self._last_activity = time.monotonic()

    def start(self):
        if self.backend.startup():
            self.loop.timeout_add(1500, self._poll_once)
        self._poll()
        self._poll_source = self.loop.timeout_add_seconds(1, self._poll)
        self._input_source = self.loop.timeout_add(16, self._tick_input)

    @property
    def _attached(self):
        return self.device is not None

    @property
    def hidden(self):
        return bool(self.device and self.device.hidden)

    @property
    def _returning(self):
        return not self._attached and time.monotonic() < self._grace_until

    @property
    def connected(self):
        return self._attached or self._returning

    @property
    def model(self):
        if self.device:
            return self.device.ref.model
        return self._last_model if self._returning else None

    @property
    def connection(self):
        if self.device:
            if self.device.hidden:
                return "usb-detached"
            return "bluetooth" if self.device.ref.bluetooth else "usb"
        return "usb" if self._returning else None

    def normal_state(self):
        k = self.cfg["intensity"] / 100
        base = battery_color(self.battery_pct) if self.cfg["lightbar_mode"] == "battery" else self.cfg["color"]
        state = OutputState(
            lightbar=tuple(round(c * k) for c in base),
            player_leds=self.cfg["player_leds"],
            led_brightness=self.cfg["led_brightness"],
            mic_led=self.cfg["mic_led"],
        )
        for side, attr in (("l2", "left_trigger"), ("r2", "right_trigger")):
            trig = self.cfg["triggers"][side]
            setattr(state, attr, MODES_BY_KEY[trig["mode"]].encode(trig.get("params", {})))
        return state

    def charge_state(self):
        state = dark_state()
        state.lightbar = charge_light.lightbar(self.cfg, self.battery_status, time.monotonic())
        return state

    def push(self, state=None):
        if not self.device:
            return
        if self.device.hidden:
            state = self.charge_state()
        elif state is None:
            state = self.charge_state() if self.charging_mode else self.normal_state()
        try:
            self.device.send(state)
        except OSError as e:
            registrar(f"falha ao enviar: {e}")
            self._drop_device()

    def settings_changed(self):
        self._update_pulse()
        self.push()
        self._avisar_cheio()
        if self._save_source:
            self.loop.source_remove(self._save_source)
        self._save_source = self.loop.timeout_add(600, self._save)

    def flush_save(self):
        if self._save_source:
            self.loop.source_remove(self._save_source)
            self._save()

    def _save(self):
        self._save_source = None
        try:
            config.save(self.cfg)
        except OSError as e:
            self.listener.toast(_("Não consegui salvar as preferências: {erro}").format(erro=e.strerror))
        return False

    def set_charging(self, on, announce=True):
        registrar(f"modo carregar: {on} bateria={self.battery_pct} {self.battery_status}")
        if not on:
            self._auto_block = self.device.ref.usb_id if self.device else None
        self.charging_mode = on
        if on and self.device and not self.device.hidden:
            self._hide()
        elif not on and self.device:
            if self.device.hidden:
                if self.device.unhide() == "rediscover":
                    self._grace_until = time.monotonic() + RETURN_GRACE
                    self._drop_device(close=False)
                    self.loop.timeout_add(700, self._poll_once)
                    self.loop.timeout_add(int(RETURN_GRACE * 1000) + 100, self._poll_once)
            else:
                self.device.release()
                self.grab_failed = []
        self.push()
        self._mode_changed()
        self._refresh_status()
        if announce and on and self._attached:
            if not self._avisar_cheio(forcar=True):
                self.listener.toast(_("Modo carregar ligado"))
        elif announce and not on:
            self.listener.toast(_("De volta ao modo normal"))

    def _avisar_cheio(self, forcar=False):
        if not (self.charging_mode and self._attached and self.battery_status == "Full"):
            return False
        if not self.cfg.get("charge_glow", True) or self.cfg.get("charge_full", "off") != "off":
            return False
        agora = time.monotonic()
        if not forcar and agora - self._aviso_cheio < 20:
            return False
        self._aviso_cheio = agora
        self.listener.toast(_("O controle já está cheio, por isso a luz apagou. "
                              "Para deixar acesa, mude \"Quando encher\" na luz do modo carregar."))
        return True

    def _hide(self):
        dev = self.device
        if dev.ref.bluetooth and not dev.can_hide_bluetooth:
            self.grab_failed = dev.grab()
            return
        escondido = dev.hide()
        registrar(f"esconder dos jogos: {escondido}")
        if escondido:
            self.grab_failed = []
            return
        self.grab_failed = dev.grab()
        if not dev.ref.bluetooth:
            if plataforma.WINDOWS:
                self.listener.toast(_("Para esconder o controle dos jogos no Windows, instale o HidHide"))
            else:
                self.listener.toast(_("Não consegui tirar o controle da Steam, só do desktop"))

    def rumble(self, left, right, ms=500):
        if not self.device or self.charging_mode:
            return
        state = self.normal_state()
        state.rumble = (max(0, min(255, int(left))), max(0, min(255, int(right))))
        self.push(state)

        def stop():
            if self.device and not self.charging_mode:
                s = self.normal_state()
                s.rumble = (0, 0)
                self.push(s)
            return False
        self.loop.timeout_add(max(50, min(5000, int(ms))), stop)

    def test_rumble(self):
        self.rumble(200, 200, 500)

    @property
    def pode_desligar_bluetooth(self):
        return bool(self.device and getattr(self.device, "can_disconnect_bluetooth", False))

    def disconnect_bluetooth(self):
        mac = (self.info or {}).get("mac")
        if not self.device or not self.device.ref.bluetooth:
            return False
        if not self.device.disconnect_bluetooth(mac):
            self.listener.toast(_("Desligar pelo Bluetooth não está disponível neste sistema"))
            return False
        self.listener.toast(_("Desligando o controle"))
        return True

    def regrab(self):
        if self.device and self.charging_mode and not self.device.hidden:
            self.grab_failed = self.device.grab()
            self._mode_changed()
        return not [k for k in self.grab_failed if k != "gamepad"]

    def cleanup(self):
        self.flush_save()
        self._drop_device()
        for name in ("_poll_source", "_input_source"):
            source = getattr(self, name)
            if source:
                self.loop.source_remove(source)
                setattr(self, name, None)

    def _mode_changed(self):
        self._update_pulse()
        self.listener.mode_changed()

    def _stop_pulse(self):
        if self._pulse_source:
            self.loop.source_remove(self._pulse_source)
            self._pulse_source = None

    def _update_pulse(self):
        want = bool(self._attached and self.charging_mode
                    and charge_light.animated(self.cfg, self.battery_status))
        if want and not self._pulse_source:
            self._pulse_source = self.loop.timeout_add(40, self._pulse)
        elif not want and self._pulse_source:
            self._stop_pulse()
            self.push()

    def _pulse(self):
        self.push()
        return True

    def _poll_once(self):
        self._poll()
        return False

    def _poll(self):
        self._update_hz()
        if self.device and self.device.failed:
            self._drop_device()
            self.listener.status_changed()
        if self.device and self.device.hidden:
            self._refresh_status()
            return True
        ref = self.backend.find()
        if ref is None and not self._returning:
            self._auto_block = None
        current = self.device.ref if self.device else None
        if ref is None and current is not None:
            self._drop_device()
        elif ref is not None and (current is None or ref.key != current.key):
            was_usb = current is not None and not current.bluetooth
            self._drop_device()
            self._attach(ref)
            fresh = ref.usb_id not in (None, self._auto_block)
            if self.cfg["auto_charge"] and fresh and not was_usb and not self.charging_mode and self.device:
                self.set_charging(True, announce=self._started)
        self._check_idle()
        self._refresh_status()
        self._started = True
        return True

    def _update_hz(self):
        now = time.monotonic()
        mark_time, mark_count = self._hz_mark
        if self._raw_count < mark_count:
            self._hz_mark = (now, self._raw_count)
        elif now - mark_time >= 1:
            self.report_hz = round((self._raw_count - mark_count) / (now - mark_time))
            self._hz_mark = (now, self._raw_count)

    def _on_report(self, report):
        if report == self._raw:
            return
        self._raw = report
        self._raw_count += 1

    def _attach(self, ref):
        try:
            dev = self.backend.open(ref)
        except (OSError, ValueError) as e:
            self.listener.toast(_("Sem acesso ao controle ({erro})").format(erro=getattr(e, 'strerror', None) or e))
            return
        self.device = dev
        registrar(f"conectado: {ref.model} bluetooth={ref.bluetooth} caminho={ref.key}")
        self._last_model = ref.model
        self._grace_until = 0.0
        self._last_activity = time.monotonic()
        self.input = None
        self._registrou = False
        dev.start(self._on_report)
        self.info = dev.read_info()
        self._load_factory(dev)
        self.listener.info_changed()
        if self.charging_mode:
            self._hide()
        self.push()
        self._mode_changed()

    def _load_factory(self, dev):
        mac = self.info.get("mac")
        cached = factory.load_cache().get(mac) if mac else None
        if cached:
            self.info.update(cached)
        if cached or dev.ref.bluetooth:
            return
        if not factory.supported(self.info.get("hardware"), self.info.get("firmware")):
            return
        info = self.info

        def work():
            try:
                decoded = factory.decode(dev.read_serial())
            except (OSError, ValueError):
                decoded = None
            if decoded:
                factory.remember(mac, decoded)
                self.loop.idle_add(self._factory_ready, info, decoded)
        threading.Thread(target=work, daemon=True).start()

    def _factory_ready(self, info, decoded):
        if self.info is info:
            info.update(decoded)
            self.listener.info_changed()
        return False

    def _drop_device(self, close=True):
        self._stop_pulse()
        dev, self.device = self.device, None
        if dev and close:
            dev.close()
        self._raw = None

    def _tick_input(self):
        if self._raw is not None and self._raw_count != self._raw_seen:
            self._raw_seen = self._raw_count
            parsed = inputs.parse(self._raw)
            if self.input is None and not self._registrou:
                self._registrou = True
                registrar(f"primeiro relatório: id=0x{self._raw[0]:02x} tamanho={len(self._raw)} lido={parsed is not None}")
            if parsed:
                self._handle_input(parsed)
                self.listener.input(parsed)
        return True

    def _handle_input(self, data):
        self.input = data
        if is_active(data):
            self._last_activity = time.monotonic()
        self._check_shortcut(data["buttons"])

    def _check_shortcut(self, buttons):
        if not self.cfg["shortcut"]:
            return
        if not (buttons["ps"] and buttons["options"]):
            self._combo_since = None
            self._combo_fired = False
            return
        now = time.monotonic()
        if self._combo_since is None:
            self._combo_since = now
        elif not self._combo_fired and now - self._combo_since >= SHORTCUT_SECONDS:
            self._combo_fired = True
            self.loop.idle_add(self._toggle_from_shortcut)

    def _toggle_from_shortcut(self):
        self.set_charging(not self.charging_mode)
        return False

    def _check_idle(self):
        minutes = self.cfg["idle_off"]
        if not minutes or not self.device or not self.device.ref.bluetooth:
            return
        if time.monotonic() - self._last_activity >= minutes * 60:
            self._last_activity = time.monotonic()
            self.disconnect_bluetooth()

    def _battery_now(self):
        if not self.device:
            return None, None
        pct, status = self.device.battery()
        if pct is None and self.input:
            return self.input["battery"]
        return pct, status

    def _refresh_status(self):
        if self._returning:
            return
        pct, status = self._battery_now()
        status_changed = status != self.battery_status
        pct_changed = pct != self.battery_pct
        self.battery_pct, self.battery_status = pct, status
        if status_changed:
            registrar(f"bateria: {pct} {status}")
        if self._attached:
            self._update_pulse()
            if status_changed and self.charging_mode and not self._pulse_source:
                self.push()
            if pct_changed and not self.charging_mode and self.cfg["lightbar_mode"] == "battery":
                self.push()
            if self.history.record(pct, status):
                self.listener.history_changed()
        full = self._attached and self.charging_mode and (status == "Full" or pct == 100)
        if full and not self._was_full:
            self.listener.charged()
        self._was_full = full
        self._check_low_battery(pct, status)
        self.listener.status_changed()

    def _check_low_battery(self, pct, status):
        limit = self.cfg["low_battery"]
        if not limit or pct is None:
            return
        if status == "Discharging" and pct <= limit and not self._low_warned:
            self._low_warned = True
            self.listener.low_battery(pct)
        elif status != "Discharging" or pct > limit + 5:
            self._low_warned = False
