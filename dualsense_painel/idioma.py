import glob
import json
import os
import subprocess

from . import plataforma

IDIOMAS = ("auto", "pt", "en")
PASTAS = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "traducoes")]
_traducoes = {}
_atual = "pt"


def _sistema_windows():
    try:
        import ctypes
        return ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x16
    except (AttributeError, OSError):
        return False


def _sistema_mac():
    try:
        saida = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True, text=True,
                               timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    for linha in saida.splitlines():
        linha = linha.strip().strip(",").strip('"')
        if linha and linha not in "()":
            return linha.lower().startswith("pt")
    return False


def _sistema_linux():
    for nome in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        valor = os.environ.get(nome)
        if valor:
            return valor.split(":")[0].lower().startswith("pt")
    return False


def do_sistema():
    if plataforma.WINDOWS:
        portugues = _sistema_windows()
    elif plataforma.MACOS:
        portugues = _sistema_mac()
    else:
        portugues = _sistema_linux()
    return "pt" if portugues else "en"


def carregar(*pastas):
    for pasta in pastas:
        if pasta not in PASTAS:
            PASTAS.append(pasta)
    _traducoes.clear()
    for pasta in PASTAS:
        for arquivo in sorted(glob.glob(os.path.join(pasta, "*.json"))):
            with open(arquivo, encoding="utf-8") as f:
                _traducoes.update(json.load(f))


def definir(preferencia):
    global _atual
    _atual = preferencia if preferencia in ("pt", "en") else do_sistema()
    if not _traducoes:
        carregar()
    return _atual


def atual():
    return _atual


def _(texto, contexto=None):
    if _atual == "pt":
        return texto
    if contexto and f"{contexto}|{texto}" in _traducoes:
        return _traducoes[f"{contexto}|{texto}"]
    return _traducoes.get(texto, texto)


def N_(texto):
    return texto
