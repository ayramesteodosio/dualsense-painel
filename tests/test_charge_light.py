import unittest

from dualsense_painel import charge_light as cl


def cfg(**kw):
    return {**cl.DEFAULTS, **kw}


class ChargeLightTest(unittest.TestCase):
    def test_breathe_goes_from_dim_to_full_color(self):
        c = cfg(charge_period=4.0)
        self.assertEqual(cl.lightbar(c, "Charging", 2.0), (255, 80, 0))
        self.assertLess(max(cl.lightbar(c, "Charging", 0.0)), 20)

    def test_speed_changes_the_cycle(self):
        self.assertEqual(cl.lightbar(cfg(charge_period=2.0), "Charging", 1.0), (255, 80, 0))
        self.assertNotEqual(cl.lightbar(cfg(charge_period=8.0), "Charging", 1.0), (255, 80, 0))

    def test_custom_color_and_intensity(self):
        c = cfg(charge_color=[0, 0, 200], charge_style="solid", charge_intensity=50)
        self.assertEqual(cl.lightbar(c, "Charging", 0.3), (0, 0, 100))

    def test_blink(self):
        c = cfg(charge_style="blink", charge_period=2.0)
        self.assertEqual(cl.lightbar(c, "Charging", 0.5), (255, 80, 0))
        self.assertEqual(cl.lightbar(c, "Charging", 1.5), (0, 0, 0))

    def test_when_full(self):
        self.assertEqual(cl.lightbar(cfg(charge_full="off"), "Full", 1.0), (0, 0, 0))
        self.assertEqual(cl.lightbar(cfg(charge_full="green"), "Full", 1.0), cl.FULL_GREEN)
        self.assertNotEqual(cl.lightbar(cfg(charge_full="keep", charge_style="solid"), "Full", 1.0), (0, 0, 0))

    def test_dark_when_disabled_or_not_charging(self):
        self.assertEqual(cl.lightbar(cfg(charge_glow=False), "Charging", 2.5), (0, 0, 0))
        self.assertEqual(cl.lightbar(cfg(), "Discharging", 2.5), (0, 0, 0))

    def test_animated(self):
        self.assertTrue(cl.animated(cfg(), "Charging"))
        self.assertFalse(cl.animated(cfg(charge_style="solid"), "Charging"))
        self.assertFalse(cl.animated(cfg(), "Full"))
        self.assertTrue(cl.animated(cfg(charge_full="keep"), "Full"))


if __name__ == "__main__":
    unittest.main()


class MigracaoTest(unittest.TestCase):
    def test_apagar_antigo_vira_verde(self):
        import json
        import os
        import tempfile
        from dualsense_painel import config
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.json")
            with open(path, "w") as f:
                json.dump({"charge_full": "off"}, f)
            self.assertEqual(config.load(path)["charge_full"], "green")
            with open(path, "w") as f:
                json.dump({"charge_full": "off", "versao_config": 2}, f)
            self.assertEqual(config.load(path)["charge_full"], "off")
