import math
import time

from .idioma import N_, _

BUTTONS = (
    ("triangle", N_("Triângulo")), ("circle", N_("Círculo")), ("cross", N_("Xis")), ("square", N_("Quadrado")),
    ("up", N_("Cima")), ("down", N_("Baixo")), ("left", N_("Esquerda")), ("right", N_("Direita")),
    ("l1", "L1"), ("r1", "R1"), ("l2", "L2"), ("r2", "R2"), ("l3", "L3"), ("r3", "R3"),
    ("create", "Create"), ("options", "Options"), ("ps", "PS"), ("touchpad", N_("Clique do touchpad")),
    ("mic", N_("Mudo")),
)
BINS = 72
TRAIL = 40
DRIFT_TEXT = {"ok": N_("Sem drift"), "warn": N_("Atenção"), "bad": N_("Drift")}


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
            return str(value) if value else _("indisponível")

        missing = [_(label) for key, label in BUTTONS if key not in self.tested]
        lines = [
            _("# Relatório do DualSense"), "",
            _("Gerado em {data}").format(data=time.strftime(_("%d/%m/%Y %H:%M"))), "",
            _("## Controle"), "",
            _("- Modelo: {valor}").format(valor=v('model')),
            _("- Cor de fábrica: {valor}").format(valor=_(info['colorPt']) if info.get('colorPt') else _("indisponível")),
            _("- Placa: {valor}").format(valor=v('board')),
            _("- Número de série: {valor}").format(valor=v('serial')),
            _("- Firmware: {valor}").format(valor=v('firmware')),
            _("- Hardware: {valor}").format(valor=v('hardware')),
            _("- Data do firmware: {valor}").format(valor=v('build')),
            _("- Endereço MAC: {valor}").format(valor=v('mac')),
            _("- Bateria: {valor}").format(valor=battery),
            _("- Taxa de atualização: {hz} Hz").format(hz=hz), "",
            _("## Botões"), "",
            _("- Testados: {feitos} de {total}").format(feitos=len(self.tested), total=len(BUTTONS)),
            _("- Faltando: {lista}").format(lista=', '.join(missing) if missing else _("nenhum")), "",
            _("## Analógicos"), "",
        ]
        for side, name in (("l", _("Esquerdo")), ("r", _("Direito"))):
            st = self.sticks[side]
            coverage, error = st.circularity()
            rest = f"{st.rest * 100:.1f}%" if st.rest is not None else _("não medido")
            circle = _("{erro:.1f}% de erro").format(erro=error * 100) if error is not None else _("não medida")
            lines.append(_("- {lado}: repouso {repouso}, {drift}, circularidade {circularidade} "
                           "({contorno:.0f}% do contorno)").format(
                lado=name, repouso=rest, drift=_(DRIFT_TEXT.get(st.drift(), N_("drift não medido"))),
                circularidade=circle, contorno=coverage * 100))
        lines += [
            "", _("## Gatilhos"), "",
            *((_("- {gatilho}: máximo {valor} de 255 (curso completo)") if self.max[k] >= 255
               else _("- {gatilho}: máximo {valor} de 255")).format(gatilho=k.upper(), valor=self.max[k])
              for k in ("l2", "r2")),
            "", _("## Sensores e extras"), "",
            _("- Touchpad: até {dedos} dedo(s), clique {clique}").format(
                dedos=self.touch_seen, clique="ok" if self.click_seen else _("não testado")),
            _("- Giroscópio: {estado}").format(estado="ok" if self.gyro_seen else _("não testado")),
            _("- Acelerômetro: {estado}").format(estado="ok" if self.accel_seen else _("não testado")),
            _("- Vibração: {estado}").format(estado=_("testada") if self.vibration_done else _("não testada")),
            _("- Alto-falante: {estado}").format(estado=_("testado") if self.speaker_done else _("não testado")),
            _("- Fone: {estado}").format(estado=_("testado") if self.headphone_done else _("não testado")),
            _("- Microfone: {estado}").format(
                estado=_("pico de {pico:.0f}%").format(pico=self.mic_peak * 100) if self.mic_peak else _("não testado")),
            "",
        ]
        return "\n".join(lines)
