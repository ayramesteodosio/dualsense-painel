import os
import signal
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import atualizacao, charge_light, config
from .protocol import MODES_BY_KEY, TRIGGER_MODES
from .session import Session, acquire_lock
from .versao import VERSAO
from .telas.ajustes import AjustesGroup, HistoricoGroup
from .telas.info import InfoPage
from .telas.perfis import PerfisGroup
from .telas.teste import TestePage

APP_ID = "com.ayrames.DualSensePainel"
RULES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "dados", "70-dualsense-painel.rules")

PRESETS = [
    ("Azul PlayStation", (0, 90, 255)), ("Branco", (255, 255, 255)), ("Vermelho", (255, 0, 0)),
    ("Laranja", (255, 90, 0)), ("Amarelo", (255, 200, 0)), ("Verde", (0, 255, 40)),
    ("Ciano", (0, 220, 255)), ("Roxo", (140, 0, 255)), ("Rosa", (255, 0, 140)),
]

STATUS_PT = {"Charging": "carregando", "Discharging": "na bateria", "Full": "carga completa",
             "Not charging": "sem carregar"}

CSS = "\n".join(
    f".swatch-{i} {{ background: rgb{c}; min-width: 26px; min-height: 26px; padding: 0; }}"
    for i, (_, c) in enumerate(PRESETS)
) + """
.battery-number { font-size: 42px; font-weight: 800; }
.charge-card { padding: 24px 12px 12px 12px; }
.chip { padding: 6px 8px; border-radius: 999px; background: alpha(currentColor, 0.08); font-size: 0.9em; }
.chip-done { background: alpha(@success_color, 0.28); }
.chip-on { background: @accent_bg_color; color: @accent_fg_color; }
.mono { font-family: monospace; }
"""


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Painel do DualSense")
        self.app = app
        self.set_default_size(540, 820)

        self.cfg = config.load()
        self.session = Session(self.cfg, self)
        self._updating = False

        self.toasts = Adw.ToastOverlay()
        self.stack = Adw.ViewStack()
        header = Adw.HeaderBar()
        switcher = Adw.ViewSwitcherTitle(stack=self.stack, title="Painel do DualSense")
        header.set_title_widget(switcher)
        bottom = Adw.ViewSwitcherBar(stack=self.stack)
        switcher.bind_property("title-visible", bottom, "reveal", 0)

        self.empty = Adw.StatusPage(
            icon_name="input-gaming-symbolic", title="Nenhum controle conectado",
            description="Ligue o DualSense no cabo USB ou pareie pelo Bluetooth.")
        self.outer = Gtk.Stack()
        self.outer.add_named(self.empty, "vazio")
        self.outer.add_named(self.stack, "controle")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(header)
        self.toasts.set_child(self.outer)
        self.toasts.set_vexpand(True)
        box.append(self.toasts)
        box.append(bottom)
        self.set_content(box)

        self._build_main_page()
        self._build_lights_page()
        self._build_triggers_page()
        self.teste = TestePage(self)
        self.stack.add_titled(self.teste.widget, "teste", "Teste").set_icon_name("applications-engineering-symbolic")
        self.info = InfoPage(self)
        self.stack.add_titled(self.info.widget, "info", "Informações").set_icon_name("help-about-symbolic")
        self.stack.connect("notify::visible-child-name", lambda *_: self.info.refresh())
        self.connect("close-request", self._on_close)

        self.mode_changed()
        self.historico.refresh()
        GLib.timeout_add_seconds(60, lambda: self.historico.refresh() or True)
        self.session.start()
        if app.start_charging:
            self.set_charging(True)


    def _build_main_page(self):
        page = Adw.PreferencesPage()

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, halign=Gtk.Align.CENTER)
        card.add_css_class("charge-card")
        self.battery_label = Gtk.Label(label="--%")
        self.battery_label.add_css_class("battery-number")
        self.battery_status = Gtk.Label()
        self.battery_status.add_css_class("dim-label")
        self.battery_bar = Gtk.LevelBar(min_value=0, max_value=100, width_request=240)
        self.mode_label = Gtk.Label()
        self.mode_label.add_css_class("title-4")
        self.mode_label.set_margin_top(12)
        self.mode_button = Gtk.Button(margin_top=6)
        self.mode_button.add_css_class("pill")
        self.mode_button.connect("clicked", lambda *_: self.set_charging(not self.session.charging_mode))
        for w in (self.battery_label, self.battery_status, self.battery_bar, self.mode_label, self.mode_button):
            card.append(w)
        top = Adw.PreferencesGroup()
        top.add(card)
        page.add(top)

        group = Adw.PreferencesGroup(title="Modo carregar")
        group.set_description(
            "No cabo USB, o controle sai do sistema: desktop, Steam e jogos param de enxergá-lo, "
            "e as luzes apagam, menos a luz laranja de carga se ela estiver ligada. Pelo "
            "Bluetooth, só os botões e o touchpad são bloqueados. A carga continua normal.")
        self.connection_row = Adw.ActionRow(title="Conexão")
        group.add(self.connection_row)

        auto_row = Adw.ActionRow(title="Entrar sozinho ao ligar no cabo",
                                 subtitle="Quando o controle aparecer pelo USB")
        self.auto_switch = Gtk.Switch(valign=Gtk.Align.CENTER, active=self.cfg["auto_charge"])
        self.auto_switch.connect("notify::active", self._on_auto_changed)
        auto_row.add_suffix(self.auto_switch)
        auto_row.set_activatable_widget(self.auto_switch)
        group.add(auto_row)

        self.permission_row = Adw.ActionRow(
            title="Touchpad ainda passa",
            subtitle="Falta uma permissão para bloquear o touchpad e os sensores. Pede a senha uma vez.")
        fix = Gtk.Button(label="Liberar", valign=Gtk.Align.CENTER)
        fix.add_css_class("suggested-action")
        fix.connect("clicked", self._install_rules)
        self.permission_row.add_suffix(fix)
        self.permission_row.set_visible(False)
        group.add(self.permission_row)
        page.add(group)
        page.add(self._build_charge_light_group())
        self.historico = HistoricoGroup(self.session)
        page.add(self.historico.widget)
        self.ajustes = AjustesGroup(self)
        page.add(self.ajustes.widget)

        page_ref = self.stack.add_titled(page, "inicio", "Controle")
        page_ref.set_icon_name("battery-good-charging-symbolic")

    def _build_charge_light_group(self):
        group = Adw.PreferencesGroup(title="Luz no modo carregar",
                                     description="Muda na hora, inclusive com o controle carregando.")
        glow = Adw.ExpanderRow(title="Acender enquanto carrega", show_enable_switch=True,
                               subtitle="Como o laranja do PS5 em repouso")
        glow.set_enable_expansion(self.cfg["charge_glow"])
        glow.set_expanded(self.cfg["charge_glow"])
        glow.connect("notify::enable-expansion", self._on_glow_changed)
        group.add(glow)

        self.charge_color = Gtk.ColorButton(valign=Gtk.Align.CENTER, use_alpha=False)
        self.charge_color.set_rgba(self._rgba(self.cfg["charge_color"]))
        self.charge_color.connect("color-set", self._on_charge_color)
        reset = Gtk.Button(icon_name="edit-undo-symbolic", valign=Gtk.Align.CENTER,
                           tooltip_text="Voltar ao laranja")
        reset.add_css_class("flat")
        reset.connect("clicked", self._on_charge_color_reset)
        color_row = Adw.ActionRow(title="Cor")
        color_row.add_suffix(reset)
        color_row.add_suffix(self.charge_color)
        glow.add_row(color_row)

        style = Adw.ComboRow(title="Estilo", model=Gtk.StringList.new(list(charge_light.STYLE_LABELS)))
        style.set_selected(charge_light.STYLES.index(self.cfg["charge_style"]))
        style.connect("notify::selected", self._on_charge_choice, "charge_style", charge_light.STYLES)
        glow.add_row(style)

        speed = self._scale(1, 10, self.cfg["charge_period"], lambda v: f"{v:.1f} s")
        speed.set_digits(1)
        speed.set_round_digits(1)
        speed.get_adjustment().set_step_increment(0.5)
        speed.connect("value-changed", self._on_charge_number, "charge_period", float)
        glow.add_row(self._row("Duração do ciclo", speed, "Maior é mais lento"))

        intensity = self._scale(5, 100, self.cfg["charge_intensity"], lambda v: f"{v:.0f}%")
        intensity.connect("value-changed", self._on_charge_number, "charge_intensity", int)
        glow.add_row(self._row("Intensidade", intensity))

        full = Adw.ComboRow(title="Quando encher", model=Gtk.StringList.new(list(charge_light.FULL_LABELS)))
        full.set_selected(charge_light.FULL_ACTIONS.index(self.cfg["charge_full"]))
        full.connect("notify::selected", self._on_charge_choice, "charge_full", charge_light.FULL_ACTIONS)
        glow.add_row(full)
        return group

    def _build_lights_page(self):
        page = Adw.PreferencesPage()
        self.lights_page = page

        bar = Adw.PreferencesGroup(title="Barra de luz")
        color_row = Adw.ActionRow(title="Cor")
        self.color_button = Gtk.ColorButton(valign=Gtk.Align.CENTER, use_alpha=False)
        self.color_button.set_rgba(self._rgba(self.cfg["color"]))
        self.color_button.connect("color-set", self._on_color_button)
        color_row.add_suffix(self.color_button)
        bar.add(color_row)

        swatches = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=9,
                               min_children_per_line=5, column_spacing=6, row_spacing=6,
                               margin_top=10, margin_bottom=10, margin_start=10, margin_end=10)
        for i, (name, rgb) in enumerate(PRESETS):
            b = Gtk.Button(tooltip_text=name)
            b.add_css_class("circular")
            b.add_css_class(f"swatch-{i}")
            b.connect("clicked", self._on_preset, rgb)
            swatches.insert(b, -1)
        swatch_row = Adw.PreferencesRow(activatable=False)
        swatch_row.set_child(swatches)
        bar.add(swatch_row)

        self.intensity = self._scale(0, 100, self.cfg["intensity"], lambda v: f"{v:.0f}%")
        self.intensity.connect("value-changed", self._on_intensity)
        bar.add(self._row("Intensidade", self.intensity))
        self.lightbar_mode = Adw.ComboRow(title="Modo da barra de luz",
                                          subtitle="Mostrar a bateria: verde, amarelo e vermelho conforme a carga",
                                          model=Gtk.StringList.new(["Cor fixa", "Mostrar a bateria"]))
        self.lightbar_mode.set_selected(1 if self.cfg["lightbar_mode"] == "battery" else 0)
        self.lightbar_mode.connect("notify::selected", self._on_lightbar_mode)
        bar.add(self.lightbar_mode)
        page.add(bar)

        players = Adw.PreferencesGroup(title="LEDs do jogador",
                                       description="Os cinco pontinhos embaixo do touchpad.")
        leds_box = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        self.led_toggles = []
        for i in range(5):
            t = Gtk.ToggleButton(active=bool(self.cfg["player_leds"] & (1 << i)))
            t.add_css_class("circular")
            t.set_child(Gtk.Image(icon_name="media-record-symbolic"))
            t.connect("toggled", self._on_led_toggle)
            self.led_toggles.append(t)
            leds_box.append(t)
        players.add(self._row("Acesos", leds_box))
        self.led_brightness = Adw.ComboRow(title="Brilho", model=Gtk.StringList.new(["Alto", "Médio", "Baixo"]))
        self.led_brightness.set_selected(self.cfg["led_brightness"])
        self.led_brightness.connect("notify::selected", self._on_simple, "led_brightness")
        players.add(self.led_brightness)
        page.add(players)

        extras = Adw.PreferencesGroup(title="Outros")
        self.mic_led = Adw.ComboRow(title="Luz do botão de microfone",
                                    model=Gtk.StringList.new(["Apagada", "Acesa", "Pulsando"]))
        self.mic_led.set_selected(self.cfg["mic_led"])
        self.mic_led.connect("notify::selected", self._on_simple, "mic_led")
        extras.add(self.mic_led)
        rumble = Gtk.Button(label="Testar", valign=Gtk.Align.CENTER)
        rumble.connect("clicked", self._test_rumble)
        extras.add(self._row("Vibração", rumble, "Os dois motores por meio segundo"))
        page.add(extras)

        self.perfis = PerfisGroup(self)
        page.add(self.perfis.widget)
        page_ref = self.stack.add_titled(page, "luzes", "Luzes")
        page_ref.set_icon_name("display-brightness-symbolic")

    def _build_triggers_page(self):
        page = Adw.PreferencesPage()
        self.triggers_page = page
        self.trigger_ui = {}
        for side, title in (("l2", "Gatilho esquerdo (L2)"), ("r2", "Gatilho direito (R2)")):
            group = Adw.PreferencesGroup(title=title)
            combo = Adw.ComboRow(title="Efeito", model=Gtk.StringList.new([m.label for m in TRIGGER_MODES]))
            keys = [m.key for m in TRIGGER_MODES]
            combo.set_selected(keys.index(self.cfg["triggers"][side]["mode"]))
            combo.connect("notify::selected", self._on_trigger_mode, side)
            group.add(combo)
            level = Gtk.LevelBar(min_value=0, max_value=255, width_request=180, valign=Gtk.Align.CENTER)
            level_row = self._row("Pressão agora", level, "Aperte para sentir o efeito")
            group.add(level_row)
            copy = Gtk.Button(label="Copiar para o outro", valign=Gtk.Align.CENTER)
            copy.add_css_class("flat")
            copy.connect("clicked", self._copy_trigger, side)
            copy_row = self._row("Mesmo efeito no outro gatilho", copy)
            group.add(copy_row)
            self.trigger_ui[side] = {"group": group, "combo": combo, "level": level, "rows": [],
                                     "tail": [level_row, copy_row]}
            page.add(group)
            self._rebuild_trigger_params(side)

        page_ref = self.stack.add_titled(page, "gatilhos", "Gatilhos")
        page_ref.set_icon_name("input-gaming-symbolic")

    def _rebuild_trigger_params(self, side):
        ui = self.trigger_ui[side]
        group = ui["group"]
        for row in ui["rows"] + ui["tail"]:
            group.remove(row)
        ui["rows"] = []
        trig = self.cfg["triggers"][side]
        mode = MODES_BY_KEY[trig["mode"]]
        ui["combo"].set_subtitle(mode.description)
        values = {**mode.defaults(), **trig.get("params", {})}
        for p in mode.params:
            fmt = (lambda v: f"{v * 10:.0f}%") if p.position else (lambda v: f"{v:.0f}")
            scale = self._scale(p.low, p.high, values[p.key], fmt)
            scale.connect("value-changed", self._on_trigger_param, side, p.key)
            row = self._row(p.label, scale)
            group.add(row)
            ui["rows"].append(row)
        for row in ui["tail"]:
            group.add(row)


    @staticmethod
    def _row(title, widget, subtitle=None):
        row = Adw.ActionRow(title=title)
        if subtitle:
            row.set_subtitle(subtitle)
        row.add_suffix(widget)
        return row

    @staticmethod
    def _scale(low, high, value, fmt):
        adj = Gtk.Adjustment(lower=low, upper=high, step_increment=1, page_increment=1, value=value)
        scale = Gtk.Scale(adjustment=adj, digits=0, draw_value=True, hexpand=True,
                          width_request=200, valign=Gtk.Align.CENTER)
        scale.set_round_digits(0)
        scale.set_value_pos(Gtk.PositionType.RIGHT)
        scale.set_format_value_func(lambda _s, v: fmt(v))
        return scale

    @staticmethod
    def _rgba(rgb):
        c = Gdk.RGBA()
        c.red, c.green, c.blue, c.alpha = rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, 1.0
        return c

    def toast(self, text):
        previous = getattr(self, "_toast", None)
        if previous:
            previous.dismiss()
        self._toast = Adw.Toast(title=text, timeout=2 if len(text) < 60 else 7)
        self.toasts.add_toast(self._toast)


    def changed(self):
        if not self._updating:
            self.session.settings_changed()

    def set_charging(self, on):
        self.session.set_charging(on, announce=False)

    def status_changed(self):
        ses = self.session
        self.outer.set_visible_child_name("controle" if ses.connected else "vazio")
        if not ses.connected:
            return
        pct, status = ses.battery_pct, ses.battery_status
        self.battery_label.set_label(f"{pct}%" if pct is not None else "--%")
        self.battery_bar.set_value(pct or 0)
        self.battery_status.set_label(STATUS_PT.get(status, status or "bateria desconhecida"))
        via = {"usb-detached": "cabo USB, fora do sistema", "usb": "cabo USB", "bluetooth": "Bluetooth"}
        self.connection_row.set_subtitle(f"{ses.model} pelo {via[ses.connection]}")
        self.ajustes.refresh()
        if self.stack.get_visible_child_name() == "info":
            self.info.refresh()

    def mode_changed(self):
        on = self.session.charging_mode
        self.mode_label.set_label("Modo carregar" if on else "Modo normal")
        self.mode_button.set_label("Voltar ao modo normal" if on else "Entrar no modo carregar")
        for cls in ("suggested-action", "destructive-action"):
            self.mode_button.remove_css_class(cls)
        self.mode_button.add_css_class("destructive-action" if on else "suggested-action")
        self.lights_page.set_sensitive(not on)
        self.triggers_page.set_sensitive(not on)
        self.teste.refresh_mode()
        failed = self.session.grab_failed
        self.permission_row.set_visible(on and bool([k for k in failed if k != "gamepad"]))
        if on and "gamepad" in failed:
            self.toast("Não consegui bloquear os botões do controle")

    def input(self, data):
        page = self.stack.get_visible_child_name() if self.get_visible() else None
        if page == "gatilhos":
            for side, value in data["triggers"].items():
                self.trigger_ui[side]["level"].set_value(value)
        elif page == "teste":
            self.teste.update(data)

    def info_changed(self):
        self.info.refresh()

    def history_changed(self):
        self.historico.refresh()

    def sync_widgets(self):
        self._updating = True
        try:
            self.color_button.set_rgba(self._rgba(self.cfg["color"]))
            self.intensity.set_value(self.cfg["intensity"])
            for i, t in enumerate(self.led_toggles):
                t.set_active(bool(self.cfg["player_leds"] & (1 << i)))
            self.led_brightness.set_selected(self.cfg["led_brightness"])
            self.mic_led.set_selected(self.cfg["mic_led"])
            self.lightbar_mode.set_selected(1 if self.cfg["lightbar_mode"] == "battery" else 0)
            keys = [m.key for m in TRIGGER_MODES]
            for side in ("l2", "r2"):
                self.trigger_ui[side]["combo"].set_selected(keys.index(self.cfg["triggers"][side]["mode"]))
                self._rebuild_trigger_params(side)
        finally:
            self._updating = False

    def _on_lightbar_mode(self, combo, _pspec):
        if self._updating:
            return
        self.cfg["lightbar_mode"] = "battery" if combo.get_selected() == 1 else "fixed"
        self.changed()

    def low_battery(self, pct):
        n = Gio.Notification.new("Bateria do controle baixa")
        n.set_body(f"O DualSense está com {pct}%. Hora de ligar no cabo.")
        self.app.send_notification("bateria-baixa", n)

    def charged(self):
        n = Gio.Notification.new("Controle carregado")
        n.set_body("Pode tirar do cabo ou voltar ao modo normal.")
        self.app.send_notification("carregado", n)

    def _set_color(self, rgb):
        self.cfg["color"] = list(rgb)
        self._updating = True
        self.color_button.set_rgba(self._rgba(rgb))
        self._updating = False
        self.changed()

    def _on_color_button(self, button):
        if self._updating:
            return
        c = button.get_rgba()
        self._set_color([round(c.red * 255), round(c.green * 255), round(c.blue * 255)])

    def _on_preset(self, _button, rgb):
        self._set_color(rgb)

    def _on_intensity(self, scale):
        if self._updating:
            return
        self.cfg["intensity"] = int(scale.get_value())
        self.changed()

    def _on_led_toggle(self, _toggle):
        if self._updating:
            return
        self.cfg["player_leds"] = sum(1 << i for i, t in enumerate(self.led_toggles) if t.get_active())
        self.changed()

    def _on_simple(self, combo, _pspec, key):
        if self._updating:
            return
        self.cfg[key] = combo.get_selected()
        self.changed()

    def _on_auto_changed(self, switch, _pspec):
        self.cfg["auto_charge"] = switch.get_active()
        self.changed()

    def _on_glow_changed(self, row, _pspec):
        self.cfg["charge_glow"] = row.get_enable_expansion()
        self._charge_changed()

    def _charge_changed(self):
        self.changed()

    def _on_charge_color(self, button):
        c = button.get_rgba()
        self.cfg["charge_color"] = [round(c.red * 255), round(c.green * 255), round(c.blue * 255)]
        self._charge_changed()

    def _on_charge_color_reset(self, _button):
        self.cfg["charge_color"] = list(charge_light.DEFAULTS["charge_color"])
        self.charge_color.set_rgba(self._rgba(self.cfg["charge_color"]))
        self._charge_changed()

    def _on_charge_choice(self, combo, _pspec, key, values):
        self.cfg[key] = values[combo.get_selected()]
        self._charge_changed()

    def _on_charge_number(self, scale, key, kind):
        self.cfg[key] = kind(scale.get_value())
        self._charge_changed()

    def _on_trigger_mode(self, combo, _pspec, side):
        mode = TRIGGER_MODES[combo.get_selected()]
        trig = self.cfg["triggers"][side]
        if trig["mode"] != mode.key:
            self.cfg["triggers"][side] = {"mode": mode.key, "params": mode.defaults()}
            self._rebuild_trigger_params(side)
            self.changed()

    def _on_trigger_param(self, scale, side, key):
        if self._updating:
            return
        self.cfg["triggers"][side].setdefault("params", {})[key] = int(scale.get_value())
        self.changed()

    def _copy_trigger(self, _button, side):
        other = "r2" if side == "l2" else "l2"
        src = self.cfg["triggers"][side]
        self.cfg["triggers"][other] = {"mode": src["mode"], "params": dict(src.get("params", {}))}
        self._updating = True
        self.trigger_ui[other]["combo"].set_selected([m.key for m in TRIGGER_MODES].index(src["mode"]))
        self._updating = False
        self._rebuild_trigger_params(other)
        self.changed()
        self.toast("Efeito copiado")

    def _test_rumble(self, _button):
        self.session.test_rumble()

    def _install_rules(self, _button):
        cmd = ("install -m 0644 \"$0\" /etc/udev/rules.d/70-dualsense-painel.rules && "
               "udevadm control --reload && "
               "udevadm trigger --action=change --subsystem-match=input --subsystem-match=hidraw --subsystem-match=usb")
        try:
            proc = Gio.Subprocess.new(["pkexec", "sh", "-c", cmd, RULES], Gio.SubprocessFlags.NONE)
        except GLib.Error as e:
            self.toast(f"Não deu para pedir a senha: {e.message}")
            return
        proc.wait_check_async(None, self._rules_done)

    def _rules_done(self, proc, result):
        try:
            proc.wait_check_finish(result)
        except GLib.Error:
            self.toast("Permissão não instalada")
            return
        GLib.timeout_add(800, self._regrab)

    def _regrab(self):
        if self.session.charging_mode and self.session.regrab():
            self.toast("Touchpad bloqueado também")
        return False

    def _on_close(self, _window):
        if self.session.charging_mode and self.session.connected:
            self.set_visible(False)
            self.app.hold_in_background()
            return True
        self.teste.stop_mic()
        self.session.cleanup()
        return False


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window = None
        self._held = False
        self._lock = None
        self.start_charging = False
        self._url_versao = None
        self._checando = False
        for name, on in (("carregar", True), ("normal", False)):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", self._on_mode_action, on)
            self.add_action(action)

    def _on_mode_action(self, _action, _param, on):
        if self.window:
            if self.window.session.charging_mode != on:
                self.window.set_charging(on)
        else:
            self.start_charging = on

    def _busy(self):
        dialog = Gtk.MessageDialog(message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.CLOSE,
                                   text="O controle já está sendo usado",
                                   secondary_text="O DualSense Studio está aberto. Feche ele para usar o painel.")
        self.add_window(dialog)
        dialog.connect("response", lambda d, _r: d.destroy())
        dialog.present()

    def do_startup(self):
        Adw.Application.do_startup(self)
        Gtk.Window.set_default_icon_name(APP_ID)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, self._on_signal)

    def _on_signal(self):
        self.quit()
        return GLib.SOURCE_REMOVE

    def do_shutdown(self):
        if self.window:
            self.window.session.cleanup()
        Adw.Application.do_shutdown(self)

    def do_activate(self):
        if not self.window and not self._lock:
            self._lock = acquire_lock()
            if self._lock is None:
                self._busy()
                return
        if not self.window:
            self.window = Window(self)
        if not self._checando:
            self._checando = True
            GLib.timeout_add_seconds(5, self._checar_versao)
            GLib.timeout_add_seconds(24 * 3600, self._checar_versao, True)
        if self._held:
            self.release()
            self._held = False
        self.window.set_visible(True)
        self.window.present()

    def _checar_versao(self, repetir=False):
        atualizacao.verificar("dualsense-painel", VERSAO,
                              lambda tag, url: GLib.idle_add(self._nova_versao, tag, url))
        return repetir

    def _nova_versao(self, tag, url):
        if url != self._url_versao and self.window:
            self._url_versao = url
            toast = Adw.Toast(title=f"Versão {tag} disponível", timeout=0)
            toast.set_button_label("Baixar")
            toast.connect("button-clicked", lambda *_: Gtk.show_uri(self.window, url, Gdk.CURRENT_TIME))
            self.window.toasts.add_toast(toast)
        return False

    def hold_in_background(self):
        if not self._held:
            self.hold()
            self._held = True
            n = Gio.Notification.new("Modo carregar continua ligado")
            n.set_body("Abra o Painel do DualSense de novo para voltar ao modo normal.")
            self.send_notification("segundo-plano", n)


def main():
    GLib.set_prgname(APP_ID)
    GLib.set_application_name("Painel do DualSense")
    app = App()
    argv = [a for a in sys.argv if a not in ("--carregar", "--normal")]
    mode = "carregar" if "--carregar" in sys.argv else "normal" if "--normal" in sys.argv else None
    if mode:
        app.register(None)
        if app.get_is_remote():
            app.activate_action(mode, None)
            return 0
        app.start_charging = mode == "carregar"
    return app.run(argv)
