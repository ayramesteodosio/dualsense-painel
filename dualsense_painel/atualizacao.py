import json
import os
import platform
import shlex
import ssl
import subprocess
import sys
import tempfile
import threading
import urllib.request

from . import plataforma
from .idioma import _

DONO = "ayramesteodosio"
BASES = {"dualsense-painel": "Painel-DualSense", "dualsense-studio": "DualSense-Studio"}
APPS = {"dualsense-painel": "Painel do DualSense", "dualsense-studio": "DualSense Studio"}
_RELEASES = {}


def numeros(versao):
    partes = []
    for parte in str(versao).lstrip("v").split("."):
        digitos = "".join(c for c in parte if c.isdigit())
        partes.append(int(digitos) if digitos else 0)
    return tuple(partes)


def _contexto():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def mais_nova(repo, atual, abrir=urllib.request.urlopen):
    pedido = urllib.request.Request(f"https://api.github.com/repos/{DONO}/{repo}/releases/latest",
                                    headers={"Accept": "application/vnd.github+json", "User-Agent": repo})
    with abrir(pedido, timeout=10, context=_contexto()) as resposta:
        dados = json.load(resposta)
    tag = str(dados.get("tag_name", "")).lstrip("v")
    _RELEASES[repo] = dados
    if tag and numeros(tag) > numeros(atual):
        return tag, dados.get("html_url") or f"https://github.com/{DONO}/{repo}/releases/latest"
    return None


def verificar(repo, atual, quando_houver, quando_nao=None):
    if quando_nao is None and numeros(atual) == (0, 0, 0):
        return

    def trabalho():
        try:
            achou = mais_nova(repo, atual)
        except Exception:
            if quando_nao:
                quando_nao(False)
            return
        if achou:
            quando_houver(*achou)
        elif quando_nao:
            quando_nao(True)
    threading.Thread(target=trabalho, daemon=True).start()


def texto_sem_novidade(encontrou, atual):
    if not encontrou:
        return _("Não consegui procurar atualizações agora. Confira a conexão com a internet.")
    return _("Você já está na versão mais nova ({versao}).").format(versao=atual)


def nome_do_arquivo(repo, tag):
    base = BASES[repo]
    if plataforma.WINDOWS:
        return f"{base}-windows.exe"
    if plataforma.MACOS:
        return f"{base}-macos-{'arm64' if platform.machine() == 'arm64' else 'intel'}.dmg"
    return f"{repo}_{tag}_all.deb"


def pode_instalar(repo):
    if plataforma.WINDOWS or plataforma.MACOS:
        return bool(getattr(sys, "frozen", False))
    pasta = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return pasta == f"/usr/share/{repo}" and bool(_procurar("pkexec"))


def _procurar(programa):
    for pasta in os.environ.get("PATH", "/usr/bin").split(os.pathsep):
        caminho = os.path.join(pasta, programa)
        if os.access(caminho, os.X_OK):
            return caminho
    return None


def _endereco(repo, tag):
    nome = nome_do_arquivo(repo, tag)
    for arquivo in (_RELEASES.get(repo) or {}).get("assets", []):
        if arquivo.get("name") == nome:
            return arquivo.get("browser_download_url"), nome
    return f"https://github.com/{DONO}/{repo}/releases/download/v{tag}/{nome}", nome


def baixar(repo, tag, progresso, pronto, falhou):
    def trabalho():
        try:
            url, nome = _endereco(repo, tag)
            pasta = tempfile.mkdtemp(prefix="dualsense-")
            destino = os.path.join(pasta, nome)
            pedido = urllib.request.Request(url, headers={"User-Agent": repo})
            with urllib.request.urlopen(pedido, timeout=30, context=_contexto()) as resposta, open(destino, "wb") as f:
                total = int(resposta.headers.get("Content-Length") or 0)
                feito = 0
                while True:
                    bloco = resposta.read(256 * 1024)
                    if not bloco:
                        break
                    f.write(bloco)
                    feito += len(bloco)
                    if total:
                        progresso(min(1.0, feito / total))
            pronto(destino)
        except Exception as e:
            falhou(str(e))
    threading.Thread(target=trabalho, daemon=True).start()


def _pacote_mac():
    caminho = os.path.abspath(sys.executable)
    while caminho != "/" and not caminho.endswith(".app"):
        caminho = os.path.dirname(caminho)
    return caminho if caminho.endswith(".app") else None


def instalar(repo, caminho):
    pid = os.getpid()
    if plataforma.WINDOWS:
        argumentos = "'/SILENT','/SUPPRESSMSGBOXES','/NORESTART','/CLOSEAPPLICATIONS','/FORCECLOSEAPPLICATIONS'"
        instalador = caminho.replace("'", "''")
        script = (f"Wait-Process -Id {pid} -Timeout 30 -ErrorAction SilentlyContinue; "
                  f"Start-Sleep -Milliseconds 500; Start-Process -FilePath '{instalador}' -ArgumentList {argumentos}")
        subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
                         creationflags=0x08000000 | 0x00000200, close_fds=True)
        return True
    if plataforma.MACOS:
        pacote = _pacote_mac()
        if not pacote:
            return False
        nome = APPS[repo] + ".app"
        script = (f"while kill -0 {pid} 2>/dev/null; do sleep 0.3; done; "
                  f"ponto=$(mktemp -d); hdiutil attach -nobrowse -quiet -mountpoint \"$ponto\" {shlex.quote(caminho)} && "
                  f"rm -rf {shlex.quote(pacote)} && ditto \"$ponto\"/{shlex.quote(nome)} {shlex.quote(pacote)}; "
                  f"hdiutil detach -quiet \"$ponto\"; open {shlex.quote(pacote)}")
        subprocess.Popen(["/bin/sh", "-c", script], start_new_session=True, close_fds=True)
        return True
    script = (f"while kill -0 {pid} 2>/dev/null; do sleep 0.3; done; "
              f"pkexec env DEBIAN_FRONTEND=noninteractive apt-get install -y {shlex.quote(caminho)}; "
              f"setsid {shlex.quote(repo)} >/dev/null 2>&1 &")
    subprocess.Popen(["/bin/sh", "-c", script], start_new_session=True, close_fds=True)
    return True
