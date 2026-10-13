import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea, QStackedWidget,
                               QTabWidget, QVBoxLayout, QWidget)

from .. import audio, charge_light, config, idioma, profiles, segundo_plano
from ..idioma import N_, _
from ..protocol import MODES_BY_KEY, TRIGGER_MODES
from ..session import Session
from ..tester import BUTTONS, DRIFT_TEXT, Tester
from ..versao import VERSAO
from .laco import QtLoop
from .widgets import (BatteryChart, Chip, ColorButton, Dot, StickView, Swatch, TouchView, ValueSlider, row,
                      section)

PRESETS = [
    (N_("Azul PlayStation"), (0, 90, 255)), (N_("Branco"), (255, 255, 255)), (N_("Vermelho"), (255, 0, 0)),
    (N_("Laranja"), (255, 90, 0)), (N_("Amarelo"), (255, 200, 0)), (N_("Verde"), (0, 255, 40)),
    (N_("Ciano"), (0, 220, 255)), (N_("Roxo"), (140, 0, 255)), (N_("Rosa"), (255, 0, 140)),
]
STATUS_PT = {"Charging": N_("carregando"), "Discharging": N_("na bateria"), "Full": N_("carga completa"),
             "Not charging": N_("sem carregar")}
CONNECTION = {"usb-detached": N_("cabo USB, fora do sistema"), "usb": N_("cabo USB"), "bluetooth": "Bluetooth"}
LOW_BATTERY = (0, 10, 15, 20, 25, 30)
IDLE_OFF = (0, 5, 10, 15, 30)
INFO_FIELDS = (
    ("model", N_("Modelo")), ("color", N_("Cor de fábrica")), ("board", N_("Placa (BDM)")),
    ("serial", N_("Número de série")), ("firmware", "Firmware"), ("hardware", "Hardware"),
    ("update", N_("Versão de atualização")), ("build", N_("Data do firmware")), ("mac", N_("Endereço MAC")),
    ("connection", N_("Conexão")), ("hz", N_("Taxa de atualização")), ("battery", N_("Bateria")),
)


