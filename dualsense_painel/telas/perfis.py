from gi.repository import Adw, Gtk

from .. import profiles
from ..idioma import _
from ..protocol import MODES_BY_KEY


class PerfisGroup:
    def __init__(self, window):
        self.win = window
        self.widget = Adw.PreferencesGroup(title=_("Perfis"),
                                           description=_("Guardam a luz, os LEDs e os gatilhos para trocar com um clique."))
        entry_box = Gtk.Box(spacing=8)
        self.entry = Gtk.Entry(placeholder_text=_("Nome do perfil, ex.: Corrida"), hexpand=True, max_length=32)
        self.entry.connect("activate", self._save)
        save = Gtk.Button(label=_("Salvar atual"))
        save.add_css_class("suggested-action")
        save.connect("clicked", self._save)
        entry_box.append(self.entry)
        entry_box.append(save)
        self.widget.add(entry_box)
        self.rows = []
        self.refresh()

    def refresh(self):
        for row in self.rows:
            self.widget.remove(row)
        self.rows = []
        for p in profiles.summary(self.win.cfg):
            modes = " · ".join(f"{side.upper()} {_(MODES_BY_KEY.get(mode, MODES_BY_KEY['off']).label).lower()}"
                               for side, mode in p["triggers"].items())
            row = Adw.ActionRow(title=p["name"], subtitle=modes)
            dot = Gtk.DrawingArea(content_width=14, content_height=14, valign=Gtk.Align.CENTER)
            r, g, b = (c / 255 for c in p["color"])
            dot.set_draw_func(lambda _a, cr, w, h, rgb=(r, g, b): (cr.arc(w / 2, h / 2, 6, 0, 6.2832),
                                                                   cr.set_source_rgb(*rgb), cr.fill()))
            row.add_prefix(dot)
            apply_btn = Gtk.Button(label=_("Aplicar"), valign=Gtk.Align.CENTER)
            apply_btn.connect("clicked", self._apply, p["name"])
            delete = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, tooltip_text=_("Apagar", "perfil"))
            delete.add_css_class("flat")
            delete.connect("clicked", self._delete, p["name"])
            row.add_suffix(apply_btn)
            row.add_suffix(delete)
            self.widget.add(row)
            self.rows.append(row)

    def _save(self, *_args):
        name = profiles.save(self.win.cfg, self.entry.get_text())
        if not name:
            self.win.toast(_("Dê um nome ao perfil"))
            return
        self.entry.set_text("")
        self.win.changed()
        self.refresh()
        self.win.toast(_("Perfil \"{nome}\" salvo").format(nome=name))

    def _apply(self, _b, name):
        if profiles.apply(self.win.cfg, name):
            self.win.sync_widgets()
            self.win.changed()
            self.win.toast(_("Perfil \"{nome}\" aplicado").format(nome=name))

    def _delete(self, _b, name):
        dialog = Gtk.MessageDialog(transient_for=self.win, modal=True, message_type=Gtk.MessageType.QUESTION,
                                   buttons=Gtk.ButtonsType.NONE, text=_("Apagar o perfil \"{nome}\"?").format(nome=name))
        dialog.add_button(_("Cancelar"), Gtk.ResponseType.CANCEL)
        dialog.add_button(_("Apagar", "perfil"), Gtk.ResponseType.ACCEPT).add_css_class("destructive-action")

        def done(d, response):
            if response == Gtk.ResponseType.ACCEPT and profiles.delete(self.win.cfg, name):
                self.win.changed()
                self.refresh()
            d.destroy()
        dialog.connect("response", done)
        dialog.present()
