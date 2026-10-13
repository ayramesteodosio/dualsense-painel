import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea, QStackedWidget,
                               QTabWidget, QVBoxLayout, QWidget)

from .. import audio, charge_light, config, profiles
from ..protocol import MODES_BY_KEY, TRIGGER_MODES
from ..session import Session
from ..tester import BUTTONS, DRIFT_TEXT, Tester
from .laco import QtLoop
from .widgets import (BatteryChart, Chip, ColorButton, Dot, StickView, Swatch, TouchView, ValueSlider, row,
                      section)

PRESETS = [
    ("Azul PlayStation", (0, 90, 255)), ("Branco", (255, 255, 255)), ("Vermelho", (255, 0, 0)),
    ("Laranja", (255, 90, 0)), ("Amarelo", (255, 200, 0)), ("Verde", (0, 255, 40)),
    ("Ciano", (0, 220, 255)), ("Roxo", (140, 0, 255)), ("Rosa", (255, 0, 140)),
]
STATUS_PT = {"Charging": "carregando", "Discharging": "na bateria", "Full": "carga completa",
             "Not charging": "sem carregar"}
CONNECTION = {"usb-detached": "cabo USB, fora do sistema", "usb": "cabo USB", "bluetooth": "Bluetooth"}
LOW_BATTERY = (0, 10, 15, 20, 25, 30)
IDLE_OFF = (0, 5, 10, 15, 30)
INFO_FIELDS = (
    ("model", "Modelo"), ("color", "Cor de fábrica"), ("board", "Placa (BDM)"), ("serial", "Número de série"),
    ("firmware", "Firmware"), ("hardware", "Hardware"), ("update", "Versão de atualização"),
    ("build", "Data do firmware"), ("mac", "Endereço MAC"), ("connection", "Conexão"),
    ("hz", "Taxa de atualização"), ("battery", "Bateria"),
)


def _fmt(value, digits=1):
    return f"{value:.{digits}f}".replace(".", ",")


def duration(minutes):
    minutes = max(1, round(minutes))
    if minutes < 60:
        return f"~{minutes} min"
    h, m = divmod(minutes, 60)
    return f"~{h} h {m} min" if m >= 10 else f"~{h} h"


def scroll(widget):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.NoFrame)
    area.setWidget(widget)
    return area


def page():
    w = QWidget()
    v = QVBoxLayout(w)
    v.setSpacing(14)
    v.setContentsMargins(16, 16, 16, 16)
    return w, v


