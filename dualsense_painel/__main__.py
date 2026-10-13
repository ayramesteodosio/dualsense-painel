import os
import sys

from . import plataforma


def run():
    if plataforma.LINUX and os.environ.get("DS_PAINEL_UI") != "qt":
        from .app import main
    else:
        from .qt.main import main
    return main()


sys.exit(run())
