import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import (QColorDialog, QGroupBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSlider,
                               QVBoxLayout, QWidget)


def accent(widget):
    palette = widget.palette()
    return QColor(palette.color(QPalette.Highlight))


def foreground(widget):
    palette = widget.palette()
    return QColor(palette.color(QPalette.WindowText))


def section(title, description=None):
    box = QGroupBox(title)
    layout = QVBoxLayout(box)
    layout.setSpacing(8)
    if description:
        label = QLabel(description)
        label.setWordWrap(True)
        label.setStyleSheet("color: palette(placeholder-text);")
        layout.addWidget(label)
    return box, layout


def row(title, widget, subtitle=None):
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    texts = QVBoxLayout()
    texts.setSpacing(0)
    t = QLabel(title)
    texts.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setWordWrap(True)
        s.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")
        texts.addWidget(s)
    h.addLayout(texts, 1)
    h.addWidget(widget)
    return w


class ValueSlider(QWidget):
    changed = Signal(float)

    def __init__(self, low, high, value, fmt=lambda v: f"{v:.0f}", step=1.0):
        super().__init__()
        self.step = step
        self.fmt = fmt
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(round(low / step), round(high / step))
        self.slider.setValue(round(value / step))
        self.slider.setMinimumWidth(180)
        self.label = QLabel()
        self.label.setMinimumWidth(52)
        self.label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.slider, 1)
        h.addWidget(self.label)
        self.slider.valueChanged.connect(self._moved)
        self._update_label()

    def value(self):
        return self.slider.value() * self.step

    def set_value(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(round(value / self.step))
        self.slider.blockSignals(False)
        self._update_label()

    def _update_label(self):
        self.label.setText(self.fmt(self.value()))

    def _moved(self, _v):
        self._update_label()
        self.changed.emit(self.value())


class ColorButton(QPushButton):
    color_changed = Signal(list)

    def __init__(self, rgb, title="Escolher cor"):
        super().__init__()
        self.title = title
        self.setFixedSize(44, 28)
        self.set_rgb(rgb)
        self.clicked.connect(self._pick)

    def set_rgb(self, rgb):
        self.rgb = list(rgb)
        r, g, b = self.rgb
        self.setStyleSheet(f"ColorButton {{ background: rgb({r},{g},{b}); border: 1px solid rgba(128,128,128,.6); "
                           "border-radius: 6px; }")

    def _pick(self):
        color = QColorDialog.getColor(QColor(*self.rgb), self.window(), self.title)
        if color.isValid():
            self.set_rgb([color.red(), color.green(), color.blue()])
            self.color_changed.emit(self.rgb)


class Swatch(QPushButton):
    def __init__(self, rgb, tip):
        super().__init__()
        self.rgb = rgb
        self.setToolTip(tip)
        self.setFixedSize(26, 26)
        r, g, b = rgb
        self.setStyleSheet(f"Swatch {{ background: rgb({r},{g},{b}); border-radius: 13px; "
                           "border: 1px solid rgba(128,128,128,.5); }")


class Chip(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(28)
        self.set_state(False, False)

    def set_state(self, done, on):
        if on:
            css = "background: palette(highlight); color: palette(highlighted-text);"
        elif done:
            css = "background: rgba(46,194,126,.30);"
        else:
            css = "background: rgba(128,128,128,.14);"
        self.setStyleSheet("Chip { " + css + " border-radius: 14px; padding: 4px 8px; }")


class BatteryChart(QWidget):
    HOURS = 48

    def __init__(self):
        super().__init__()
        self.points = []
        self.setMinimumHeight(130)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_points(self, points):
        self.points = points
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h, pad = self.width(), self.height(), 4
        fg = foreground(self)
        ac = accent(self)
        grid = QColor(fg)
        grid.setAlphaF(0.12)
        p.setPen(QPen(grid, 1))
        for frac in (0, 0.5, 1):
            y = pad + (h - 2 * pad) * frac
            p.drawLine(0, int(y), w, int(y))
        now = time.time() * 1000
        start = now - self.HOURS * 3600 * 1000
        pts = [x for x in self.points if x[0] >= start]
        if len(pts) < 2:
            muted = QColor(fg)
            muted.setAlphaF(0.55)
            p.setPen(muted)
            p.drawText(self.rect(), Qt.AlignCenter, "O histórico aparece depois de alguns minutos com o controle ligado.")
            return
        x = lambda t: pad + (t - start) / (now - start) * (w - 2 * pad)
        y = lambda v: pad + (1 - v / 100) * (h - 2 * pad)
        band = QColor(ac)
        band.setAlphaF(0.08)
        for a, b in zip(pts, pts[1:]):
            if a[2] == "Charging":
                p.fillRect(QRectF(x(a[0]), pad, max(1, x(b[0]) - x(a[0])), h - 2 * pad), band)
        path = QPainterPath(QPointF(x(pts[0][0]), y(pts[0][1])))
        for t, v, _s in pts[1:]:
            path.lineTo(x(t), y(v))
        path.lineTo(x(now), y(pts[-1][1]))
        p.setPen(QPen(ac, 2))
        p.drawPath(path)
        fill = QPainterPath(path)
        fill.lineTo(x(now), h - pad)
        fill.lineTo(x(pts[0][0]), h - pad)
        fill.closeSubpath()
        area = QColor(ac)
        area.setAlphaF(0.15)
        p.fillPath(fill, area)


class StickView(QWidget):
    def __init__(self, getter):
        super().__init__()
        self.getter = getter
        self.setFixedSize(160, 160)

    def paintEvent(self, _e):
        st = self.getter()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r = min(w, h) / 2 - 6
        c = QPointF(w / 2, h / 2)
        fg = foreground(self)
        ac = accent(self)
        bg = QColor(fg)
        bg.setAlphaF(0.06)
        p.setBrush(bg)
        line = QColor(fg)
        line.setAlphaF(0.25)
        p.setPen(QPen(line, 1))
        p.drawEllipse(c, r, r)
        p.drawLine(QPointF(c.x() - r, c.y()), QPointF(c.x() + r, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - r), QPointF(c.x(), c.y() + r))
        if any(st.bins):
            path = QPainterPath()
            for i, v in enumerate(st.bins):
                a = -math.pi + (i + 0.5) / len(st.bins) * 2 * math.pi
                pt = QPointF(c.x() + math.cos(a) * v * r, c.y() + math.sin(a) * v * r)
                path.lineTo(pt) if i else path.moveTo(pt)
            path.closeSubpath()
            fill = QColor(ac)
            fill.setAlphaF(0.18)
            p.fillPath(path, fill)
        p.setPen(Qt.NoPen)
        for i, (sx, sy) in enumerate(st.trail):
            dot = QColor(ac)
            dot.setAlphaF((i + 1) / len(st.trail) * 0.5)
            p.setBrush(dot)
            p.drawEllipse(QPointF(c.x() + sx * r, c.y() + sy * r), 2, 2)
        p.setBrush(ac)
        p.drawEllipse(QPointF(c.x() + st.x * r, c.y() + st.y * r), 6, 6)


class TouchView(QWidget):
    def __init__(self):
        super().__init__()
        self.touch = []
        self.click = False
        self.setFixedSize(288, 162)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        fg = foreground(self)
        ac = accent(self)
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        if self.click:
            fill = QColor(ac)
            fill.setAlphaF(0.22)
        else:
            fill = QColor(fg)
            fill.setAlphaF(0.07)
        line = QColor(fg)
        line.setAlphaF(0.25)
        p.setPen(QPen(line, 1))
        p.setBrush(fill)
        p.drawRoundedRect(rect, 12, 12)
        for t in self.touch:
            if not t["active"]:
                continue
            pt = QPointF(t["x"] / 1919 * rect.width(), t["y"] / 1079 * rect.height())
            dot = QColor(ac)
            dot.setAlphaF(0.85)
            p.setPen(Qt.NoPen)
            p.setBrush(dot)
            p.drawEllipse(pt, 11, 11)
            p.setPen(QColor("white"))
            p.drawText(QRectF(pt.x() - 11, pt.y() - 11, 22, 22), Qt.AlignCenter, str(t["id"] % 10))


class Dot(QWidget):
    def __init__(self, size=14):
        super().__init__()
        self.color = None
        self.setFixedSize(size, size)

    def set_color(self, color):
        self.color = QColor(color) if color else None
        self.update()

    def paintEvent(self, _e):
        if not self.color:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(self.color)
        p.setPen(QPen(QColor(128, 128, 128, 150), 1))
        p.drawEllipse(QRectF(1, 1, self.width() - 2, self.height() - 2))
