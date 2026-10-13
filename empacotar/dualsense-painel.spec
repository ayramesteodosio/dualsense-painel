import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
ICON = os.path.join(ROOT, "empacotar", "icones", "dualsense-painel.ico" if sys.platform.startswith("win") else "dualsense-painel.icns")

a = Analysis(
    [os.path.join(ROOT, "empacotar", "iniciar.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "dados", "com.ayrames.DualSensePainel.svg"), "dados")],
    hiddenimports=["dualsense_painel.backends.hidapi_backend", "dualsense_painel.backends.hidhide",
                   "dualsense_painel.audio_portable", "hid", "PySide6.QtSvg"],
    excludes=["gi", "dualsense_painel.app", "dualsense_painel.telas", "dualsense_painel.audio_pulse",
              "pkg_resources", "setuptools", "tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Painel do DualSense", console=False,
          icon=ICON if os.path.exists(ICON) else None)
coll = COLLECT(exe, a.binaries, a.datas, name="Painel do DualSense")
if sys.platform == "darwin":
    app = BUNDLE(coll, name="Painel do DualSense.app", icon=ICON if os.path.exists(ICON) else None,
                 bundle_identifier="com.ayrames.DualSensePainel",
                 info_plist={"NSHighResolutionCapable": True, "LSUIElement": False,
                             "NSMicrophoneUsageDescription": "Medir o microfone do controle no teste de áudio.",
                             "NSBluetoothAlwaysUsageDescription": "Desligar o controle pelo Bluetooth."})
