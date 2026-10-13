import json
import ssl
import threading
import urllib.request

DONO = "ayramesteodosio"


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
    if tag and numeros(tag) > numeros(atual):
        return tag, dados.get("html_url") or f"https://github.com/{DONO}/{repo}/releases/latest"
    return None


def verificar(repo, atual, quando_houver):
    if numeros(atual) == (0, 0, 0):
        return

    def trabalho():
        try:
            achou = mais_nova(repo, atual)
        except Exception:
            return
        if achou:
            quando_houver(*achou)
    threading.Thread(target=trabalho, daemon=True).start()
