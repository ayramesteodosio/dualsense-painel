from gi.repository import Adw, Gtk

from .historico import BatteryChart, duration

LOW_BATTERY = (0, 10, 15, 20, 25, 30)
IDLE_OFF = (0, 5, 10, 15, 30)


class HistoricoGroup:
    def __init__(self, session):
        self.session = session
        self.widget = Adw.PreferencesGroup(title="Histórico da bateria", description="Últimas 48 horas.")
        self.chart = BatteryChart()
        self.chart.set_margin_top(6)
        self.widget.add(self.chart)
        self.estimate = Gtk.Label(xalign=0, margin_top=6)
        self.estimate.add_css_class("caption")
        self.widget.add(self.estimate)

    def refresh(self):
        h = self.session.history
        self.chart.set_points(h.as_list())
        est = h.estimate()
        if est and est["kind"] == "full":
            self.estimate.set_label(f"Cheio em {duration(est['minutes'])}, no ritmo atual.")
        elif est and est["kind"] == "empty":
            self.estimate.set_label(f"Acaba em {duration(est['minutes'])}, no ritmo atual.")
        else:
            self.estimate.set_label("A estimativa aparece depois de alguns minutos de carga ou uso.")


class AjustesGroup:
    def __init__(self, window):
        self.win = window
        cfg = window.cfg
        self.widget = Adw.PreferencesGroup(title="Ajustes")

        shortcut = Adw.ActionRow(title="Atalho no controle",
                                 subtitle="Segurar PS + Options por 2 s liga ou desliga o modo carregar")
        sw = Gtk.Switch(valign=Gtk.Align.CENTER, active=cfg["shortcut"])
        sw.connect("notify::active", self._set, "shortcut", lambda w: w.get_active())
        shortcut.add_suffix(sw)
        shortcut.set_activatable_widget(sw)
        self.widget.add(shortcut)

        low = Adw.ComboRow(title="Aviso de bateria baixa",
                           model=Gtk.StringList.new(["Desligado"] + [f"{v}%" for v in LOW_BATTERY[1:]]))
        low.set_selected(LOW_BATTERY.index(cfg["low_battery"]) if cfg["low_battery"] in LOW_BATTERY else 0)
        low.connect("notify::selected", self._set, "low_battery", lambda w: LOW_BATTERY[w.get_selected()])
        self.widget.add(low)

        idle = Adw.ComboRow(title="Desligar sozinho no Bluetooth",
                            subtitle="Depois de um tempo sem mexer no controle",
                            model=Gtk.StringList.new(["Nunca"] + [f"{v} min" for v in IDLE_OFF[1:]]))
        idle.set_selected(IDLE_OFF.index(cfg["idle_off"]) if cfg["idle_off"] in IDLE_OFF else 0)
        idle.connect("notify::selected", self._set, "idle_off", lambda w: IDLE_OFF[w.get_selected()])
        self.widget.add(idle)

        self.off_row = Adw.ActionRow(title="Desligar controle", subtitle="Desconecta do Bluetooth e desliga")
        off = Gtk.Button(label="Desligar", valign=Gtk.Align.CENTER)
        off.add_css_class("destructive-action")
        off.connect("clicked", lambda *_: self.win.session.disconnect_bluetooth())
        self.off_row.add_suffix(off)
        self.off_row.set_visible(False)
        self.widget.add(self.off_row)

    def _set(self, widget, _pspec, key, getter):
        self.win.cfg[key] = getter(widget)
        self.win.changed()

    def refresh(self):
        self.off_row.set_visible(self.win.session.connection == "bluetooth")