class Janela(QMainWindow):
    def __init__(self, app_ctl):
        super().__init__()
        self.app_ctl = app_ctl
        self.setWindowTitle("Painel do DualSense")
        self.resize(600, 860)
        self.cfg = config.load()
        self.session = Session(self.cfg, self, loop=QtLoop())
        self.tester = Tester()
        self.mic = None
        self._updating = False

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(scroll(self._build_controle()), "Controle")
        self.tabs.addTab(scroll(self._build_luzes()), "Luzes")
        self.tabs.addTab(scroll(self._build_gatilhos()), "Gatilhos")
        self.tabs.addTab(scroll(self._build_teste()), "Teste")
        self.tabs.addTab(scroll(self._build_info()), "Informações")
        self.tabs.currentChanged.connect(lambda _i: self._refresh_info())

        empty = QLabel("<h2>Nenhum controle conectado</h2><p>Ligue o DualSense no cabo USB ou pareie pelo Bluetooth.</p>")
        empty.setAlignment(Qt.AlignCenter)
        self.outer = QStackedWidget()
        self.outer.addWidget(empty)
        self.outer.addWidget(self.tabs)
        self.setCentralWidget(self.outer)

        self.mode_changed()
        self.historico_refresh()
        self.session.loop.timeout_add_seconds(60, lambda: self.historico_refresh() or True)
        self.session.start()

    def toast(self, text):
        self.statusBar().showMessage(text, 2500)

    def aviso_versao(self, tag, abrir):
        if getattr(self, "botao_versao", None):
            self.botao_versao.setText(f"Baixar a versão {tag}")
            return
        self.botao_versao = QPushButton(f"Baixar a versão {tag}")
        self.botao_versao.setFlat(True)
        self.botao_versao.clicked.connect(abrir)
        self.statusBar().addPermanentWidget(self.botao_versao)

    def _current(self):
        return self.tabs.tabText(self.tabs.currentIndex()) if self.isVisible() else None

    def _build_controle(self):
        w, v = page()
        card = QWidget()
        c = QVBoxLayout(card)
        c.setAlignment(Qt.AlignHCenter)
        self.battery_label = QLabel("--%")
        font = QFont()
        font.setPointSize(34)
        font.setBold(True)
        self.battery_label.setFont(font)
        self.battery_label.setAlignment(Qt.AlignCenter)
        self.battery_status = QLabel()
        self.battery_status.setAlignment(Qt.AlignCenter)
        self.battery_bar = QProgressBar()
        self.battery_bar.setRange(0, 100)
        self.battery_bar.setTextVisible(False)
        self.battery_bar.setFixedWidth(260)
        self.mode_label = QLabel()
        self.mode_label.setAlignment(Qt.AlignCenter)
        bold = QFont()
        bold.setPointSize(13)
        bold.setBold(True)
        self.mode_label.setFont(bold)
        self.mode_button = QPushButton()
        self.mode_button.setMinimumHeight(38)
        self.mode_button.setMinimumWidth(260)
        self.mode_button.clicked.connect(lambda: self.set_charging(not self.session.charging_mode))
        for x in (self.battery_label, self.battery_status):
            c.addWidget(x)
        c.addWidget(self.battery_bar, 0, Qt.AlignHCenter)
        c.addWidget(self.mode_label)
        c.addWidget(self.mode_button, 0, Qt.AlignHCenter)
        v.addWidget(card)

        box, lay = section("Modo carregar", "No cabo USB o controle sai do sistema: desktop, Steam e jogos param de "
                                            "enxergá-lo, e as luzes apagam, menos a luz de carga se estiver ligada.")
        self.connection_label = QLabel()
        lay.addWidget(row("Conexão", self.connection_label))
        auto = QCheckBox()
        auto.setChecked(self.cfg["auto_charge"])
        auto.toggled.connect(lambda on: self._set("auto_charge", on))
        lay.addWidget(row("Entrar sozinho ao ligar no cabo", auto, "Quando o controle aparecer pelo USB"))
        v.addWidget(box)

        box, lay = section("Luz no modo carregar", "Muda na hora, inclusive com o controle carregando.")
        glow = QCheckBox()
        glow.setChecked(self.cfg["charge_glow"])
        glow.toggled.connect(lambda on: self._set("charge_glow", on))
        lay.addWidget(row("Acender enquanto carrega", glow, "Como o laranja do PS5 em repouso"))
        self.charge_color = ColorButton(self.cfg["charge_color"], "Cor da luz de carga")
        self.charge_color.color_changed.connect(lambda rgb: self._set("charge_color", rgb))
        reset = QPushButton("Laranja")
        reset.clicked.connect(self._reset_charge_color)
        colors = QWidget()
        ch = QHBoxLayout(colors)
        ch.setContentsMargins(0, 0, 0, 0)
        ch.addWidget(reset)
        ch.addWidget(self.charge_color)
        lay.addWidget(row("Cor", colors))
        style = QComboBox()
        style.addItems(charge_light.STYLE_LABELS)
        style.setCurrentIndex(charge_light.STYLES.index(self.cfg["charge_style"]))
        style.currentIndexChanged.connect(lambda i: self._set("charge_style", charge_light.STYLES[i]))
        lay.addWidget(row("Estilo", style))
        period = ValueSlider(1, 10, self.cfg["charge_period"], lambda x: f"{_fmt(x)} s", step=0.5)
        period.changed.connect(lambda x: self._set("charge_period", float(x)))
        lay.addWidget(row("Duração do ciclo", period, "Maior é mais lento"))
        intensity = ValueSlider(5, 100, self.cfg["charge_intensity"], lambda x: f"{x:.0f}%")
        intensity.changed.connect(lambda x: self._set("charge_intensity", int(x)))
        lay.addWidget(row("Intensidade", intensity))
        full = QComboBox()
        full.addItems(charge_light.FULL_LABELS)
        full.setCurrentIndex(charge_light.FULL_ACTIONS.index(self.cfg["charge_full"]))
        full.currentIndexChanged.connect(lambda i: self._set("charge_full", charge_light.FULL_ACTIONS[i]))
        lay.addWidget(row("Quando encher", full))
        v.addWidget(box)

        box, lay = section("Histórico da bateria", "Últimas 48 horas.")
        self.chart = BatteryChart()
        self.estimate = QLabel()
        lay.addWidget(self.chart)
        lay.addWidget(self.estimate)
        v.addWidget(box)

        box, lay = section("Ajustes")
        shortcut = QCheckBox()
        shortcut.setChecked(self.cfg["shortcut"])
        shortcut.toggled.connect(lambda on: self._set("shortcut", on))
        lay.addWidget(row("Atalho no controle", shortcut, "Segurar PS + Options por 2 s liga ou desliga o modo carregar"))
        low = QComboBox()
        low.addItems(["Desligado"] + [f"{x}%" for x in LOW_BATTERY[1:]])
        low.setCurrentIndex(LOW_BATTERY.index(self.cfg["low_battery"]) if self.cfg["low_battery"] in LOW_BATTERY else 0)
        low.currentIndexChanged.connect(lambda i: self._set("low_battery", LOW_BATTERY[i]))
        lay.addWidget(row("Aviso de bateria baixa", low))
        idle = QComboBox()
        idle.addItems(["Nunca"] + [f"{x} min" for x in IDLE_OFF[1:]])
        idle.setCurrentIndex(IDLE_OFF.index(self.cfg["idle_off"]) if self.cfg["idle_off"] in IDLE_OFF else 0)
        idle.currentIndexChanged.connect(lambda i: self._set("idle_off", IDLE_OFF[i]))
        lay.addWidget(row("Desligar sozinho no Bluetooth", idle, "Depois de um tempo sem mexer no controle"))
        off = QPushButton("Desligar")
        off.clicked.connect(self.session.disconnect_bluetooth)
        self.off_row = row("Desligar controle", off, "Desconecta do Bluetooth e desliga")
        self.off_row.setVisible(False)
        lay.addWidget(self.off_row)
        v.addWidget(box)
        v.addStretch(1)
        return w

    def _build_luzes(self):
        w, v = page()
        self.lights_page = w
        box, lay = section("Barra de luz")
        self.color_button = ColorButton(self.cfg["color"], "Cor da barra de luz")
        self.color_button.color_changed.connect(self._set_color)
        lay.addWidget(row("Cor", self.color_button))
        swatches = QWidget()
        sh = QHBoxLayout(swatches)
        sh.setContentsMargins(0, 0, 0, 0)
        for name, rgb in PRESETS:
            s = Swatch(rgb, name)
            s.clicked.connect(lambda _c=False, rgb=rgb: self._set_color(list(rgb)))
            sh.addWidget(s)
        sh.addStretch(1)
        lay.addWidget(swatches)
        self.intensity = ValueSlider(0, 100, self.cfg["intensity"], lambda x: f"{x:.0f}%")
        self.intensity.changed.connect(lambda x: self._set("intensity", int(x)))
        lay.addWidget(row("Intensidade", self.intensity))
        self.lightbar_mode = QComboBox()
        self.lightbar_mode.addItems(["Cor fixa", "Mostrar a bateria"])
        self.lightbar_mode.setCurrentIndex(1 if self.cfg["lightbar_mode"] == "battery" else 0)
        self.lightbar_mode.currentIndexChanged.connect(
            lambda i: self._set("lightbar_mode", "battery" if i == 1 else "fixed"))
        lay.addWidget(row("Modo da barra de luz", self.lightbar_mode, "Verde, amarelo e vermelho conforme a carga"))
        v.addWidget(box)

        box, lay = section("LEDs do jogador", "Os cinco pontinhos embaixo do touchpad.")
        leds = QWidget()
        lh = QHBoxLayout(leds)
        lh.setContentsMargins(0, 0, 0, 0)
        self.led_toggles = []
        for i in range(5):
            t = QPushButton("●")
            t.setCheckable(True)
            t.setFixedSize(34, 34)
            t.setChecked(bool(self.cfg["player_leds"] & (1 << i)))
            t.toggled.connect(self._on_leds)
            self.led_toggles.append(t)
            lh.addWidget(t)
        lay.addWidget(row("Acesos", leds))
        self.led_brightness = QComboBox()
        self.led_brightness.addItems(["Alto", "Médio", "Baixo"])
        self.led_brightness.setCurrentIndex(self.cfg["led_brightness"])
        self.led_brightness.currentIndexChanged.connect(lambda i: self._set("led_brightness", i))
        lay.addWidget(row("Brilho", self.led_brightness))
        v.addWidget(box)

        box, lay = section("Outros")
        self.mic_led = QComboBox()
        self.mic_led.addItems(["Apagada", "Acesa", "Pulsando"])
        self.mic_led.setCurrentIndex(self.cfg["mic_led"])
        self.mic_led.currentIndexChanged.connect(lambda i: self._set("mic_led", i))
        lay.addWidget(row("Luz do botão de microfone", self.mic_led))
        rumble = QPushButton("Testar")
        rumble.clicked.connect(self.session.test_rumble)
        lay.addWidget(row("Vibração", rumble, "Os dois motores por meio segundo"))
        v.addWidget(box)

        box, self.perfis_layout = section("Perfis", "Guardam a luz, os LEDs e os gatilhos para trocar com um clique.")
        entry = QWidget()
        eh = QHBoxLayout(entry)
        eh.setContentsMargins(0, 0, 0, 0)
        self.profile_name = QLineEdit()
        self.profile_name.setPlaceholderText("Nome do perfil, ex.: Corrida")
        self.profile_name.setMaxLength(32)
        self.profile_name.returnPressed.connect(self._save_profile)
        save = QPushButton("Salvar atual")
        save.clicked.connect(self._save_profile)
        eh.addWidget(self.profile_name, 1)
        eh.addWidget(save)
        self.perfis_layout.addWidget(entry)
        self.profile_rows = []
        v.addWidget(box)
        self._refresh_profiles()
        v.addStretch(1)
        return w

    def _build_gatilhos(self):
        w, v = page()
        self.triggers_page = w
        self.trigger_ui = {}
        for side, title in (("l2", "Gatilho esquerdo (L2)"), ("r2", "Gatilho direito (R2)")):
            box, lay = section(title)
            combo = QComboBox()
            combo.addItems([m.label for m in TRIGGER_MODES])
            combo.setCurrentIndex([m.key for m in TRIGGER_MODES].index(self.cfg["triggers"][side]["mode"]))
            combo.currentIndexChanged.connect(lambda i, s=side: self._on_trigger_mode(s, i))
            lay.addWidget(row("Efeito", combo))
            desc = QLabel()
            desc.setWordWrap(True)
            lay.addWidget(desc)
            params = QWidget()
            params_layout = QVBoxLayout(params)
            params_layout.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(params)
            level = QProgressBar()
            level.setRange(0, 255)
            level.setTextVisible(False)
            level.setFixedWidth(180)
            lay.addWidget(row("Pressão agora", level, "Aperte para sentir o efeito"))
            copy = QPushButton("Copiar para o outro")
            copy.clicked.connect(lambda _c=False, s=side: self._copy_trigger(s))
            lay.addWidget(row("Mesmo efeito no outro gatilho", copy))
            self.trigger_ui[side] = {"combo": combo, "desc": desc, "params": params_layout, "level": level}
            v.addWidget(box)
            self._rebuild_params(side)
        v.addStretch(1)
        return w

    def _rebuild_params(self, side):
        ui = self.trigger_ui[side]
        lay = ui["params"]
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        trig = self.cfg["triggers"][side]
        mode = MODES_BY_KEY[trig["mode"]]
        ui["desc"].setText(mode.description)
        values = {**mode.defaults(), **trig.get("params", {})}
        for p in mode.params:
            fmt = (lambda x: f"{x * 10:.0f}%") if p.position else (lambda x: f"{x:.0f}")
            slider = ValueSlider(p.low, p.high, values[p.key], fmt)
            slider.changed.connect(lambda x, s=side, k=p.key: self._on_trigger_param(s, k, x))
            lay.addWidget(row(p.label, slider))

    def _build_teste(self):
        w, v = page()
        top = QWidget()
        th = QHBoxLayout(top)
        th.setContentsMargins(0, 0, 0, 0)
        self.hz_label = QLabel("-- Hz")
        restart = QPushButton("Recomeçar")
        restart.clicked.connect(self._restart_test)
        report = QPushButton("Gerar relatório")
        report.clicked.connect(self._report)
        th.addWidget(QLabel("<b>Teste do controle</b>"))
        th.addStretch(1)
        th.addWidget(self.hz_label)
        th.addWidget(restart)
        th.addWidget(report)
        v.addWidget(top)
        self.test_paused = QLabel("Teste pausado: no modo carregar o controle fica fora do sistema.")
        self.test_paused.setVisible(False)
        v.addWidget(self.test_paused)

        box, lay = section("Botões")
        self.buttons_count = QLabel()
        lay.addWidget(self.buttons_count)
        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setSpacing(6)
        self.chips = {}
        for i, (key, label) in enumerate(BUTTONS):
            chip = Chip(label)
            self.chips[key] = chip
            grid.addWidget(chip, i // 4, i % 4)
        lay.addWidget(grid_w)
        v.addWidget(box)

        box, lay = section("Analógicos", "Gire cada analógico encostando na borda para medir a circularidade.")
        sticks = QWidget()
        sh = QHBoxLayout(sticks)
        self.stick_views, self.stick_labels = {}, {}
        for side, name in (("l", "Esquerdo"), ("r", "Direito")):
            col = QVBoxLayout()
            col.addWidget(QLabel(f"<b>{name}</b>"))
            view = StickView(lambda s=side: self.tester.sticks[s])
            col.addWidget(view)
            info = QLabel()
            info.setWordWrap(True)
            col.addWidget(info)
            reset = QPushButton("Zerar circularidade")
            reset.clicked.connect(lambda _c=False, s=side: (self.tester.sticks[s].reset_circle(), self.stick_views[s].update()))
            col.addWidget(reset)
            sh.addLayout(col)
            self.stick_views[side], self.stick_labels[side] = view, info
        lay.addWidget(sticks)
        v.addWidget(box)

        box, lay = section("Gatilhos")
        self.test_bars, self.test_trigger_labels = {}, {}
        for side in ("l2", "r2"):
            bar = QProgressBar()
            bar.setRange(0, 255)
            bar.setTextVisible(False)
            bar.setFixedWidth(180)
            label = QLabel()
            line = QWidget()
            lh = QHBoxLayout(line)
            lh.setContentsMargins(0, 0, 0, 0)
            lh.addWidget(QLabel(f"<b>{side.upper()}</b>"))
            lh.addWidget(label, 1)
            lh.addWidget(bar)
            lay.addWidget(line)
            self.test_bars[side], self.test_trigger_labels[side] = bar, label
        v.addWidget(box)

        box, lay = section("Touchpad")
        self.touch_view = TouchView()
        lay.addWidget(self.touch_view, 0, Qt.AlignHCenter)
        self.touch_label = QLabel()
        self.touch_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.touch_label)
        v.addWidget(box)

        box, lay = section("Movimento")
        mono = QFont("monospace")
        mono.setStyleHint(QFont.Monospace)
        self.gyro_label = QLabel()
        self.accel_label = QLabel()
        for x in (self.gyro_label, self.accel_label):
            x.setFont(mono)
        lay.addWidget(row("Giroscópio", self.gyro_label, "graus por segundo"))
        lay.addWidget(row("Acelerômetro", self.accel_label, "em g"))
        v.addWidget(box)

        box, lay = section("Vibração")
        self.motor = {}
        for key, title in (("left", "Motor esquerdo (forte)"), ("right", "Motor direito (fraco)")):
            s = ValueSlider(0, 255, 180)
            lay.addWidget(row(title, s))
            self.motor[key] = s
        pulses = QWidget()
        ph = QHBoxLayout(pulses)
        ph.setContentsMargins(0, 0, 0, 0)
        ph.addStretch(1)
        for label, which in (("Esquerdo", "left"), ("Direito", "right"), ("Os dois", "both")):
            b = QPushButton(label)
            b.clicked.connect(lambda _c=False, wh=which: self._pulse(wh))
            ph.addWidget(b)
        lay.addWidget(pulses)
        v.addWidget(box)

        self.audio_box, lay = section("Áudio", "Funciona com o controle no cabo USB.")
        tones = QWidget()
        toh = QHBoxLayout(tones)
        toh.setContentsMargins(0, 0, 0, 0)
        for label, target in (("Tocar no alto-falante", audio.SPEAKER), ("Tocar no fone", audio.HEADPHONES)):
            b = QPushButton(label)
            b.clicked.connect(lambda _c=False, t=target: self._tone(t))
            toh.addWidget(b)
        toh.addStretch(1)
        lay.addWidget(tones)
        self.mic_check = QCheckBox("Medir")
        self.mic_check.toggled.connect(self._mic_toggled)
        self.mic_bar = QProgressBar()
        self.mic_bar.setRange(0, 100)
        self.mic_bar.setTextVisible(False)
        self.mic_bar.setFixedWidth(140)
        micw = QWidget()
        mh = QHBoxLayout(micw)
        mh.setContentsMargins(0, 0, 0, 0)
        mh.addWidget(self.mic_bar)
        mh.addWidget(self.mic_check)
        lay.addWidget(row("Microfone", micw, "Fale perto do controle"))
        self.phone_label = QLabel("não")
        lay.addWidget(row("Fone conectado", self.phone_label))
        v.addWidget(self.audio_box)
        self._refresh_chips(None)
        v.addStretch(1)
        return w

    def _build_info(self):
        w, v = page()
        box, lay = section("Informações do controle", "Cor, placa e número de série são lidos pelo cabo USB e ficam "
                                                     "guardados para aparecer também no Bluetooth.")
        self.info_labels, self.info_values = {}, {}
        for key, title in INFO_FIELDS:
            value = QLabel("Indisponível")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            copy = QPushButton("Copiar")
            copy.clicked.connect(lambda _c=False, k=key: self._copy_info(k))
            line = QWidget()
            lh = QHBoxLayout(line)
            lh.setContentsMargins(0, 0, 0, 0)
            if key == "color":
                self.info_dot = Dot()
                lh.addWidget(self.info_dot)
            lh.addWidget(QLabel(f"<b>{title}</b>"))
            lh.addStretch(1)
            lh.addWidget(value)
            lh.addWidget(copy)
            lay.addWidget(line)
            self.info_labels[key] = value
        v.addWidget(box)
        v.addStretch(1)
        return w

    def changed(self):
        if not self._updating:
            self.session.settings_changed()

    def _set(self, key, value):
        if self._updating:
            return
        self.cfg[key] = value
        self.changed()

    def _set_color(self, rgb):
        self.cfg["color"] = list(rgb)
        self.color_button.set_rgb(rgb)
        self.changed()

    def _reset_charge_color(self):
        rgb = list(charge_light.DEFAULTS["charge_color"])
        self.charge_color.set_rgb(rgb)
        self._set("charge_color", rgb)

    def _on_leds(self, _on):
        if self._updating:
            return
        self.cfg["player_leds"] = sum(1 << i for i, t in enumerate(self.led_toggles) if t.isChecked())
        self.changed()

    def _on_trigger_mode(self, side, index):
        if self._updating:
            return
        mode = TRIGGER_MODES[index]
        if self.cfg["triggers"][side]["mode"] != mode.key:
            self.cfg["triggers"][side] = {"mode": mode.key, "params": mode.defaults()}
            self._rebuild_params(side)
            self.changed()

    def _on_trigger_param(self, side, key, value):
        self.cfg["triggers"][side].setdefault("params", {})[key] = int(value)
        self.changed()

    def _copy_trigger(self, side):
        other = "r2" if side == "l2" else "l2"
        src = self.cfg["triggers"][side]
        self.cfg["triggers"][other] = {"mode": src["mode"], "params": dict(src.get("params", {}))}
        self._updating = True
        self.trigger_ui[other]["combo"].setCurrentIndex([m.key for m in TRIGGER_MODES].index(src["mode"]))
        self._updating = False
        self._rebuild_params(other)
        self.changed()
        self.toast("Efeito copiado")

    def sync_widgets(self):
        self._updating = True
        try:
            self.color_button.set_rgb(self.cfg["color"])
            self.intensity.set_value(self.cfg["intensity"])
            for i, t in enumerate(self.led_toggles):
                t.setChecked(bool(self.cfg["player_leds"] & (1 << i)))
            self.led_brightness.setCurrentIndex(self.cfg["led_brightness"])
            self.mic_led.setCurrentIndex(self.cfg["mic_led"])
            self.lightbar_mode.setCurrentIndex(1 if self.cfg["lightbar_mode"] == "battery" else 0)
            keys = [m.key for m in TRIGGER_MODES]
            for side in ("l2", "r2"):
                self.trigger_ui[side]["combo"].setCurrentIndex(keys.index(self.cfg["triggers"][side]["mode"]))
                self._rebuild_params(side)
        finally:
            self._updating = False

    def _refresh_profiles(self):
        for w in self.profile_rows:
            self.perfis_layout.removeWidget(w)
            w.deleteLater()
        self.profile_rows = []
        for p in profiles.summary(self.cfg):
            modes = " · ".join(f"{s.upper()} {MODES_BY_KEY.get(m, MODES_BY_KEY['off']).label.lower()}"
                               for s, m in p["triggers"].items())
            line = QWidget()
            lh = QHBoxLayout(line)
            lh.setContentsMargins(0, 0, 0, 0)
            dot = Dot()
            dot.set_color("#%02x%02x%02x" % tuple(p["color"]))
            lh.addWidget(dot)
            texts = QLabel(f"<b>{p['name']}</b><br><small>{modes}</small>")
            lh.addWidget(texts, 1)
            apply_btn = QPushButton("Aplicar")
            apply_btn.clicked.connect(lambda _c=False, n=p["name"]: self._apply_profile(n))
            delete = QPushButton("Apagar")
            delete.clicked.connect(lambda _c=False, n=p["name"]: self._delete_profile(n))
            lh.addWidget(apply_btn)
            lh.addWidget(delete)
            self.perfis_layout.addWidget(line)
            self.profile_rows.append(line)

    def _save_profile(self):
        name = profiles.save(self.cfg, self.profile_name.text())
        if not name:
            self.toast("Dê um nome ao perfil")
            return
        self.profile_name.clear()
        self.changed()
        self._refresh_profiles()
        self.toast(f"Perfil \"{name}\" salvo")

    def _apply_profile(self, name):
        if profiles.apply(self.cfg, name):
            self.sync_widgets()
            self.changed()
            self.toast(f"Perfil \"{name}\" aplicado")

    def _delete_profile(self, name):
        answer = QMessageBox.question(self, "Apagar perfil", f"Apagar o perfil \"{name}\"?")
        if answer == QMessageBox.Yes and profiles.delete(self.cfg, name):
            self.changed()
            self._refresh_profiles()

    def set_charging(self, on):
        self.session.set_charging(on, announce=False)

    def status_changed(self):
        ses = self.session
        self.outer.setCurrentIndex(1 if ses.connected else 0)
        if not ses.connected:
            return
        pct, status = ses.battery_pct, ses.battery_status
        self.battery_label.setText(f"{pct}%" if pct is not None else "--%")
        self.battery_bar.setValue(pct or 0)
        self.battery_status.setText(STATUS_PT.get(status, status or "bateria desconhecida"))
        self.connection_label.setText(f"{ses.model} pelo {CONNECTION.get(ses.connection, '')}")
        self.off_row.setVisible(ses.connection == "bluetooth")
        self.app_ctl.update_tray()
        if self._current() == "Informações":
            self._refresh_info()

    def mode_changed(self):
        on = self.session.charging_mode
        self.mode_label.setText("Modo carregar" if on else "Modo normal")
        self.mode_button.setText("Voltar ao modo normal" if on else "Entrar no modo carregar")
        self.lights_page.setEnabled(not on)
        self.triggers_page.setEnabled(not on)
        paused = on and self.session.connection == "usb-detached"
        self.test_paused.setVisible(paused)
        usb = self.session.connection == "usb" and not on
        self.audio_box.setEnabled(usb)
        if not usb:
            self.stop_mic()
        self.app_ctl.update_tray()

    def input(self, data):
        page_name = self._current()
        if page_name == "Gatilhos":
            for side, value in data["triggers"].items():
                self.trigger_ui[side]["level"].setValue(value)
        elif page_name == "Teste":
            self._update_test(data)

    def info_changed(self):
        self._refresh_info()

    def history_changed(self):
        self.historico_refresh()

    def historico_refresh(self):
        h = self.session.history
        self.chart.set_points(h.as_list())
        est = h.estimate()
        if est and est["kind"] == "full":
            self.estimate.setText(f"Cheio em {duration(est['minutes'])}, no ritmo atual.")
        elif est and est["kind"] == "empty":
            self.estimate.setText(f"Acaba em {duration(est['minutes'])}, no ritmo atual.")
        else:
            self.estimate.setText("A estimativa aparece depois de alguns minutos de carga ou uso.")
        return True

    def low_battery(self, pct):
        self.app_ctl.notify("Bateria do controle baixa", f"O DualSense está com {pct}%. Hora de ligar no cabo.")

    def charged(self):
        self.app_ctl.notify("Controle carregado", "Pode tirar do cabo ou voltar ao modo normal.")

    def _refresh_chips(self, data):
        for key, chip in self.chips.items():
            chip.set_state(key in self.tester.tested, bool(data and data["buttons"].get(key)))
        self.buttons_count.setText(f"{len(self.tester.tested)} de {len(BUTTONS)} testados. "
                                   "Cada botão fica verde depois de apertado uma vez.")

    def _update_test(self, data):
        self.tester.record(data)
        self._refresh_chips(data)
        for side in ("l", "r"):
            st = self.tester.sticks[side]
            coverage, error = st.circularity()
            rest = f"repouso {_fmt(st.rest * 100)}%" if st.rest is not None else "medindo repouso"
            circ = f"circularidade {_fmt(error * 100)}% de erro" if error is not None else "gire para medir"
            self.stick_labels[side].setText(f"X {st.raw[0]}  Y {st.raw[1]}\n{rest} · "
                                            f"{DRIFT_TEXT.get(st.drift(), 'medindo drift')}\n"
                                            f"{circ} · contorno {coverage * 100:.0f}%")
            self.stick_views[side].update()
        for side in ("l2", "r2"):
            value, best = data["triggers"][side], self.tester.max[side]
            self.test_bars[side].setValue(value)
            self.test_trigger_labels[side].setText(
                f"agora {value} · máximo {best}{' · curso completo' if best >= 255 else ''}")
        self.touch_view.touch = data["touch"]
        self.touch_view.click = data["buttons"].get("touchpad", False)
        self.touch_view.update()
        active = sum(1 for t in data["touch"] if t["active"])
        self.touch_label.setText(f"{active} dedo(s) agora · até {self.tester.touch_seen} visto(s) · "
                                 f"clique {'ok' if self.tester.click_seen else 'não testado'}")
        self.gyro_label.setText("  ".join(f"{x:+7.1f}" for x in data["gyro"]))
        self.accel_label.setText("  ".join(f"{x:+6.2f}" for x in data["accel"]))
        self.phone_label.setText("sim" if data.get("headphones") else "não")
        self.hz_label.setText(f"{self.session.report_hz} Hz")

    def _restart_test(self):
        self.tester.reset()
        self._refresh_chips(None)
        for view in self.stick_views.values():
            view.update()
        self.toast("Teste recomeçado")

    def _pulse(self, which):
        left = self.motor["left"].value() if which in ("left", "both") else 0
        right = self.motor["right"].value() if which in ("right", "both") else 0
        self.session.rumble(left, right, 600)
        self.tester.vibration_done = True

    def _tone(self, target):
        if audio.play_tone(target):
            if target == audio.SPEAKER:
                self.tester.speaker_done = True
            else:
                self.tester.headphone_done = True
        else:
            self.toast("Áudio do controle não encontrado")

    def _mic_toggled(self, on):
        if on and not self.mic:
            self.mic = audio.MicMeter(lambda level: self.session.loop.idle_add(self._mic_level, level))
            if not self.mic.start():
                self.mic = None
                self.mic_check.setChecked(False)
                self.toast("Microfone do controle não encontrado")
        elif not on:
            self.stop_mic()

    def _mic_level(self, level):
        self.mic_bar.setValue(int(level * 100))
        self.tester.mic_peak = max(self.tester.mic_peak, level)
        return False

    def stop_mic(self):
        if self.mic:
            self.mic.stop()
            self.mic = None
        if self.mic_check.isChecked():
            self.mic_check.setChecked(False)
        self.mic_bar.setValue(0)

    def _report(self):
        ses = self.session
        pct, status = ses.battery_pct, ses.battery_status
        battery = f"{pct}%, {STATUS_PT.get(status, status or '')}".rstrip(", ") if pct is not None else "indisponível"
        text = self.tester.report(ses.info, battery, ses.report_hz)
        name = f"relatorio-dualsense-{time.strftime('%Y%m%d-%H%M')}.md"
        path, _ = QFileDialog.getSaveFileName(self, "Salvar relatório", name, "Markdown (*.md)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self.toast(f"Relatório salvo em {path}")
        except OSError as e:
            self.toast(f"Não consegui salvar: {e.strerror}")

    def _info_value(self, key):
        ses, info = self.session, self.session.info or {}
        if key == "connection":
            text = CONNECTION.get(ses.connection, "")
            return text[:1].upper() + text[1:] if text else None
        if key == "hz":
            return f"{ses.report_hz} Hz" if ses.report_hz else None
        if key == "battery":
            if ses.battery_pct is None:
                return None
            return f"{ses.battery_pct}%, {STATUS_PT.get(ses.battery_status, '')}".rstrip(", ")
        if key == "model":
            return info.get("model") or ses.model
        if key == "color":
            if info.get("colorPt"):
                english = info.get("color")
                return info["colorPt"] + (f" ({english})" if english and english != info["colorPt"] else "")
            return f"Código {info['colorCode']}" if info.get("colorCode") else None
        value = info.get(key)
        return str(value) if value else None

    def _refresh_info(self):
        for key, label in self.info_labels.items():
            value = self._info_value(key)
            self.info_values[key] = value
            label.setText(value or "Indisponível")
        self.info_dot.set_color((self.session.info or {}).get("colorHex"))

    def _copy_info(self, key):
        value = self.info_values.get(key)
        if value:
            QGuiApplication.clipboard().setText(value)
            self.toast("Copiado")

    def closeEvent(self, event):
        if self.session.charging_mode and self.session.connected and self.app_ctl.tray_available():
            event.ignore()
            self.hide()
            self.app_ctl.notify("Modo carregar continua ligado", "O painel segue na bandeja do sistema.")
            return
        self.stop_mic()
        self.session.cleanup()
        event.accept()
        self.app_ctl.quit()
