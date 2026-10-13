import math

from gi.repository import Adw, GLib, Gtk

from .. import audio, idioma
from ..idioma import N_, _
from ..tester import BUTTONS, DRIFT_TEXT, Tester

STATUS_PT = {"Charging": N_("carregando"), "Discharging": N_("na bateria"), "Full": N_("carga completa")}


def _fmt(value, digits=1):
    texto = f"{value:.{digits}f}"
    return texto.replace(".", ",") if idioma.atual() == "pt" else texto


def _accent(widget):
    ok, color = widget.get_style_context().lookup_color("accent_bg_color")
    return (color.red, color.green, color.blue) if ok else (0.21, 0.52, 0.89)


class StickView(Gtk.DrawingArea):
    def __init__(self, stick_getter):
        super().__init__(content_width=150, content_height=150)
        self.stick_getter = stick_getter
        self.set_draw_func(self._draw)

    def _draw(self, _area, cr, w, h):
        st = self.stick_getter()
        r = min(w, h) / 2 - 6
        cx, cy = w / 2, h / 2
        fg = self.get_style_context().get_color()
        ar, ag, ab = _accent(self)
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.06)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.25)
        cr.set_line_width(1)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.stroke()
        cr.move_to(cx - r, cy)
        cr.line_to(cx + r, cy)
        cr.move_to(cx, cy - r)
        cr.line_to(cx, cy + r)
        cr.stroke()
        bins = st.bins
        if any(bins):
            cr.set_source_rgba(ar, ag, ab, 0.18)
            for i, v in enumerate(bins):
                a = -math.pi + (i + 0.5) / len(bins) * 2 * math.pi
                x, y = cx + math.cos(a) * v * r, cy + math.sin(a) * v * r
                (cr.line_to if i else cr.move_to)(x, y)
            cr.close_path()
            cr.fill()
        for i, (x, y) in enumerate(st.trail):
            cr.set_source_rgba(ar, ag, ab, (i + 1) / len(st.trail) * 0.5)
            cr.arc(cx + x * r, cy + y * r, 2, 0, 2 * math.pi)
            cr.fill()
        cr.set_source_rgb(ar, ag, ab)
        cr.arc(cx + st.x * r, cy + st.y * r, 6, 0, 2 * math.pi)
        cr.fill()


