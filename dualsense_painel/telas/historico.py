import math
import time

from gi.repository import Gtk

from ..idioma import _

HOURS = 48


def duration(minutes):
    minutes = max(1, round(minutes))
    if minutes < 60:
        return f"~{minutes} min"
    h, m = divmod(minutes, 60)
    return f"~{h} h {m} min" if m >= 10 else f"~{h} h"


class BatteryChart(Gtk.DrawingArea):
    def __init__(self):
        super().__init__(content_height=130, hexpand=True)
        self.points = []
        self.set_draw_func(self._draw)

    def set_points(self, points):
        self.points = points
        self.queue_draw()

    def _draw(self, _a, cr, w, h):
        fg = self.get_style_context().get_color()
        ok, accent = self.get_style_context().lookup_color("accent_bg_color")
        ar, ag, ab = (accent.red, accent.green, accent.blue) if ok else (0.21, 0.52, 0.89)
        pad = 4
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.12)
        cr.set_line_width(1)
        for frac in (0, 0.5, 1):
            y = pad + (h - 2 * pad) * frac
            cr.move_to(0, y)
            cr.line_to(w, y)
        cr.stroke()
        now = time.time() * 1000
        start = now - HOURS * 3600 * 1000
        pts = [p for p in self.points if p[0] >= start]
        if len(pts) < 2:
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.5)
            cr.set_font_size(12)
            cr.move_to(pad + 4, h / 2)
            cr.show_text(_("O histórico aparece depois de alguns minutos com o controle ligado."))
            return
        x = lambda t: pad + (t - start) / (now - start) * (w - 2 * pad)
        y = lambda p: pad + (1 - p / 100) * (h - 2 * pad)
        for a, b in zip(pts, pts[1:]):
            if a[2] == "Charging":
                cr.set_source_rgba(ar, ag, ab, 0.08)
                cr.rectangle(x(a[0]), pad, max(1, x(b[0]) - x(a[0])), h - 2 * pad)
                cr.fill()
        cr.move_to(x(pts[0][0]), y(pts[0][1]))
        for t, p, _s in pts[1:]:
            cr.line_to(x(t), y(p))
        cr.line_to(x(now), y(pts[-1][1]))
        cr.set_source_rgb(ar, ag, ab)
        cr.set_line_width(2)
        cr.stroke_preserve()
        cr.line_to(x(now), h - pad)
        cr.line_to(x(pts[0][0]), h - pad)
        cr.close_path()
        cr.set_source_rgba(ar, ag, ab, 0.15)
        cr.fill()