def _fmt(value, digits=1):
    texto = f"{value:.{digits}f}"
    return texto.replace(".", ",") if idioma.atual() == "pt" else texto


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
        self.setWindowTitle(_("Painel do DualSense"))
        self.resize(600, 860)
        self.cfg = config.load()
        self.session = Session(self.cfg, self, loop=QtLoop())
        self.tester = Tester()
        self.mic = None
        self._updating = False

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(scroll(self._build_controle()), _("Controle"))
        self.tabs.addTab(scroll(self._build_luzes()), _("Luzes"))
        self.tabs.addTab(scroll(self._build_gatilhos()), _("Gatilhos"))
        self.tabs.addTab(scroll(self._build_teste()), _("Teste"))
        self.tabs.addTab(scroll(self._build_info()), _("Informações"))
        self.tabs.currentChanged.connect(lambda _i: self._refresh_info())

        empty = QLabel(f"<h2>{_('Nenhum controle conectado')}</h2>"
                       f"<p>{_('Ligue o DualSense no cabo USB ou pareie pelo Bluetooth.')}</p>")
        empty.setAlignment(Qt.AlignCenter)
        self.outer = QStackedWidget()
        self.outer.addWidget(empty)
        self.outer.addWidget(self.tabs)
        corpo = QWidget()
        coluna = QVBoxLayout(corpo)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(0)
        coluna.addWidget(self._build_faixa())
        coluna.addWidget(self.outer, 1)
        self.setCentralWidget(corpo)

        self.mode_changed()
        self.historico_refresh()
        self.session.loop.timeout_add_seconds(60, lambda: self.historico_refresh() or True)
        self.session.start()

    def _iniciar_com_sistema(self, on):
        try:
            segundo_plano.definir("dualsense-painel", on)
        except OSError as e:
            self.toast(_("Não consegui mudar: {erro}").format(erro=e.strerror or e))

    def toast(self, text):
        self.statusBar().showMessage(text, 2500 if len(text) < 60 else 8000)

    def _build_faixa(self):
        self.faixa = QFrame()
        self.faixa.setObjectName("faixa")
        self.faixa.setStyleSheet("QFrame#faixa { background: palette(highlight); } "
                                 "QFrame#faixa QLabel { color: palette(highlighted-text); font-weight: 600; }")
        h = QHBoxLayout(self.faixa)
        h.setContentsMargins(14, 8, 10, 8)
        self.faixa_texto = QLabel()
        self.faixa_progresso = QProgressBar()
        self.faixa_progresso.setRange(0, 100)
        self.faixa_progresso.setMaximumWidth(180)
        self.faixa_progresso.setVisible(False)
        self.faixa_acao = QPushButton()
        self.faixa_depois = QPushButton(_("Depois"))
        self.faixa_depois.clicked.connect(lambda: self.faixa.setVisible(False))
        h.addWidget(self.faixa_texto, 1)
        h.addWidget(self.faixa_progresso)
        h.addWidget(self.faixa_acao)
        h.addWidget(self.faixa_depois)
        self.faixa.setVisible(False)
        return self.faixa

    def _faixa_botao(self, texto, acao):
        try:
            self.faixa_acao.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.faixa_acao.setText(texto)
        self.faixa_acao.setEnabled(True)
        self.faixa_acao.clicked.connect(acao)

    def aviso_versao(self, tag, pode_instalar, atualizar, abrir):
        self.faixa_texto.setText(_("Versão {versao} disponível.").format(versao=tag))
        self.faixa_progresso.setVisible(False)
        self.faixa_depois.setVisible(True)
        self._faixa_botao(_("Atualizar agora") if pode_instalar else _("Baixar"), atualizar if pode_instalar else abrir)
        self.faixa.setVisible(True)

    def progresso_versao(self, tag, fracao):
        self.faixa_texto.setText(_("Baixando a versão {versao}...").format(versao=tag))
        self.faixa_progresso.setVisible(True)
        self.faixa_progresso.setValue(round(fracao * 100))
        self.faixa_acao.setEnabled(False)
        self.faixa_depois.setVisible(False)

    def instalando_versao(self, tag):
        self.faixa_texto.setText(
            _("Instalando a versão {versao}. O painel fecha e abre de novo sozinho.").format(versao=tag))
        self.faixa_progresso.setVisible(False)
        self.faixa_acao.setVisible(False)

    def falha_versao(self, erro, abrir):
        self.faixa_texto.setText(_("Não consegui baixar a atualização ({erro}).").format(erro=erro))
        self.faixa_progresso.setVisible(False)
        self.faixa_depois.setVisible(True)
        self._faixa_botao(_("Abrir a página"), abrir)

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

        box, lay = section(_("Modo carregar"), _("No cabo USB o controle sai do sistema: desktop, Steam e jogos param "
                                                "de enxergá-lo, e as luzes apagam, menos a luz de carga se estiver "
                                                "ligada."))
        self.connection_label = QLabel()
        lay.addWidget(row(_("Conexão"), self.connection_label))
        auto = QCheckBox()
        auto.setChecked(self.cfg["auto_charge"])
        auto.toggled.connect(lambda on: self._set("auto_charge", on))
        lay.addWidget(row(_("Entrar sozinho ao ligar no cabo"), auto, _("Quando o controle aparecer pelo USB")))
        v.addWidget(box)

        box, lay = section(_("Luz no modo carregar"), _("Muda na hora, inclusive com o controle carregando."))
        glow = QCheckBox()
        glow.setChecked(self.cfg["charge_glow"])
        glow.toggled.connect(lambda on: self._set("charge_glow", on))
        lay.addWidget(row(_("Acender enquanto carrega"), glow, _("Como o laranja do PS5 em repouso")))
        self.charge_color = ColorButton(self.cfg["charge_color"], _("Cor da luz de carga"))
        self.charge_color.color_changed.connect(lambda rgb: self._set("charge_color", rgb))
        reset = QPushButton(_("Laranja"))
        reset.clicked.connect(self._reset_charge_color)
        colors = QWidget()
        ch = QHBoxLayout(colors)
        ch.setContentsMargins(0, 0, 0, 0)
        ch.addWidget(reset)
        ch.addWidget(self.charge_color)
        lay.addWidget(row(_("Cor"), colors))
        style = QComboBox()
        style.addItems([_(x) for x in charge_light.STYLE_LABELS])
        style.setCurrentIndex(charge_light.STYLES.index(self.cfg["charge_style"]))
        style.currentIndexChanged.connect(lambda i: self._set("charge_style", charge_light.STYLES[i]))
        lay.addWidget(row(_("Estilo"), style))
        period = ValueSlider(1, 10, self.cfg["charge_period"], lambda x: f"{_fmt(x)} s", step=0.5)
        period.changed.connect(lambda x: self._set("charge_period", float(x)))
        lay.addWidget(row(_("Duração do ciclo"), period, _("Maior é mais lento")))
        intensity = ValueSlider(5, 100, self.cfg["charge_intensity"], lambda x: f"{x:.0f}%")
        intensity.changed.connect(lambda x: self._set("charge_intensity", int(x)))
        lay.addWidget(row(_("Intensidade"), intensity))
        full = QComboBox()
        full.addItems([_(x) for x in charge_light.FULL_LABELS])
        full.setCurrentIndex(charge_light.FULL_ACTIONS.index(self.cfg["charge_full"]))
        full.currentIndexChanged.connect(lambda i: self._set("charge_full", charge_light.FULL_ACTIONS[i]))
        lay.addWidget(row(_("Quando encher"), full))
        v.addWidget(box)

        box, lay = section(_("Histórico da bateria"), _("Últimas 48 horas."))
        self.chart = BatteryChart()
        self.estimate = QLabel()
        lay.addWidget(self.chart)
        lay.addWidget(self.estimate)
        v.addWidget(box)

        box, lay = section(_("Ajustes"))
        shortcut = QCheckBox()
        shortcut.setChecked(self.cfg["shortcut"])
        shortcut.toggled.connect(lambda on: self._set("shortcut", on))
        lay.addWidget(row(_("Atalho no controle"), shortcut,
                          _("Segurar PS + Options por 2 s liga ou desliga o modo carregar")))
        low = QComboBox()
        low.addItems([_("Desligado")] + [f"{x}%" for x in LOW_BATTERY[1:]])
        low.setCurrentIndex(LOW_BATTERY.index(self.cfg["low_battery"]) if self.cfg["low_battery"] in LOW_BATTERY else 0)
        low.currentIndexChanged.connect(lambda i: self._set("low_battery", LOW_BATTERY[i]))
        lay.addWidget(row(_("Aviso de bateria baixa"), low))
        idle = QComboBox()
        idle.addItems([_("Nunca")] + [f"{x} min" for x in IDLE_OFF[1:]])
        idle.setCurrentIndex(IDLE_OFF.index(self.cfg["idle_off"]) if self.cfg["idle_off"] in IDLE_OFF else 0)
        idle.currentIndexChanged.connect(lambda i: self._set("idle_off", IDLE_OFF[i]))
        lay.addWidget(row(_("Desligar sozinho no Bluetooth"), idle, _("Depois de um tempo sem mexer no controle")))
        off = QPushButton(_("Desligar"))
        off.clicked.connect(self.session.disconnect_bluetooth)
        self.off_row = row(_("Desligar controle"), off, _("Desconecta do Bluetooth e desliga"))
        self.off_row.setVisible(False)
        lay.addWidget(self.off_row)
        fundo = QCheckBox()
        fundo.setChecked(self.cfg["segundo_plano"])
        fundo.toggled.connect(lambda on: self._set("segundo_plano", on))
        lay.addWidget(row(_("Continuar rodando ao fechar a janela"), fundo,
                          _("Modo carregar automático, avisos de bateria e atalho seguem funcionando")))
        inicio = QCheckBox()
        inicio.setChecked(segundo_plano.ativo("dualsense-painel"))
        inicio.toggled.connect(self._iniciar_com_sistema)
        lay.addWidget(row(_("Iniciar com o sistema"), inicio, _("Abre escondido ao entrar na sua conta")))
        lingua = QComboBox()
        lingua.addItems([_("Automático"), _("Português"), "English"])
        lingua.setCurrentIndex(idioma.IDIOMAS.index(self.cfg["idioma"]) if self.cfg["idioma"] in idioma.IDIOMAS else 0)
        lingua.currentIndexChanged.connect(self._mudar_idioma)
        lay.addWidget(row(_("Idioma"), lingua))
        sair = QPushButton(_("Sair"))
        sair.clicked.connect(self.app_ctl.quit)
        lay.addWidget(row(_("Sair do app"), sair, _("Fecha de vez, inclusive em segundo plano")))
        procurar = QPushButton(_("Procurar atualizações"))
        procurar.clicked.connect(self.app_ctl.procurar_versao)
        lay.addWidget(row(_("Versão do app"), procurar, VERSAO if VERSAO != "0.0.0" else _("Rodando pelo código")))
        v.addWidget(box)
        v.addStretch(1)
        return w

    def _build_luzes(self):
        w, v = page()
        self.lights_page = w
        box, lay = section(_("Barra de luz"))
        self.color_button = ColorButton(self.cfg["color"], _("Cor da barra de luz"))
        self.color_button.color_changed.connect(self._set_color)
        lay.addWidget(row(_("Cor"), self.color_button))
        swatches = QWidget()
        sh = QHBoxLayout(swatches)
        sh.setContentsMargins(0, 0, 0, 0)
        for name, rgb in PRESETS:
            s = Swatch(rgb, _(name))
            s.clicked.connect(lambda _c=False, rgb=rgb: self._set_color(list(rgb)))
            sh.addWidget(s)
        sh.addStretch(1)
        lay.addWidget(swatches)
        self.intensity = ValueSlider(0, 100, self.cfg["intensity"], lambda x: f"{x:.0f}%")
        self.intensity.changed.connect(lambda x: self._set("intensity", int(x)))
        lay.addWidget(row(_("Intensidade"), self.intensity))
        self.lightbar_mode = QComboBox()
        self.lightbar_mode.addItems([_("Cor fixa"), _("Mostrar a bateria")])
        self.lightbar_mode.setCurrentIndex(1 if self.cfg["lightbar_mode"] == "battery" else 0)
        self.lightbar_mode.currentIndexChanged.connect(
            lambda i: self._set("lightbar_mode", "battery" if i == 1 else "fixed"))
        lay.addWidget(row(_("Modo da barra de luz"), self.lightbar_mode,
                          _("Verde, amarelo e vermelho conforme a carga")))
        v.addWidget(box)

        box, lay = section(_("LEDs do jogador"), _("Os cinco pontinhos embaixo do touchpad."))
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
        lay.addWidget(row(_("Acesos"), leds))
        self.led_brightness = QComboBox()
        self.led_brightness.addItems([_("Alto"), _("Médio"), _("Baixo", "brilho")])
        self.led_brightness.setCurrentIndex(self.cfg["led_brightness"])
        self.led_brightness.currentIndexChanged.connect(lambda i: self._set("led_brightness", i))
        lay.addWidget(row(_("Brilho"), self.led_brightness))
        v.addWidget(box)

        box, lay = section(_("Outros"))
        self.mic_led = QComboBox()
        self.mic_led.addItems([_("Apagada"), _("Acesa"), _("Pulsando")])
        self.mic_led.setCurrentIndex(self.cfg["mic_led"])
        self.mic_led.currentIndexChanged.connect(lambda i: self._set("mic_led", i))
        lay.addWidget(row(_("Luz do botão de microfone"), self.mic_led))
        rumble = QPushButton(_("Testar"))
        rumble.clicked.connect(self.session.test_rumble)
        lay.addWidget(row(_("Vibração"), rumble, _("Os dois motores por meio segundo")))
        v.addWidget(box)

        box, self.perfis_layout = section(_("Perfis"),
                                          _("Guardam a luz, os LEDs e os gatilhos para trocar com um clique."))
        entry = QWidget()
        eh = QHBoxLayout(entry)
        eh.setContentsMargins(0, 0, 0, 0)
        self.profile_name = QLineEdit()
        self.profile_name.setPlaceholderText(_("Nome do perfil, ex.: Corrida"))
        self.profile_name.setMaxLength(32)
        self.profile_name.returnPressed.connect(self._save_profile)
        save = QPushButton(_("Salvar atual"))
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
        for side, title in (("l2", _("Gatilho esquerdo (L2)")), ("r2", _("Gatilho direito (R2)"))):
            box, lay = section(title)
            combo = QComboBox()
            combo.addItems([_(m.label) for m in TRIGGER_MODES])
            combo.setCurrentIndex([m.key for m in TRIGGER_MODES].index(self.cfg["triggers"][side]["mode"]))
            combo.currentIndexChanged.connect(lambda i, s=side: self._on_trigger_mode(s, i))
            lay.addWidget(row(_("Efeito"), combo))
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
            lay.addWidget(row(_("Pressão agora"), level, _("Aperte para sentir o efeito")))
            copy = QPushButton(_("Copiar para o outro"))
            copy.clicked.connect(lambda _c=False, s=side: self._copy_trigger(s))
            lay.addWidget(row(_("Mesmo efeito no outro gatilho"), copy))
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
        ui["desc"].setText(_(mode.description))
        values = {**mode.defaults(), **trig.get("params", {})}
        for p in mode.params:
            fmt = (lambda x: f"{x * 10:.0f}%") if p.position else (lambda x: f"{x:.0f}")
            slider = ValueSlider(p.low, p.high, values[p.key], fmt)
            slider.changed.connect(lambda x, s=side, k=p.key: self._on_trigger_param(s, k, x))
            lay.addWidget(row(_(p.label), slider))

    def _build_teste(self):
        w, v = page()
        top = QWidget()
        th = QHBoxLayout(top)
        th.setContentsMargins(0, 0, 0, 0)
        self.hz_label = QLabel("-- Hz")
        restart = QPushButton(_("Recomeçar"))
        restart.clicked.connect(self._restart_test)
        report = QPushButton(_("Gerar relatório"))
        report.clicked.connect(self._report)
        th.addWidget(QLabel(f"<b>{_('Teste do controle')}</b>"))
        th.addStretch(1)
        th.addWidget(self.hz_label)
        th.addWidget(restart)
        th.addWidget(report)
        v.addWidget(top)
        self.test_paused = QLabel(_("Teste pausado: no modo carregar o controle fica fora do sistema."))
        self.test_paused.setVisible(False)
        v.addWidget(self.test_paused)

        box, lay = section(_("Botões"))
        self.buttons_count = QLabel()
        lay.addWidget(self.buttons_count)
        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setSpacing(6)
        self.chips = {}
        for i, (key, label) in enumerate(BUTTONS):
            chip = Chip(_(label))
            self.chips[key] = chip
            grid.addWidget(chip, i // 4, i % 4)
        lay.addWidget(grid_w)
        v.addWidget(box)

        box, lay = section(_("Analógicos"), _("Gire cada analógico encostando na borda para medir a circularidade."))
        sticks = QWidget()
        sh = QHBoxLayout(sticks)
        self.stick_views, self.stick_labels = {}, {}
        for side, name in (("l", _("Esquerdo")), ("r", _("Direito"))):
            col = QVBoxLayout()
            col.addWidget(QLabel(f"<b>{name}</b>"))
            view = StickView(lambda s=side: self.tester.sticks[s])
            col.addWidget(view)
            info = QLabel()
            info.setWordWrap(True)
            col.addWidget(info)
            reset = QPushButton(_("Zerar circularidade"))
            reset.clicked.connect(lambda _c=False, s=side: (self.tester.sticks[s].reset_circle(), self.stick_views[s].update()))
            col.addWidget(reset)
            sh.addLayout(col)
            self.stick_views[side], self.stick_labels[side] = view, info
        lay.addWidget(sticks)
        v.addWidget(box)

        box, lay = section(_("Gatilhos"))
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

        box, lay = section(_("Touchpad"))
        self.touch_view = TouchView()
        lay.addWidget(self.touch_view, 0, Qt.AlignHCenter)
        self.touch_label = QLabel()
        self.touch_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.touch_label)
        v.addWidget(box)

        box, lay = section(_("Movimento"))
        mono = QFont("monospace")
        mono.setStyleHint(QFont.Monospace)
        self.gyro_label = QLabel()
        self.accel_label = QLabel()
        for x in (self.gyro_label, self.accel_label):
            x.setFont(mono)
        lay.addWidget(row(_("Giroscópio"), self.gyro_label, _("graus por segundo")))
        lay.addWidget(row(_("Acelerômetro"), self.accel_label, _("em g")))
        v.addWidget(box)

        box, lay = section(_("Vibração"))
        self.motor = {}
        for key, title in (("left", _("Motor esquerdo (forte)")), ("right", _("Motor direito (fraco)"))):
            s = ValueSlider(0, 255, 180)
            lay.addWidget(row(title, s))
            self.motor[key] = s
        pulses = QWidget()
        ph = QHBoxLayout(pulses)
        ph.setContentsMargins(0, 0, 0, 0)
        ph.addStretch(1)
        for label, which in ((_("Esquerdo"), "left"), (_("Direito"), "right"), (_("Os dois"), "both")):
            b = QPushButton(label)
            b.clicked.connect(lambda _c=False, wh=which: self._pulse(wh))
            ph.addWidget(b)
        lay.addWidget(pulses)
        v.addWidget(box)

        self.audio_box, lay = section(_("Áudio"), _("Funciona com o controle no cabo USB."))
        tones = QWidget()
        toh = QHBoxLayout(tones)
        toh.setContentsMargins(0, 0, 0, 0)
        for label, target in ((_("Tocar no alto-falante"), audio.SPEAKER), (_("Tocar no fone"), audio.HEADPHONES)):
            b = QPushButton(label)
            b.clicked.connect(lambda _c=False, t=target: self._tone(t))
            toh.addWidget(b)
        toh.addStretch(1)
        lay.addWidget(tones)
        self.mic_check = QCheckBox(_("Medir"))
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
        lay.addWidget(row(_("Microfone"), micw, _("Fale perto do controle")))
        self.phone_label = QLabel(_("não"))
        lay.addWidget(row(_("Fone conectado"), self.phone_label))
        v.addWidget(self.audio_box)
        self._refresh_chips(None)
        v.addStretch(1)
        return w

    def _build_info(self):
        w, v = page()
        box, lay = section(_("Informações do controle"), _("Cor, placa e número de série são lidos pelo cabo USB e "
                                                         "ficam guardados para aparecer também no Bluetooth."))
        self.info_labels, self.info_values = {}, {}
        for key, title in INFO_FIELDS:
            value = QLabel(_("Indisponível"))
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            copy = QPushButton(_("Copiar"))
            copy.clicked.connect(lambda _c=False, k=key: self._copy_info(k))
            line = QWidget()
            lh = QHBoxLayout(line)
            lh.setContentsMargins(0, 0, 0, 0)
            if key == "color":
                self.info_dot = Dot()
                lh.addWidget(self.info_dot)
            lh.addWidget(QLabel(f"<b>{_(title)}</b>"))
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

    def _mudar_idioma(self, indice):
        self._set("idioma", idioma.IDIOMAS[indice])
        caixa = QMessageBox(QMessageBox.Question, _("Idioma"), _("O idioma muda quando o app abrir de novo."),
                            parent=self)
        agora = caixa.addButton(_("Reiniciar agora"), QMessageBox.AcceptRole)
        caixa.addButton(_("Depois"), QMessageBox.RejectRole)
        caixa.exec()
        if caixa.clickedButton() is agora:
            self.session.flush_save()
            segundo_plano.reiniciar("dualsense_painel")
            self.app_ctl.quit()

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
        self.toast(_("Efeito copiado"))

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
            modes = " · ".join(f"{s.upper()} {_(MODES_BY_KEY.get(m, MODES_BY_KEY['off']).label).lower()}"
                               for s, m in p["triggers"].items())
            line = QWidget()
            lh = QHBoxLayout(line)
            lh.setContentsMargins(0, 0, 0, 0)
            dot = Dot()
            dot.set_color("#%02x%02x%02x" % tuple(p["color"]))
            lh.addWidget(dot)
            texts = QLabel(f"<b>{p['name']}</b><br><small>{modes}</small>")
            lh.addWidget(texts, 1)
            apply_btn = QPushButton(_("Aplicar"))
            apply_btn.clicked.connect(lambda _c=False, n=p["name"]: self._apply_profile(n))
            delete = QPushButton(_("Apagar", "perfil"))
            delete.clicked.connect(lambda _c=False, n=p["name"]: self._delete_profile(n))
            lh.addWidget(apply_btn)
            lh.addWidget(delete)
            self.perfis_layout.addWidget(line)
            self.profile_rows.append(line)

    def _save_profile(self):
        name = profiles.save(self.cfg, self.profile_name.text())
        if not name:
            self.toast(_("Dê um nome ao perfil"))
            return
        self.profile_name.clear()
        self.changed()
        self._refresh_profiles()
        self.toast(_("Perfil \"{nome}\" salvo").format(nome=name))

    def _apply_profile(self, name):
        if profiles.apply(self.cfg, name):
            self.sync_widgets()
            self.changed()
            self.toast(_("Perfil \"{nome}\" aplicado").format(nome=name))

    def _delete_profile(self, name):
        answer = QMessageBox.question(self, _("Apagar perfil"), _("Apagar o perfil \"{nome}\"?").format(nome=name))
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
        self.battery_status.setText(_(STATUS_PT.get(status, status or N_("bateria desconhecida"))))
        self.connection_label.setText(_("{modelo} pelo {conexao}").format(modelo=ses.model,
                                                                         conexao=_(CONNECTION.get(ses.connection, ""))))
        self.off_row.setVisible(ses.connection == "bluetooth" and ses.pode_desligar_bluetooth)
        self.app_ctl.update_tray()
        if self._current() == _("Informações"):
            self._refresh_info()

    def mode_changed(self):
        on = self.session.charging_mode
        self.mode_label.setText(_("Modo carregar") if on else _("Modo normal"))
        self.mode_button.setText(_("Voltar ao modo normal") if on else _("Entrar no modo carregar"))
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
        if page_name == _("Gatilhos"):
            for side, value in data["triggers"].items():
                self.trigger_ui[side]["level"].setValue(value)
        elif page_name == _("Teste"):
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
            self.estimate.setText(_("Cheio em {tempo}, no ritmo atual.").format(tempo=duration(est["minutes"])))
        elif est and est["kind"] == "empty":
            self.estimate.setText(_("Acaba em {tempo}, no ritmo atual.").format(tempo=duration(est["minutes"])))
        else:
            self.estimate.setText(_("A estimativa aparece depois de alguns minutos de carga ou uso."))
        return True

    def low_battery(self, pct):
        self.app_ctl.notify(_("Bateria do controle baixa"),
                            _("O DualSense está com {pct}%. Hora de ligar no cabo.").format(pct=pct))

    def charged(self):
        self.app_ctl.notify(_("Controle carregado"), _("Pode tirar do cabo ou voltar ao modo normal."))

    def _refresh_chips(self, data):
        for key, chip in self.chips.items():
            chip.set_state(key in self.tester.tested, bool(data and data["buttons"].get(key)))
        self.buttons_count.setText(
            _("{testados} de {total} testados. Cada botão fica verde depois de apertado uma vez.").format(
                testados=len(self.tester.tested), total=len(BUTTONS)))

    def _update_test(self, data):
        self.tester.record(data)
        self._refresh_chips(data)
        for side in ("l", "r"):
            st = self.tester.sticks[side]
            coverage, error = st.circularity()
            rest = (_("repouso {valor}%").format(valor=_fmt(st.rest * 100)) if st.rest is not None
                    else _("medindo repouso"))
            circ = (_("circularidade {valor}% de erro").format(valor=_fmt(error * 100)) if error is not None
                    else _("gire para medir"))
            self.stick_labels[side].setText(
                _("X {x}  Y {y}\n{repouso} · {drift}\n{circularidade} · contorno {contorno}%").format(
                    x=st.raw[0], y=st.raw[1], repouso=rest, drift=_(DRIFT_TEXT.get(st.drift(), N_("medindo drift"))),
                    circularidade=circ, contorno=f"{coverage * 100:.0f}"))
            self.stick_views[side].update()
        for side in ("l2", "r2"):
            value, best = data["triggers"][side], self.tester.max[side]
            self.test_bars[side].setValue(value)
            self.test_trigger_labels[side].setText(
                _("agora {valor} · máximo {maximo}").format(valor=value, maximo=best)
                + (" · " + _("curso completo") if best >= 255 else ""))
        self.touch_view.touch = data["touch"]
        self.touch_view.click = data["buttons"].get("touchpad", False)
        self.touch_view.update()
        active = sum(1 for t in data["touch"] if t["active"])
        self.touch_label.setText(_("{ativos} dedo(s) agora · até {vistos} visto(s) · clique {clique}").format(
            ativos=active, vistos=self.tester.touch_seen, clique="ok" if self.tester.click_seen else _("não testado")))
        self.gyro_label.setText("  ".join(f"{x:+7.1f}" for x in data["gyro"]))
        self.accel_label.setText("  ".join(f"{x:+6.2f}" for x in data["accel"]))
        self.phone_label.setText(_("sim") if data.get("headphones") else _("não"))
        self.hz_label.setText(f"{self.session.report_hz} Hz")

    def _restart_test(self):
        self.tester.reset()
        self._refresh_chips(None)
        for view in self.stick_views.values():
            view.update()
        self.toast(_("Teste recomeçado"))

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
            self.toast(_("Áudio do controle não encontrado"))

    def _mic_toggled(self, on):
        if on and not self.mic:
            self.mic = audio.MicMeter(lambda level: self.session.loop.idle_add(self._mic_level, level))
            if not self.mic.start():
                self.mic = None
                self.mic_check.setChecked(False)
                self.toast(_("Microfone do controle não encontrado"))
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
        battery = (f"{pct}%, {_(STATUS_PT.get(status, status or ''))}".rstrip(", ") if pct is not None
                   else _("indisponível"))
        text = self.tester.report(ses.info, battery, ses.report_hz)
        name = f"relatorio-dualsense-{time.strftime('%Y%m%d-%H%M')}.md"
        path, _ = QFileDialog.getSaveFileName(self, _("Salvar relatório"), name, "Markdown (*.md)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self.toast(_("Relatório salvo em {caminho}").format(caminho=path))
        except OSError as e:
            self.toast(_("Não consegui salvar: {erro}").format(erro=e.strerror))

    def _info_value(self, key):
        ses, info = self.session, self.session.info or {}
        if key == "connection":
            text = _(CONNECTION.get(ses.connection, ""))
            return text[:1].upper() + text[1:] if text else None
        if key == "hz":
            return f"{ses.report_hz} Hz" if ses.report_hz else None
        if key == "battery":
            if ses.battery_pct is None:
                return None
            return f"{ses.battery_pct}%, {_(STATUS_PT.get(ses.battery_status, ''))}".rstrip(", ")
        if key == "model":
            return info.get("model") or ses.model
        if key == "color":
            if info.get("colorPt"):
                english = info.get("color")
                nome = _(info["colorPt"])
                return nome + (f" ({english})" if english and english != nome else "")
            return _("Código {codigo}").format(codigo=info["colorCode"]) if info.get("colorCode") else None
        value = info.get(key)
        return str(value) if value else None

    def _refresh_info(self):
        for key, label in self.info_labels.items():
            value = self._info_value(key)
            self.info_values[key] = value
            label.setText(value or _("Indisponível"))
        self.info_dot.set_color((self.session.info or {}).get("colorHex"))

    def _copy_info(self, key):
        value = self.info_values.get(key)
        if value:
            QGuiApplication.clipboard().setText(value)
            self.toast(_("Copiado"))

    def closeEvent(self, event):
        if self.cfg["segundo_plano"] or (self.session.charging_mode and self.session.connected):
            event.ignore()
            self.hide()
            self.app_ctl.avisar_fundo()
            return
        self.stop_mic()
        self.session.cleanup()
        event.accept()
        self.app_ctl.quit()
