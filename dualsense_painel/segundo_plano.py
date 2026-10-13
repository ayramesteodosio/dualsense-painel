import os
import shlex
import socket
import subprocess
import sys
import tempfile
import threading
import time

from . import plataforma

APPS = {"dualsense-painel": ("Painel do DualSense", "com.ayrames.DualSensePainel"),
        "dualsense-studio": ("DualSense Studio", "com.ayrames.DualSenseStudio")}
FLAG = "--segundo-plano"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _outro(repo):
    return next(r for r in APPS if r != repo)


def _arquivo_linux(repo):
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "autostart", APPS[repo][1] + ".desktop")


def _arquivo_mac(repo):
    return os.path.expanduser(f"~/Library/LaunchAgents/{APPS[repo][1]}.plist")


def comando(repo, raiz=None):
    if getattr(sys, "frozen", False):
        return [sys.executable, FLAG]
    if plataforma.LINUX and raiz and os.path.isfile(os.path.join(raiz, repo)):
        return [os.path.join(raiz, repo), FLAG]
    return [repo, FLAG]


def _winreg():
    import winreg
    return winreg


def ativo(repo):
    if plataforma.WINDOWS:
        reg = _winreg()
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY) as chave:
                reg.QueryValueEx(chave, APPS[repo][0])
            return True
        except OSError:
            return False
    return os.path.isfile(_arquivo_mac(repo) if plataforma.MACOS else _arquivo_linux(repo))


def _escrever(repo, partes):
    nome, app_id = APPS[repo]
    if plataforma.WINDOWS:
        reg = _winreg()
        linha = " ".join(f'"{p}"' if " " in p else p for p in partes)
        with reg.CreateKey(reg.HKEY_CURRENT_USER, RUN_KEY) as chave:
            reg.SetValueEx(chave, nome, 0, reg.REG_SZ, linha)
        return
    if plataforma.MACOS:
        import plistlib
        caminho = _arquivo_mac(repo)
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with open(caminho, "wb") as f:
            plistlib.dump({"Label": app_id, "ProgramArguments": partes, "RunAtLoad": True}, f)
        return
    caminho = _arquivo_linux(repo)
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    linha = " ".join(f'"{p}"' if " " in p else p for p in partes)
    with open(caminho, "w") as f:
        f.write(f"[Desktop Entry]\nType=Application\nName={nome}\nExec={linha}\nIcon={app_id}\n"
                "Terminal=false\nX-GNOME-Autostart-enabled=true\n")


def _apagar(repo):
    if plataforma.WINDOWS:
        reg = _winreg()
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as chave:
                reg.DeleteValue(chave, APPS[repo][0])
        except OSError:
            pass
        return
    try:
        os.remove(_arquivo_mac(repo) if plataforma.MACOS else _arquivo_linux(repo))
    except OSError:
        pass


def definir(repo, ligado, raiz=None):
    if ligado:
        _apagar(_outro(repo))
        _escrever(repo, comando(repo, raiz))
    else:
        _apagar(repo)


def reiniciar(pacote, raiz=None):
    if getattr(sys, "frozen", False):
        partes = [sys.executable]
    else:
        partes = [sys.executable, "-m", pacote]
    pid = os.getpid()
    if plataforma.WINDOWS:
        argumentos = ", ".join("'" + p.replace("'", "''") + "'" for p in partes[1:])
        script = (f"Wait-Process -Id {pid} -ErrorAction SilentlyContinue; "
                  f"Start-Process -FilePath '{partes[0]}'" + (f" -ArgumentList {argumentos}" if argumentos else "")
                  + (f" -WorkingDirectory '{raiz}'" if raiz else ""))
        subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
                         creationflags=0x08000000, close_fds=True)
        return
    linha = " ".join(shlex.quote(p) for p in partes)
    pasta = f"cd {shlex.quote(raiz)} && " if raiz else ""
    script = f"while kill -0 {pid} 2>/dev/null; do sleep 0.2; done; {pasta}exec {linha}"
    subprocess.Popen(["/bin/sh", "-c", script], start_new_session=True, close_fds=True)


def _caminho_canal():
    caminho = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir(), plataforma.APP + ".sock")
    if len(caminho.encode()) > 100:
        caminho = os.path.join("/tmp", f"{plataforma.APP}-{os.getuid()}.sock")
    return caminho


class Canal:
    def __init__(self, repo, lock, ao_comando):
        self.repo = repo
        self.ao_comando = ao_comando
        try:
            if plataforma.LINUX:
                caminho = _caminho_canal()
                try:
                    os.remove(caminho)
                except OSError:
                    pass
                self.servidor = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.servidor.bind(caminho)
            else:
                self.servidor = lock
            self.servidor.listen(4)
        except OSError:
            self.servidor = None
            return
        threading.Thread(target=self._aceitar, daemon=True).start()

    def _aceitar(self):
        while True:
            try:
                conexao, _ = self.servidor.accept()
            except OSError:
                return
            with conexao:
                try:
                    conexao.settimeout(2)
                    pedido = conexao.recv(256).decode("utf-8", "ignore").split()
                    if len(pedido) == 2:
                        resposta = "ok" if pedido[0] == self.repo else "saindo"
                        conexao.sendall(resposta.encode())
                        self.ao_comando("mostrar" if resposta == "ok" else "sair")
                except OSError:
                    pass


def enviar(repo, pedido="abrir", tempo=3):
    try:
        if plataforma.LINUX:
            cliente = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            endereco = _caminho_canal()
        else:
            cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            endereco = ("127.0.0.1", plataforma.LOCK_PORT)
        with cliente:
            cliente.settimeout(tempo)
            cliente.connect(endereco)
            cliente.sendall(f"{repo} {pedido}".encode())
            return cliente.recv(64).decode("utf-8", "ignore").strip() or None
    except OSError:
        return None


def obter_controle(repo, escondido=False, espera=8.0):
    lock = plataforma.acquire_lock()
    if lock is not None:
        return "livre", lock
    if escondido:
        return "ocupado", None
    resposta = enviar(repo)
    if resposta == "ok":
        return "mostrado", None
    if resposta == "saindo":
        limite = time.monotonic() + espera
        while time.monotonic() < limite:
            time.sleep(0.25)
            lock = plataforma.acquire_lock()
            if lock is not None:
                return "livre", lock
    return "ocupado", None