class TouchView(Gtk.DrawingArea):
    def __init__(self):
        super().__init__(content_width=256, content_height=144)
        self.touch = []
        self.click = False
        self.set_draw_func(self._draw)

    def _draw(self, _area, cr, w, h):
        fg = self.get_style_context().get_color()
        ar, ag, ab = _accent(self)
        radius = 12
        cr.new_sub_path()
        for x, y, a in ((w - radius, radius, -math.pi / 2), (w - radius, h - radius, 0),
                        (radius, h - radius, math.pi / 2), (radius, radius, math.pi)):
            cr.arc(x, y, radius, a, a + math.pi / 2)
        cr.close_path()
        cr.set_source_rgba(ar, ag, ab, 0.22) if self.click else cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.07)
        cr.fill_preserve()
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.25)
        cr.set_line_width(1)
        cr.stroke()
        for t in self.touch:
            if not t["active"]:
                continue
            x, y = t["x"] / 1919 * w, t["y"] / 1079 * h
            cr.set_source_rgba(ar, ag, ab, 0.85)
            cr.arc(x, y, 11, 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgb(1, 1, 1)
            cr.move_to(x - 3.5, y + 4)
            cr.set_font_size(11)
            cr.show_text(str(t["id"] % 10))


class TestePage:
    def __init__(self, window):
        self.win = window
        self.session = window.session
        self.tester = Tester()
        self.mic = None
        self.widget = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.paused = Adw.StatusPage(icon_name="battery-good-charging-symbolic", title=_("Teste pausado"),
                                     description=_("No modo carregar o controle fica fora do sistema."))
        back = Gtk.Button(label=_("Voltar ao modo normal"), halign=Gtk.Align.CENTER)
        back.add_css_class("pill")
        back.add_css_class("suggested-action")
        back.connect("clicked", lambda *_: self.win.set_charging(False))
        self.paused.set_child(back)
        self.page = Adw.PreferencesPage()
        self.widget.add_named(self.page, "ativo")
        self.widget.add_named(self.paused, "pausado")
        self._build()

    def _group(self, title, description=None):
        g = Adw.PreferencesGroup(title=title)
        if description:
            g.set_description(description)
        self.page.add(g)
        return g

    def _build(self):
        top = self._group(_("Teste do controle"), _("Aperte, gire e toque. Tudo aparece aqui ao vivo."))
        bar = Gtk.Box(spacing=8)
        self.hz_label = Gtk.Label(label="-- Hz", hexpand=True, xalign=0)
        self.hz_label.add_css_class("mono")
        restart = Gtk.Button(label=_("Recomeçar"))
        restart.connect("clicked", self._restart)
        report = Gtk.Button(label=_("Gerar relatório"))
        report.add_css_class("suggested-action")
        report.connect("clicked", self._report)
        for w in (self.hz_label, restart, report):
            bar.append(w)
        top.add(bar)

        self.buttons_group = self._group(_("Botões"))
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=3,
                           max_children_per_line=5, column_spacing=6, row_spacing=6, homogeneous=True)
        self.chips = {}
        for key, label in BUTTONS:
            chip = Gtk.Label(label=_(label))
            chip.add_css_class("chip")
            self.chips[key] = chip
            flow.insert(chip, -1)
        self.buttons_group.add(flow)

        sticks = self._group(_("Analógicos"), _("Gire cada analógico encostando na borda para medir a circularidade."))
        box = Gtk.Box(spacing=12, homogeneous=True)
        self.stick_views, self.stick_labels = {}, {}
        for side, name in (("l", _("Esquerdo")), ("r", _("Direito"))):
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            title = Gtk.Label(label=name, xalign=0)
            title.add_css_class("heading")
            view = StickView(lambda s=side: self.tester.sticks[s])
            info = Gtk.Label(xalign=0, wrap=True)
            info.add_css_class("caption")
            reset = Gtk.Button(label=_("Zerar circularidade"), halign=Gtk.Align.START)
            reset.add_css_class("flat")
            reset.connect("clicked", lambda _b, s=side: (self.tester.sticks[s].reset_circle(), self.stick_views[s].queue_draw()))
            for w in (title, view, info, reset):
                col.append(w)
            box.append(col)
            self.stick_views[side], self.stick_labels[side] = view, info
        sticks.add(box)

        triggers = self._group(_("Gatilhos"))
        self.trigger_bars, self.trigger_labels = {}, {}
        for side in ("l2", "r2"):
            bar = Gtk.LevelBar(min_value=0, max_value=255, width_request=160, valign=Gtk.Align.CENTER)
            row = Adw.ActionRow(title=side.upper())
            row.add_suffix(bar)
            triggers.add(row)
            self.trigger_bars[side], self.trigger_labels[side] = bar, row

        touch = self._group("Touchpad")
        self.touch_view = TouchView()
        self.touch_view.set_halign(Gtk.Align.CENTER)
        touch.add(self.touch_view)
        self.touch_label = Gtk.Label(xalign=0.5)
        self.touch_label.add_css_class("caption")
        touch.add(self.touch_label)

        motion = self._group(_("Movimento"))
        self.gyro_row = Adw.ActionRow(title=_("Giroscópio"), subtitle=_("graus por segundo"))
        self.accel_row = Adw.ActionRow(title=_("Acelerômetro"), subtitle=_("em g"))
        self.gyro_value = Gtk.Label()
        self.accel_value = Gtk.Label()
        for row, value in ((self.gyro_row, self.gyro_value), (self.accel_row, self.accel_value)):
            value.add_css_class("mono")
            row.add_suffix(value)
            motion.add(row)

        vib = self._group(_("Vibração"))
        self.motor = {}
        for key, title in (("left", _("Motor esquerdo (forte)")), ("right", _("Motor direito (fraco)"))):
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 255, 1)
            scale.set_value(180)
            scale.set_hexpand(True)
            scale.set_size_request(180, -1)
            row = Adw.ActionRow(title=title)
            row.add_suffix(scale)
            vib.add(row)
            self.motor[key] = scale
        pulses = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=8)
        for label, which in ((_("Esquerdo"), "left"), (_("Direito"), "right"), (_("Os dois"), "both")):
            b = Gtk.Button(label=label)
            b.connect("clicked", self._pulse, which)
            pulses.append(b)
        vib.add(pulses)

        self.audio_group = self._group(_("Áudio"), _("Funciona com o controle no cabo USB."))
        self.speaker_btn = Gtk.Button(label=_("Tocar no alto-falante"))
        self.speaker_btn.connect("clicked", self._tone, audio.SPEAKER)
        self.phone_btn = Gtk.Button(label=_("Tocar no fone"))
        self.phone_btn.connect("clicked", self._tone, audio.HEADPHONES)
        tones = Gtk.Box(spacing=8)
        tones.append(self.speaker_btn)
        tones.append(self.phone_btn)
        self.audio_group.add(tones)
        self.mic_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.mic_switch.connect("notify::active", self._mic_toggled)
        self.mic_bar = Gtk.LevelBar(min_value=0, max_value=1, width_request=120, valign=Gtk.Align.CENTER)
        mic_row = Adw.ActionRow(title=_("Microfone"), subtitle=_("Fale perto do controle"))
        mic_row.add_suffix(self.mic_bar)
        mic_row.add_suffix(self.mic_switch)
        self.audio_group.add(mic_row)
        self.phone_row = Adw.ActionRow(title=_("Fone conectado"))
        self.phone_state = Gtk.Label(label=_("não"))
        self.phone_row.add_suffix(self.phone_state)
        self.audio_group.add(self.phone_row)
        self._refresh_static()

    def _refresh_static(self):
        for key, chip in self.chips.items():
            if key in self.tester.tested:
                chip.add_css_class("chip-done")
            else:
                chip.remove_css_class("chip-done")
        self.buttons_group.set_description(
            _("{testados} de {total} testados. Cada botão fica verde depois de apertado uma vez.").format(
                testados=len(self.tester.tested), total=len(BUTTONS)))

    def update(self, data):
        if self.tester.record(data):
            self._refresh_static()
        for key, chip in self.chips.items():
            if data["buttons"].get(key):
                chip.add_css_class("chip-on")
            else:
                chip.remove_css_class("chip-on")
        for side in ("l", "r"):
            st = self.tester.sticks[side]
            coverage, error = st.circularity()
            rest = _("repouso {valor}%").format(valor=_fmt(st.rest * 100)) if st.rest is not None else _("medindo repouso")
            circ = (_("circularidade {valor}% de erro").format(valor=_fmt(error * 100)) if error is not None
                    else _("gire para medir"))
            drift = _(DRIFT_TEXT.get(st.drift(), N_("medindo drift")))
            contorno = _("contorno {valor}%").format(valor=f"{coverage * 100:.0f}")
            self.stick_labels[side].set_label(f"X {st.raw[0]}  Y {st.raw[1]}\n{rest} · {drift}\n{circ} · {contorno}")
            self.stick_views[side].queue_draw()
        for side in ("l2", "r2"):
            value, best = data["triggers"][side], self.tester.max[side]
            self.trigger_bars[side].set_value(value)
            self.trigger_labels[side].set_subtitle(
                _("agora {valor} · máximo {maximo}").format(valor=value, maximo=best)
                + (_(" · curso completo") if best >= 255 else ""))
        self.touch_view.touch = data["touch"]
        self.touch_view.click = data["buttons"].get("touchpad", False)
        self.touch_view.queue_draw()
        active = sum(1 for t in data["touch"] if t["active"])
        self.touch_label.set_label(_("{ativos} dedo(s) agora · até {vistos} visto(s) · clique {clique}").format(
            ativos=active, vistos=self.tester.touch_seen, clique="ok" if self.tester.click_seen else _("não testado")))
        self.gyro_value.set_label("  ".join(f"{v:+7.1f}" for v in data["gyro"]))
        self.accel_value.set_label("  ".join(f"{v:+6.2f}" for v in data["accel"]))
        self.phone_state.set_label(_("sim") if data.get("headphones") else _("não"))
        self.hz_label.set_label(f"{self.session.report_hz} Hz")

    def refresh_mode(self):
        ses = self.session
        paused = ses.charging_mode and ses.connection == "usb-detached"
        self.widget.set_visible_child_name("pausado" if paused else "ativo")
        usb = ses.connection == "usb" and not ses.charging_mode
        self.audio_group.set_sensitive(usb)
        if not usb:
            self.stop_mic()

    def _restart(self, _b):
        self.tester.reset()
        self._refresh_static()
        for v in self.stick_views.values():
            v.queue_draw()
        self.win.toast(_("Teste recomeçado"))

    def _pulse(self, _b, which):
        left = self.motor["left"].get_value() if which in ("left", "both") else 0
        right = self.motor["right"].get_value() if which in ("right", "both") else 0
        self.session.rumble(left, right, 600)
        self.tester.vibration_done = True

    def _tone(self, _b, target):
        if audio.play_tone(target):
            if target == audio.SPEAKER:
                self.tester.speaker_done = True
            else:
                self.tester.headphone_done = True
        else:
            self.win.toast(_("Áudio do controle não encontrado"))

    def _mic_toggled(self, switch, _pspec):
        if switch.get_active() and not self.mic:
            self.mic = audio.MicMeter(self._mic_level)
            if not self.mic.start():
                self.mic = None
                switch.set_active(False)
                self.win.toast(_("Microfone do controle não encontrado"))
        elif not switch.get_active():
            self.stop_mic()

    def _mic_level(self, level):
        self.mic_bar.set_value(level)
        self.tester.mic_peak = max(self.tester.mic_peak, level)

    def stop_mic(self):
        if self.mic:
            self.mic.stop()
            self.mic = None
        if self.mic_switch.get_active():
            self.mic_switch.set_active(False)
        self.mic_bar.set_value(0)

    def _report(self, _b):
        ses = self.session
        pct, status = ses.battery_pct, ses.battery_status
        battery = (f"{pct}%, {_(STATUS_PT.get(status, status or ''))}".rstrip(", ") if pct is not None
                   else _("indisponível"))
        text = self.tester.report(ses.info, battery, ses.report_hz)
        dialog = Gtk.FileChooserNative.new(_("Salvar relatório"), self.win, Gtk.FileChooserAction.SAVE,
                                           _("Salvar"), _("Cancelar"))
        dialog.set_current_name(f"relatorio-dualsense-{GLib.DateTime.new_now_local().format('%Y%m%d-%H%M')}.md")

        def done(d, response):
            if response == Gtk.ResponseType.ACCEPT:
                path = d.get_file().get_path()
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(text)
                    self.win.toast(_("Relatório salvo em {caminho}").format(caminho=path))
                except OSError as e:
                    self.win.toast(_("Não consegui salvar: {erro}").format(erro=e.strerror))
            d.destroy()
        dialog.connect("response", done)
        dialog.show()
        self._dialog = dialog
