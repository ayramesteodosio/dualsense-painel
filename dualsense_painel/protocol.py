import zlib
from dataclasses import dataclass, field

from .idioma import N_

USB_REPORT_ID = 0x02
USB_REPORT_SIZE = 63
BT_REPORT_ID = 0x31
BT_REPORT_SIZE = 78
COMMON_SIZE = 47

FLAG0_COMPATIBLE_VIBRATION = 0x01
FLAG0_HAPTICS_SELECT = 0x02
FLAG0_RIGHT_TRIGGER = 0x04
FLAG0_LEFT_TRIGGER = 0x08
FLAG1_MIC_LED = 0x01
FLAG1_LIGHTBAR = 0x04
FLAG1_PLAYER_LEDS = 0x10
FLAG2_LED_BRIGHTNESS = 0x01
FLAG2_LIGHTBAR_SETUP = 0x02
FLAG2_COMPATIBLE_VIBRATION2 = 0x04

PLAYER_LEDS_INSTANT = 0x20
LIGHTBAR_SETUP_LIGHT_OUT = 0x02

OFF_FLAG0 = 0
OFF_FLAG1 = 1
OFF_MOTOR_RIGHT = 2
OFF_MOTOR_LEFT = 3
OFF_MIC_LED = 8
OFF_RIGHT_TRIGGER = 10
OFF_LEFT_TRIGGER = 21
OFF_FLAG2 = 38
OFF_LIGHTBAR_SETUP = 41
OFF_LED_BRIGHTNESS = 42
OFF_PLAYER_LEDS = 43
OFF_LIGHTBAR = 44

TRIGGER_SIZE = 11


def _clamp(value, low, high):
    return max(low, min(high, int(value)))


def _zones(*positions):
    mask = 0
    for p in positions:
        mask |= 1 << p
    return mask


def _effect(mode, zones=0, *payload):
    data = bytearray(TRIGGER_SIZE)
    data[0] = mode
    data[1] = zones & 0xFF
    data[2] = (zones >> 8) & 0xFF
    for i, b in enumerate(payload):
        data[3 + i] = b & 0xFF
    return bytes(data)


def _per_zone(start, level):
    active = 0
    levels = 0
    for i in range(start, 10):
        active |= 1 << i
        levels |= (level & 0x07) << (3 * i)
    return active, levels.to_bytes(4, "little")


def effect_off():
    return _effect(0x05)


def effect_feedback(start, strength):
    start = _clamp(start, 0, 9)
    strength = _clamp(strength, 1, 8)
    active, levels = _per_zone(start, strength - 1)
    return _effect(0x21, active, *levels)


def effect_weapon(start, end, strength):
    start = _clamp(start, 2, 7)
    end = _clamp(end, start + 1, 8)
    strength = _clamp(strength, 1, 8)
    return _effect(0x25, _zones(start, end), strength - 1)


def effect_bow(start, end, strength, snap):
    start = _clamp(start, 0, 8)
    end = _clamp(end, start + 1, 8)
    pair = ((_clamp(strength, 1, 8) - 1) & 0x07) | (((_clamp(snap, 1, 8) - 1) & 0x07) << 3)
    return _effect(0x22, _zones(start, end), pair & 0xFF, pair >> 8)


def effect_vibration(start, amplitude, frequency):
    start = _clamp(start, 0, 9)
    amplitude = _clamp(amplitude, 1, 8)
    frequency = _clamp(frequency, 1, 255)
    active, levels = _per_zone(start, amplitude - 1)
    return _effect(0x26, active, *levels, 0, 0, frequency)


def effect_galloping(start, end, first_foot, second_foot, frequency):
    start = _clamp(start, 0, 8)
    end = _clamp(end, start + 1, 9)
    first_foot = _clamp(first_foot, 0, 6)
    second_foot = _clamp(second_foot, first_foot + 1, 7)
    timing = (second_foot & 0x07) | ((first_foot & 0x07) << 3)
    return _effect(0x23, _zones(start, end), timing, _clamp(frequency, 1, 255))


def effect_machine(start, end, amplitude_a, amplitude_b, frequency, period):
    start = _clamp(start, 0, 8)
    end = _clamp(end, start + 1, 9)
    pair = (_clamp(amplitude_a, 0, 7) & 0x07) | ((_clamp(amplitude_b, 0, 7) & 0x07) << 3)
    return _effect(0x27, _zones(start, end), pair, _clamp(frequency, 1, 255), _clamp(period, 0, 255))


@dataclass(frozen=True)
class Param:
    key: str
    label: str
    low: int
    high: int
    default: int
    position: bool = False


@dataclass(frozen=True)
class TriggerMode:
    key: str
    label: str
    description: str
    params: tuple
    encoder: object

    def encode(self, values):
        args = [values.get(p.key, p.default) for p in self.params]
        return self.encoder(*args)

    def defaults(self):
        return {p.key: p.default for p in self.params}


_START = lambda default, low=0, high=9: Param("start", N_("Começa em"), low, high, default, True)
_END = lambda default, low=1, high=9: Param("end", N_("Termina em"), low, high, default, True)

