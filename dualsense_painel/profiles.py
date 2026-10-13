import copy

KEYS = ("color", "intensity", "lightbar_mode", "player_leds", "led_brightness", "mic_led", "triggers")
MAX_NAME = 32
MAX_PROFILES = 24


def clean_name(name):
    return " ".join(str(name or "").split())[:MAX_NAME]


def save(cfg, name):
    name = clean_name(name)
    if not name:
        return None
    profiles = cfg.setdefault("profiles", {})
    if name not in profiles and len(profiles) >= MAX_PROFILES:
        return None
    profiles[name] = {k: copy.deepcopy(cfg[k]) for k in KEYS}
    return name


def apply(cfg, name):
    profile = cfg.get("profiles", {}).get(name)
    if not profile:
        return False
    for k in KEYS:
        if k in profile:
            cfg[k] = copy.deepcopy(profile[k])
    return True


def delete(cfg, name):
    return cfg.get("profiles", {}).pop(name, None) is not None


def summary(cfg):
    return [{"name": n, "color": list(p.get("color", [0, 0, 0])),
             "triggers": {s: p.get("triggers", {}).get(s, {}).get("mode", "off") for s in ("l2", "r2")}}
            for n, p in sorted(cfg.get("profiles", {}).items(), key=lambda kv: kv[0].lower())]
