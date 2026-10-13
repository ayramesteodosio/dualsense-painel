import os
import sys


def registro():
    if sys.stdout is not None and sys.stderr is not None:
        return
    from dualsense_painel import plataforma
    pasta = plataforma.data_dir()
    os.makedirs(pasta, exist_ok=True)
    arquivo = open(os.path.join(pasta, "registro.txt"), "w", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or arquivo
    sys.stderr = sys.stderr or arquivo


registro()

from dualsense_painel.qt.main import main

sys.exit(main())
