import os

from gi.repository import Adw, Gtk

from .. import segundo_plano
from ..idioma import IDIOMAS, _
from ..versao import VERSAO
from .historico import BatteryChart, duration

LOW_BATTERY = (0, 10, 15, 20, 25, 30)
IDLE_OFF = (0, 5, 10, 15, 30)
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class HistoricoGroup:
    def __init__(self, session):
        self.session = session
        self.widget = Adw.PreferencesGroup(title=_("Histórico da bateria"), description=_("Últimas 48 horas."))
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
            self.estimate.set_label(_("Cheio em {tempo}, no ritmo atual.").format(tempo=duration(est["minutes"])))
        elif est and est["kind"] == "empty":
            self.estimate.set_label(_("Acaba em {tempo}, no ritmo atual.").format(tempo=duration(est["minutes"])))
        else:
            self.estimate.set_label(_("A estimativa aparece depois de alguns minutos de carga ou uso."))


class AjustesGroup:
    def __init__(self, window):
        self.win = window
        cfg = window.cfg
        self.widget = Adw.PreferencesGroup(title=_("Ajustes"))

        shortcut = Adw.ActionRow(title=_("Atalho no controle"),
                                 subtitle=_("Segurar PS + Options por 2 s liga ou desliga o modo carregar"))
        sw = Gtk.Switch(valign=Gtk.Align.CENTER, active=cfg["shortcut"])
        sw.connect("notify::active", self._set, "shortcut", lambda w: w.get_active())
        shortcut.add_suffix(sw)
        shortcut.set_activatable_widget(sw)
        self.widget.add(shortcut)

        low = Adw.ComboRow(title=_("Aviso de bateria baixa"),
                           model=Gtk.StringList.new([_("Desligado")] + [f"{v}%" for v in LOW_BATTERY[1:]]))
        low.set_selected(LOW_BATTERY.index(cfg["low_battery"]) if cfg["low_battery"] in LOW_BATTERY else 0)
        low.connect("notify::selected", self._set, "low_battery", lambda w: LOW_BATTERY[w.get_selected()])
        self.widget.add(low)

        idle = Adw.ComboRow(title=_("Desligar sozinho no Bluetooth"),
                            subtitle=_("Depois de um tempo sem mexer no controle"),
                            model=Gtk.StringList.new([_("Nunca")] + [f"{v} min" for v in IDLE_OFF[1:]]))
        idle.set_selected(IDLE_OFF.index(cfg["idle_off"]) if cfg["idle_off"] in IDLE_OFF else 0)
        idle.connect("notify::selected", self._set, "idle_off", lambda w: IDLE_OFF[w.get_selected()])
        self.widget.add(idle)

        self.off_row = Adw.ActionRow(title=_("Desligar controle"), subtitle=_("Desconecta do Bluetooth e desliga"))
        off = Gtk.Button(label=_("Desligar"), valign=Gtk.Align.CENTER)
        off.add_css_class("destructive-action")
        off.connect("clicked", lambda *_: self.win.session.disconnect_bluetooth())
        self.off_row.add_suffix(off)
        self.off_row.set_visible(False)
        self.widget.add(self.off_row)

        fundo = Adw.ActionRow(title=_("Continuar rodando ao fechar a janela"),
                              subtitle=_("Modo carregar automático, avisos de bateria e atalho seguem funcionando"))
        fundo_sw = Gtk.Switch(valign=Gtk.Align.CENTER, active=cfg["segundo_plano"])
        fundo_sw.connect("notify::active", self._set, "segundo_plano", lambda w: w.get_active())
        fundo.add_suffix(fundo_sw)
        fundo.set_activatable_widget(fundo_sw)
        self.widget.add(fundo)

        inicio = Adw.ActionRow(title=_("Iniciar com o sistema"), subtitle=_("Abre escondido ao entrar na sua conta"))
        self.inicio_sw = Gtk.Switch(valign=Gtk.Align.CENTER, active=segundo_plano.ativo("dualsense-painel"))
        self.inicio_sw.connect("notify::active", self._iniciar_com_sistema)
        inicio.add_suffix(self.inicio_sw)
        inicio.set_activatable_widget(self.inicio_sw)
        self.widget.add(inicio)

        lingua = Adw.ComboRow(title=_("Idioma"), model=Gtk.StringList.new([_("Automático"), "Português", "English"]))
        lingua.set_selected(IDIOMAS.index(cfg["idioma"]) if cfg["idioma"] in IDIOMAS else 0)
        lingua.connect("notify::selected", self._set, "idioma", lambda w: IDIOMAS[w.get_selected()])
        lingua.connect("notify::selected", self._idioma_mudou)
        self.widget.add(lingua)

        sair = Adw.ActionRow(title=_("Sair do app"), subtitle=_("Fecha de vez, inclusive em segundo plano"))
        sair_botao = Gtk.Button(label=_("Sair"), valign=Gtk.Align.CENTER)
        sair_botao.connect("clicked", lambda *_: self.win.get_application().quit())
        sair.add_suffix(sair_botao)
        self.widget.add(sair)

        versao = Adw.ActionRow(title=_("Versão do app"), subtitle=VERSAO if VERSAO != "0.0.0" else _("Rodando pelo código"))
        procurar = Gtk.Button(label=_("Procurar atualizações"), valign=Gtk.Align.CENTER)
        procurar.connect("clicked", lambda *_: self.win.get_application().procurar_versao())
        versao.add_suffix(procurar)
        self.widget.add(versao)

    def _iniciar_com_sistema(self, widget, _pspec):
        try:
            segundo_plano.definir("dualsense-painel", widget.get_active(), RAIZ)
        except OSError as e:
            self.win.toast(_("Não consegui mudar: {erro}").format(erro=e.strerror))

    def _idioma_mudou(self, _widget, _pspec):
        if getattr(self, "_aviso_idioma", None):
            self._aviso_idioma.dismiss()
        self._aviso_idioma = Adw.Toast(title=_("O idioma muda quando o app abrir de novo"), timeout=0)
        self._aviso_idioma.set_button_label(_("Reiniciar agora"))
        self._aviso_idioma.connect("button-clicked", self._reiniciar)
        self.win.toasts.add_toast(self._aviso_idioma)

    def _reiniciar(self, _toast):
        self.win.session.flush_save()
        segundo_plano.reiniciar("dualsense_painel", RAIZ)
        self.win.get_application().quit()

    def _set(self, widget, _pspec, key, getter):
        self.win.cfg[key] = getter(widget)
        self.win.changed()

    def refresh(self):
        self.off_row.set_visible(self.win.session.connection == "bluetooth" and self.win.session.pode_desligar_bluetooth)
