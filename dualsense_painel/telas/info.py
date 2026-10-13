import math

from gi.repository import Adw, Gdk, Gtk

FIELDS = (
    ("model", "Modelo"), ("color", "Cor de fábrica"), ("board", "Placa (BDM)"), ("serial", "Número de série"),
    ("firmware", "Firmware"), ("hardware", "Hardware"), ("update", "Versão de atualização"),
    ("build", "Data do firmware"), ("mac", "Endereço MAC"), ("connection", "Conexão"),
    ("hz", "Taxa de atualização"), ("battery", "Bateria"),
)
CONNECTION = {"usb": "Cabo USB", "bluetooth": "Bluetooth", "usb-detached": "Cabo USB, no modo carregar"}
STATUS = {"Charging": "carregando", "Discharging": "na bateria", "Full": "carga completa"}


class Swatch(Gtk.DrawingArea):
    def __init__(self):
        super().__init__(content_width=16, content_height=16, valign=Gtk.Align.CENTER)
        self.rgba = None
        self.set_draw_func(self._draw)

    def _draw(self, _a, cr, w, h):
        if not self.rgba:
            return
        cr.arc(w / 2, h / 2, min(w, h) / 2 - 1, 0, 2 * math.pi)
        cr.set_source_rgba(self.rgba.red, self.rgba.green, self.rgba.blue, 1)
        cr.fill_preserve()
        cr.set_source_rgba(0.5, 0.5, 0.5, 0.6)
        cr.set_line_width(1)
        cr.stroke()


class InfoPage:
    def __init__(self, window):
        self.win = window
        self.session = window.session
        self.widget = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title="Informações do controle",
                                     description="Cor, placa e número de série são lidos pelo cabo USB e "
                                                 "ficam guardados para aparecer também no Bluetooth.")
        self.widget.add(group)
        self.rows, self.values = {}, {}
        for key, title in FIELDS:
            row = Adw.ActionRow(title=title, subtitle="Indisponível")
            if key == "color":
                self.swatch = Swatch()
                row.add_prefix(self.swatch)
            copy = Gtk.Button(icon_name="edit-copy-symbolic", valign=Gtk.Align.CENTER, tooltip_text="Copiar")
            copy.add_css_class("flat")
            copy.connect("clicked", self._copy, key)
            row.add_suffix(copy)
            group.add(row)
            self.rows[key] = row

    def _value(self, key):
        ses, info = self.session, self.session.info or {}
        if key == "connection":
            return CONNECTION.get(ses.connection)
        if key == "hz":
            return f"{ses.report_hz} Hz" if ses.report_hz else None
        if key == "battery":
            if ses.battery_pct is None:
                return None
            return f"{ses.battery_pct}%, {STATUS.get(ses.battery_status, '')}".rstrip(", ")
        if key == "model":
            return info.get("model") or ses.model
        if key == "color":
            if info.get("colorPt"):
                english = info.get("color")
                return info["colorPt"] + (f" ({english})" if english and english != info["colorPt"] else "")
            return f"Código {info['colorCode']}" if info.get("colorCode") else None
        value = info.get(key)
        return str(value) if value else None

    def refresh(self):
        for key, row in self.rows.items():
            value = self._value(key)
            self.values[key] = value
            row.set_subtitle(value or "Indisponível")
        hex_color = (self.session.info or {}).get("colorHex")
        rgba = Gdk.RGBA()
        self.swatch.rgba = rgba if hex_color and rgba.parse(hex_color) else None
        self.swatch.queue_draw()

    def _copy(self, _b, key):
        value = self.values.get(key)
        if value:
            self.win.get_clipboard().set(value)
            self.win.toast("Copiado")
