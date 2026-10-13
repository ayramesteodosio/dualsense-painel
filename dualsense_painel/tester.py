import math
import time

BUTTONS = (
    ("triangle", "Triângulo"), ("circle", "Círculo"), ("cross", "Xis"), ("square", "Quadrado"),
    ("up", "Cima"), ("down", "Baixo"), ("left", "Esquerda"), ("right", "Direita"),
    ("l1", "L1"), ("r1", "R1"), ("l2", "L2"), ("r2", "R2"), ("l3", "L3"), ("r3", "R3"),
    ("create", "Create"), ("options", "Options"), ("ps", "PS"), ("touchpad", "Clique do touchpad"),
    ("mic", "Mudo"),
)
BINS = 72
TRAIL = 40
DRIFT_TEXT = {"ok": "Sem drift", "warn": "Atenção", "bad": "Drift"}


def normalize(value):
    return max(-1.0, min(1.0, (value - 128) / 127.5))


class Stick:
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.raw = (128, 128)
        self.trail = []
        self.rest = None
        self.still = 0
        self.bins = [0.0] * BINS

    def sample(self, rx, ry):
        nx, ny = normalize(rx), normalize(ry)
        moved = math.hypot(nx - self.x, ny - self.y)
        mag = math.hypot(nx, ny)
        self.x, self.y, self.raw = nx, ny, (rx, ry)
        self.trail.append((nx, ny))
        if len(self.trail) > TRAIL:
            self.trail.pop(0)
        if mag < 0.3 and moved < 0.012:
            self.still += 1
            if self.still > 24:
                self.rest = mag if self.rest is None else self.rest + (mag - self.rest) * 0.08
        else:
            self.still = 0
        if mag > 0.6:
            index = int((math.atan2(ny, nx) + math.pi) / (2 * math.pi) * BINS) % BINS
            self.bins[index] = max(self.bins[index], min(mag, 1.42))

    def circularity(self):
        filled = [v for v in self.bins if v > 0]
        coverage = len(filled) / BINS
        error = sum(abs(v - 1) for v in filled) / len(filled) if len(filled) >= 18 else None
        return coverage, error

    def drift(self):
        if self.rest is None:
            return None
        return "ok" if self.rest < 0.05 else "warn" if self.rest < 0.1 else "bad"

    def reset_circle(self):
        self.bins = [0.0] * BINS


class Tester:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.reset()

    def reset(self):
        self.tested = set()
        self.max = {"l2": 0, "r2": 0}
        self.sticks = {"l": Stick(), "r": Stick()}
        self.touch_seen = 0
        self.click_seen = False
        self.gyro_seen = False
        self.accel_seen = False
        self.vibration_done = False
        self.speaker_done = False
        self.headphone_done = False
        self.mic_peak = 0.0
        self.hz = 0
        self.last = None

    def record(self, data):
        if not data:
            return set()
        self.last = data
        newly = {k for k, _ in BUTTONS if data["buttons"].get(k) and k not in self.tested}
        self.tested |= newly
        for side in ("l2", "r2"):
            self.max[side] = max(self.max[side], data["triggers"][side])
        s = data["sticks"]
        self.sticks["l"].sample(s["lx"], s["ly"])
        self.sticks["r"].sample(s["rx"], s["ry"])
        active = sum(1 for t in data["touch"] if t["active"])
        self.touch_seen = max(self.touch_seen, active)
        self.click_seen = self.click_seen or data["buttons"].get("touchpad", False)
        if any(abs(v) > 20 for v in data["gyro"]):
            self.gyro_seen = True
        if abs(math.hypot(*data["accel"]) - 1) < 0.25 and any(abs(v) > 0.05 for v in data["accel"]):
            self.accel_seen = True
        return newly

    def report(self, info, battery, hz):
        info = info or {}

        def v(key):
            value = info.get(key)
            return str(value) if value else "indisponível"

        missing = [label for key, label in BUTTONS if key not in self.tested]
        lines = [
            "# Relatório do DualSense", "",
            f"Gerado em {time.strftime('%d/%m/%Y %H:%M')}", "",
            "## Controle", "",
            f"- Modelo: {v('model')}",
            f"- Cor de fábrica: {info.get('colorPt') or 'indisponível'}",
            f"- Placa: {v('board')}",
            f"- Número de série: {v('serial')}",
            f"- Firmware: {v('firmware')}",
            f"- Hardware: {v('hardware')}",
            f"- Data do firmware: {v('build')}",
            f"- Endereço MAC: {v('mac')}",
            f"- Bateria: {battery}",
            f"- Taxa de atualização: {hz} Hz", "",
            "## Botões", "",
            f"- Testados: {len(self.tested)} de {len(BUTTONS)}",
            f"- Faltando: {', '.join(missing) if missing else 'nenhum'}", "",
            "## Analógicos", "",
        ]
        for side, name in (("l", "Esquerdo"), ("r", "Direito")):
            st = self.sticks[side]
            coverage, error = st.circularity()
            rest = f"{st.rest * 100:.1f}%" if st.rest is not None else "não medido"
            lines.append(f"- {name}: repouso {rest}, {DRIFT_TEXT.get(st.drift(), 'drift não medido')}, "
                         f"circularidade {f'{error * 100:.1f}% de erro' if error is not None else 'não medida'} "
                         f"({coverage * 100:.0f}% do contorno)")
        lines += [
            "", "## Gatilhos", "",
            f"- L2: máximo {self.max['l2']} de 255{' (curso completo)' if self.max['l2'] >= 255 else ''}",
            f"- R2: máximo {self.max['r2']} de 255{' (curso completo)' if self.max['r2'] >= 255 else ''}",
            "", "## Sensores e extras", "",
            f"- Touchpad: até {self.touch_seen} dedo(s), clique {'ok' if self.click_seen else 'não testado'}",
            f"- Giroscópio: {'ok' if self.gyro_seen else 'não testado'}",
            f"- Acelerômetro: {'ok' if self.accel_seen else 'não testado'}",
            f"- Vibração: {'testada' if self.vibration_done else 'não testada'}",
            f"- Alto-falante: {'testado' if self.speaker_done else 'não testado'}",
            f"- Fone: {'testado' if self.headphone_done else 'não testado'}",
            f"- Microfone: {'pico de ' + format(self.mic_peak * 100, '.0f') + '%' if self.mic_peak else 'não testado'}",
            "",
        ]
        return "\n".join(lines)
