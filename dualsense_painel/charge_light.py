import math

from .idioma import N_

STYLES = ("breathe", "solid", "blink")
STYLE_LABELS = (N_("Respirar"), N_("Fixa"), N_("Piscar"))
FULL_ACTIONS = ("off", "green", "keep")
FULL_LABELS = (N_("Apagar"), N_("Ficar verde"), N_("Continuar igual"))
FULL_GREEN = (0, 255, 40)

DEFAULTS = {
    "charge_glow": True,
    "charge_color": [255, 80, 0],
    "charge_style": "breathe",
    "charge_period": 5.0,
    "charge_intensity": 100,
    "charge_full": "green",
}


def _scale(rgb, level):
    return tuple(max(0, min(255, round(c * level))) for c in rgb)


def _wave(style, period, t):
    if style == "solid":
        return 1.0
    phase = (t % period) / period
    if style == "blink":
        return 1.0 if phase < 0.5 else 0.0
    return 0.06 + 0.94 * (0.5 - 0.5 * math.cos(2 * math.pi * phase))


def lightbar(cfg, status, t):
    if not cfg.get("charge_glow", True):
        return (0, 0, 0)
    intensity = max(0, min(100, cfg.get("charge_intensity", 100))) / 100
    period = max(0.5, float(cfg.get("charge_period", 5.0)))
    style = cfg.get("charge_style", "breathe")
    color = cfg.get("charge_color", DEFAULTS["charge_color"])
    if status == "Full":
        action = cfg.get("charge_full", "off")
        if action == "off":
            return (0, 0, 0)
        if action == "green":
            return _scale(FULL_GREEN, intensity)
    elif status != "Charging":
        return (0, 0, 0)
    return _scale(color, intensity * _wave(style, period, t))


def animated(cfg, status):
    if not cfg.get("charge_glow", True) or cfg.get("charge_style") == "solid":
        return False
    if status == "Charging":
        return True
    return status == "Full" and cfg.get("charge_full") == "keep"
