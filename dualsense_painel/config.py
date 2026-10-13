import json
import os

from . import charge_light, plataforma
from .protocol import MODES_BY_KEY

PATH = os.path.join(plataforma.config_dir(), "config.json")

DEFAULTS = {
    "color": [0, 90, 255],
    "intensity": 100,
    "player_leds": 0b00100,
    "led_brightness": 0,
    "mic_led": 0,
    "auto_charge": False,
    "lightbar_mode": "fixed",
    "shortcut": True,
    "low_battery": 20,
    "idle_off": 0,
    "segundo_plano": True,
    "idioma": "auto",
    "profiles": {},
    **charge_light.DEFAULTS,
    "triggers": {"l2": {"mode": "off", "params": {}}, "r2": {"mode": "off", "params": {}}},
    "versao_config": 2,
}


def load(path=PATH):
    data = json.loads(json.dumps(DEFAULTS))
    try:
        with open(path) as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return data
    for key in DEFAULTS:
        if key in saved:
            data[key] = saved[key]
    if data["charge_style"] not in charge_light.STYLES:
        data["charge_style"] = charge_light.DEFAULTS["charge_style"]
    if saved.get("versao_config", 1) < 2:
        if data["charge_full"] == "off":
            data["charge_full"] = "green"
        data["versao_config"] = 2
    if data["charge_full"] not in charge_light.FULL_ACTIONS:
        data["charge_full"] = charge_light.DEFAULTS["charge_full"]
    if data["lightbar_mode"] not in ("fixed", "battery"):
        data["lightbar_mode"] = "fixed"
    if not isinstance(data["profiles"], dict):
        data["profiles"] = {}
    for side in ("l2", "r2"):
        trig = data["triggers"].get(side) or {}
        if trig.get("mode") not in MODES_BY_KEY:
            data["triggers"][side] = {"mode": "off", "params": {}}
    return data


def save(data, path=PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