TRIGGER_MODES = (
    TriggerMode("off", N_("Livre"), N_("Sem efeito, o gatilho fica solto como de fábrica."), (), effect_off),
    TriggerMode(
        "feedback", N_("Resistência"), N_("Fica duro a partir de um ponto do curso até o fim."),
        (_START(2), Param("strength", N_("Força"), 1, 8, 6)), effect_feedback),
    TriggerMode(
        "weapon", N_("Gatilho de arma"), N_("Resistência num trecho que cede de uma vez, como um disparo."),
        (_START(3, 2, 7), _END(6, 3, 8), Param("strength", N_("Força"), 1, 8, 8)), effect_weapon),
    TriggerMode(
        "bow", N_("Arco"), N_("Puxa cada vez mais e dá um tranco ao soltar a corda."),
        (_START(1, 0, 8), _END(6, 1, 8), Param("strength", N_("Força"), 1, 8, 6),
         Param("snap", N_("Tranco"), 1, 8, 4)), effect_bow),
    TriggerMode(
        "vibration", N_("Vibração"), N_("O gatilho vibra a partir de um ponto do curso."),
        (_START(0), Param("amplitude", N_("Intensidade"), 1, 8, 6),
         Param("frequency", N_("Frequência (Hz)"), 1, 255, 40)), effect_vibration),
    TriggerMode(
        "galloping", N_("Galope"), N_("Dois toques ritmados, como um cavalo."),
        (_START(0, 0, 8), _END(9), Param("first_foot", N_("Primeiro toque"), 0, 6, 1),
         Param("second_foot", N_("Segundo toque"), 1, 7, 4), Param("frequency", N_("Ritmo"), 1, 255, 3)),
        effect_galloping),
    TriggerMode(
        "machine", N_("Máquina"), N_("Vibração que alterna entre duas intensidades."),
        (_START(0, 0, 8), _END(9), Param("amplitude_a", N_("Intensidade A"), 0, 7, 2),
         Param("amplitude_b", N_("Intensidade B"), 0, 7, 7), Param("frequency", N_("Frequência (Hz)"), 1, 255, 20),
         Param("period", N_("Período"), 0, 255, 5)), effect_machine),
)
MODES_BY_KEY = {m.key: m for m in TRIGGER_MODES}


@dataclass
class OutputState:
    lightbar: tuple = (0, 0, 255)
    player_leds: int = 0b00100
    led_brightness: int = 0
    mic_led: int = 0
    left_trigger: bytes = field(default_factory=effect_off)
    right_trigger: bytes = field(default_factory=effect_off)
    rumble: tuple = None


def dark_state():
    return OutputState(lightbar=(0, 0, 0), player_leds=0, mic_led=0, rumble=(0, 0))


def build_common(state, setup=False):
    data = bytearray(COMMON_SIZE)
    data[OFF_FLAG0] = FLAG0_RIGHT_TRIGGER | FLAG0_LEFT_TRIGGER
    data[OFF_FLAG1] = FLAG1_MIC_LED | FLAG1_LIGHTBAR | FLAG1_PLAYER_LEDS
    data[OFF_FLAG2] = FLAG2_LED_BRIGHTNESS
    if setup:
        data[OFF_FLAG2] |= FLAG2_LIGHTBAR_SETUP
        data[OFF_LIGHTBAR_SETUP] = LIGHTBAR_SETUP_LIGHT_OUT
    if state.rumble is not None:
        data[OFF_FLAG0] |= FLAG0_COMPATIBLE_VIBRATION | FLAG0_HAPTICS_SELECT
        data[OFF_FLAG2] |= FLAG2_COMPATIBLE_VIBRATION2
        data[OFF_MOTOR_RIGHT] = _clamp(state.rumble[1], 0, 255)
        data[OFF_MOTOR_LEFT] = _clamp(state.rumble[0], 0, 255)
    data[OFF_MIC_LED] = _clamp(state.mic_led, 0, 2)
    data[OFF_RIGHT_TRIGGER:OFF_RIGHT_TRIGGER + TRIGGER_SIZE] = state.right_trigger
    data[OFF_LEFT_TRIGGER:OFF_LEFT_TRIGGER + TRIGGER_SIZE] = state.left_trigger
    data[OFF_LED_BRIGHTNESS] = _clamp(state.led_brightness, 0, 2)
    data[OFF_PLAYER_LEDS] = (state.player_leds & 0x1F) | PLAYER_LEDS_INSTANT
    for i, c in enumerate(state.lightbar):
        data[OFF_LIGHTBAR + i] = _clamp(c, 0, 255)
    return data


def build_report(state, bluetooth=False, seq=0, setup=False):
    common = build_common(state, setup)
    if not bluetooth:
        report = bytearray(USB_REPORT_SIZE)
        report[0] = USB_REPORT_ID
        report[1:1 + COMMON_SIZE] = common
        return bytes(report)
    report = bytearray(BT_REPORT_SIZE)
    report[0] = BT_REPORT_ID
    report[1] = (seq & 0x0F) << 4
    report[2] = 0x10
    report[3:3 + COMMON_SIZE] = common
    crc = zlib.crc32(b"\xa2" + bytes(report[:-4]))
    report[-4:] = crc.to_bytes(4, "little")
    return bytes(report)
