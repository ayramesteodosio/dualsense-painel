import os
import tempfile
import unittest

from dualsense_painel import factory


class FactoryTest(unittest.TestCase):
    def test_decode_white_bdm030(self):
        d = factory.decode("F3AB00CDEFGHIJKLM")
        self.assertEqual((d["color"], d["colorPt"], d["board"], d["colorCode"]),
                         ("White", "Branco", "BDM-030", "00"))

    def test_decode_special_edition_and_unknown(self):
        self.assertEqual(factory.decode("F5ABZ2xxxx")["color"], "Spider-Man 2")
        d = factory.decode("F9ABQQxxxx")
        self.assertIsNone(d["color"])
        self.assertIsNone(d["board"])
        self.assertIsNone(factory.decode("F3"))

    def test_supported_gate(self):
        self.assertTrue(factory.supported("0x00000513", "0x0110002a"))
        self.assertFalse(factory.supported("0x00000200", "0x0110002a"))
        self.assertFalse(factory.supported(None, "0x0110002a"))

    def test_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.json")
            factory.remember("AA:BB", {"board": "BDM-030"}, path)
            self.assertEqual(factory.load_cache(path), {"AA:BB": {"board": "BDM-030"}})


if __name__ == "__main__":
    unittest.main()


class AtualizacaoTest(unittest.TestCase):
    def resposta(self, tag):
        import io
        import json

        class Resposta(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return lambda pedido, timeout, context: Resposta(json.dumps({"tag_name": tag, "html_url": "u"}).encode())

    def test_compara_versoes(self):
        from dualsense_painel import atualizacao
        self.assertEqual(atualizacao.mais_nova("r", "0.1.2", self.resposta("v0.1.10")), ("0.1.10", "u"))
        self.assertIsNone(atualizacao.mais_nova("r", "0.1.2", self.resposta("v0.1.2")))
        self.assertIsNone(atualizacao.mais_nova("r", "0.2.0", self.resposta("v0.1.9")))
