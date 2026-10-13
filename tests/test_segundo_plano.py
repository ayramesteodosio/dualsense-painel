import os
import plistlib
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

from dualsense_painel import plataforma, segundo_plano as sp


def winreg_falso():
    valores = {}
    mod = types.ModuleType("winreg")
    mod.HKEY_CURRENT_USER = "HKCU"
    mod.KEY_SET_VALUE = 2
    mod.REG_SZ = 1

    class Chave:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    mod.OpenKey = lambda *a: Chave()
    mod.CreateKey = lambda *a: Chave()

    def consultar(_chave, nome):
        if nome not in valores:
            raise OSError
        return valores[nome], 1

    def apagar(_chave, nome):
        if nome not in valores:
            raise OSError
        del valores[nome]

    mod.QueryValueEx = consultar
    mod.SetValueEx = lambda _c, nome, _r, _t, dado: valores.__setitem__(nome, dado)
    mod.DeleteValue = apagar
    return mod, valores


@unittest.skipUnless(plataforma.LINUX, "caminhos do Linux")
class AutostartLinuxTest(unittest.TestCase):
    def test_liga_desliga_e_exclusivo(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": d}):
            sp.definir("dualsense-studio", True)
            self.assertTrue(sp.ativo("dualsense-studio"))
            sp.definir("dualsense-painel", True, raiz="/opt/x")
            self.assertTrue(sp.ativo("dualsense-painel"))
            self.assertFalse(sp.ativo("dualsense-studio"))
            with open(os.path.join(d, "autostart", "com.ayrames.DualSensePainel.desktop")) as f:
                texto = f.read()
            self.assertIn("Exec=dualsense-painel --segundo-plano", texto)
            sp.definir("dualsense-painel", False)
            self.assertFalse(sp.ativo("dualsense-painel"))


class AutostartOutrosTest(unittest.TestCase):
    def test_windows_registro(self):
        mod, valores = winreg_falso()
        with mock.patch.object(plataforma, "WINDOWS", True), mock.patch.object(plataforma, "LINUX", False), \
                mock.patch.object(sp, "_winreg", lambda: mod), mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "executable", r"C:\Programas\Painel do DualSense\Painel do DualSense.exe"):
            sp.definir("dualsense-studio", True)
            sp.definir("dualsense-painel", True)
            self.assertEqual(valores, {"Painel do DualSense":
                                       '"C:\\Programas\\Painel do DualSense\\Painel do DualSense.exe" --segundo-plano'})
            self.assertTrue(sp.ativo("dualsense-painel"))
            sp.definir("dualsense-painel", False)
            self.assertFalse(sp.ativo("dualsense-painel"))

    def test_macos_launchagent(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"HOME": d, "USERPROFILE": d}), \
                mock.patch.object(plataforma, "MACOS", True), mock.patch.object(plataforma, "LINUX", False), \
                mock.patch.object(plataforma, "WINDOWS", False), mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "executable", "/Applications/DualSense Studio.app/Contents/MacOS/DualSense Studio"):
            sp.definir("dualsense-studio", True)
            caminho = os.path.join(d, "Library", "LaunchAgents", "com.ayrames.DualSenseStudio.plist")
            with open(caminho, "rb") as f:
                dados = plistlib.load(f)
            self.assertEqual(dados["ProgramArguments"][-1], "--segundo-plano")
            self.assertTrue(dados["RunAtLoad"])
            sp.definir("dualsense-studio", False)
            self.assertFalse(os.path.exists(caminho))


@unittest.skipUnless(plataforma.LINUX, "canal por soquete Unix")
class CanalTest(unittest.TestCase):
    def test_mesmo_app_mostra_e_outro_app_assume(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": d}):
            estado, lock = sp.obter_controle("dualsense-painel")
            self.assertEqual(estado, "livre")
            comandos = []

            def ao_comando(c):
                comandos.append(c)
                if c == "sair":
                    def soltar():
                        time.sleep(0.3)
                        os.close(lock)
                    threading.Thread(target=soltar).start()

            sp.Canal("dualsense-painel", lock, ao_comando)
            self.assertEqual(sp.enviar("dualsense-studio", "sair"), "outro")
            self.assertEqual(sp.obter_controle("dualsense-painel"), ("mostrado", None))
            self.assertEqual(sp.obter_controle("dualsense-studio", escondido=True), ("ocupado", None))
            estado, novo = sp.obter_controle("dualsense-studio")
            self.assertEqual(estado, "livre")
            self.assertEqual(comandos, ["mostrar", "sair"])
            os.close(novo)
