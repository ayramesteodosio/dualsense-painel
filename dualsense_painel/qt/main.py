import os
import signal
import sys

from PySide6.QtCore import QLibraryInfo, QLocale, QObject, QTimer, QTranslator, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .. import atualizacao, plataforma, segundo_plano
from ..versao import VERSAO
from ..session import acquire_lock

SERVER = "dualsense-painel-qt"
APP_ID = "com.ayrames.DualSensePainel"


def resource(*parts):
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, *parts)


def send_command(command):
    sock = QLocalSocket()
    sock.connectToServer(SERVER)
    if not sock.waitForConnected(800):
        return False
    sock.write(command.encode())
    sock.flush()
    sock.waitForBytesWritten(800)
    sock.disconnectFromServer()
    return True


class _Aviso(QObject):
    pronto = Signal(str, str)
    nada = Signal(bool)
    progresso = Signal(float)
    baixado = Signal(str)
    falhou = Signal(str)
    canal = Signal(str)


class AppCtl:
    def __init__(self, app, start_mode, escondido=False):
        from .janela import Janela
        self.app = app
        self.icon = QIcon(resource("dados", APP_ID + ".svg"))
        app.setWindowIcon(self.icon)
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.icon)
            self.tray.setToolTip("Painel do DualSense")
            menu = QMenu()
            self.open_action = QAction("Abrir o painel")
            self.open_action.triggered.connect(self.show)
            self.mode_action = QAction("Entrar no modo carregar")
            self.mode_action.triggered.connect(self.toggle_mode)
            quit_action = QAction("Sair")
            quit_action.triggered.connect(self.quit)
            for action in (self.open_action, self.mode_action, quit_action):
                menu.addAction(action)
            self.menu = menu
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda reason: reason == QSystemTrayIcon.Trigger and self.show())
            self.tray.show()
        self.server = QLocalServer()
        QLocalServer.removeServer(SERVER)
        self.server.listen(SERVER)
        self.server.newConnection.connect(self._command)
        self.window = Janela(self)
        if not escondido:
            self.window.show()
        if start_mode is not None:
            QTimer.singleShot(1500, lambda: self.window.set_charging(start_mode))
        self._url_versao = None
        self._avisou_fundo = False
        self.aviso = _Aviso()
        self.aviso.canal.connect(lambda comando: self.show() if comando == "mostrar" else self.quit())
        self.aviso.pronto.connect(self._nova_versao)
        self.aviso.nada.connect(lambda achou: self.window.toast(atualizacao.texto_sem_novidade(achou, VERSAO)))
        self.aviso.progresso.connect(lambda f: self.window.progresso_versao(self._tag_versao, f))
        self.aviso.baixado.connect(self._baixado)
        self.aviso.falhou.connect(lambda e: self.window.falha_versao(e, self._abrir_versao))
        self._tag_versao = None
        if self.tray:
            self.tray.messageClicked.connect(self.show)
        QTimer.singleShot(5000, self._checar_versao)
        self.timer_versao = QTimer()
        self.timer_versao.setInterval(24 * 3600 * 1000)
        self.timer_versao.timeout.connect(self._checar_versao)
        self.timer_versao.start()

    def _checar_versao(self):
        atualizacao.verificar("dualsense-painel", VERSAO, self.aviso.pronto.emit)

    def procurar_versao(self):
        atualizacao.verificar("dualsense-painel", VERSAO, self.aviso.pronto.emit, self.aviso.nada.emit)

    def _nova_versao(self, tag, url):
        self._url_versao = url
        self._tag_versao = tag
        if not self.window.isVisible():
            self.notify(f"Versão {tag} disponível", "Abra o painel para atualizar.")
        if self.tray and not getattr(self, "acao_versao", None):
            acao = QAction(f"Atualizar para a versão {tag}")
            acao.triggered.connect(self.show)
            self.menu.insertAction(self.menu.actions()[0], acao)
            self.acao_versao = acao
        self.window.aviso_versao(tag, atualizacao.pode_instalar("dualsense-painel"), self._atualizar,
                                 self._abrir_versao)

    def _atualizar(self):
        self.window.progresso_versao(self._tag_versao, 0)
        atualizacao.baixar("dualsense-painel", self._tag_versao, self.aviso.progresso.emit, self.aviso.baixado.emit,
                           self.aviso.falhou.emit)

    def _baixado(self, caminho):
        self.window.instalando_versao(self._tag_versao)
        if atualizacao.instalar("dualsense-painel", caminho):
            QTimer.singleShot(600, self.quit)
        else:
            self.window.falha_versao("não deu para instalar sozinho", self._abrir_versao)

    def _abrir_versao(self):
        if self._url_versao:
            QDesktopServices.openUrl(QUrl(self._url_versao))

    def avisar_fundo(self):
        if not self._avisou_fundo:
            self._avisou_fundo = True
            self.notify("O painel continua rodando", "Ele segue na bandeja do sistema. Para fechar de vez, use Sair.")

    def tray_available(self):
        return self.tray is not None

    def show(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def toggle_mode(self):
        self.window.set_charging(not self.window.session.charging_mode)

    def update_tray(self):
        if self.tray:
            on = self.window.session.charging_mode if hasattr(self, "window") else False
            self.mode_action.setText("Voltar ao modo normal" if on else "Entrar no modo carregar")
            pct = self.window.session.battery_pct if hasattr(self, "window") else None
            self.tray.setToolTip("Painel do DualSense" + (f": {pct}%" if pct is not None else ""))

    def notify(self, title, body):
        if self.tray:
            self.tray.showMessage(title, body, self.icon, 5000)
        else:
            self.window.toast(f"{title}. {body}")

    def _command(self):
        sock = self.server.nextPendingConnection()
        if not sock:
            return

        def read():
            command = bytes(sock.readAll()).decode(errors="ignore").strip()
            if command == "carregar":
                self.window.set_charging(True)
            elif command == "normal":
                self.window.set_charging(False)
            else:
                self.show()
        sock.readyRead.connect(read)

    def quit(self):
        if getattr(self, "_saindo", False):
            return
        self._saindo = True
        try:
            self.window.stop_mic()
            self.window.session.cleanup()
        finally:
            self.app.quit()


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    mode = True if "--carregar" in argv else False if "--normal" in argv else None
    QApplication.setApplicationName("Painel do DualSense")
    QApplication.setDesktopFileName(APP_ID)
    escondido = segundo_plano.FLAG in argv
    app = QApplication([a for a in argv if a not in ("--carregar", "--normal", segundo_plano.FLAG)])
    if plataforma.WINDOWS:
        app.setStyle("Fusion")
    traducao = QTranslator(app)
    if traducao.load(QLocale("pt_BR"), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(traducao)
    app.setQuitOnLastWindowClosed(False)
    lock = acquire_lock()
    if lock is None:
        if escondido:
            return 0
        if send_command({True: "carregar", False: "normal"}.get(mode, "mostrar")):
            return 0
        estado, lock = segundo_plano.obter_controle("dualsense-painel")
        if estado != "livre":
            QMessageBox.information(None, "Painel do DualSense", "Não consegui assumir o controle. Feche o outro app "
                                                                 "do DualSense e tente de novo.")
            return 1
    ctl = AppCtl(app, mode, escondido)
    segundo_plano.Canal("dualsense-painel", lock, ctl.aviso.canal.emit)
    signal.signal(signal.SIGINT, lambda *_: ctl.quit())
    signal.signal(signal.SIGTERM, lambda *_: ctl.quit())
    keepalive = QTimer()
    keepalive.timeout.connect(lambda: None)
    keepalive.start(300)
    code = app.exec()
    del lock
    return code


if __name__ == "__main__":
    sys.exit(main())
