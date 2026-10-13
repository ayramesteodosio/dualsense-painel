import glob
import os
import unittest

from tests.verificar_traducao import problemas, traducoes

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TraducaoTest(unittest.TestCase):
    def test_todo_texto_tem_traducao(self):
        pacote = os.path.join(RAIZ, "dualsense_painel")
        arquivos = [f for padrao in ("*.py", "telas/*.py", "qt/*.py", "backends/*.py")
                    for f in glob.glob(os.path.join(pacote, padrao))]
        self.assertEqual(problemas(arquivos, traducoes(os.path.join(pacote, "traducoes"))), [])
