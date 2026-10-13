import unittest
import zlib

from dualsense_painel import protocol as p


class EffectsTest(unittest.TestCase):
    def test_off(self):
        self.assertEqual(p.effect_off(), bytes([0x05] + [0] * 10))

    def test_feedback_full_travel(self):
        e = p.effect_feedback(0, 8)
        self.assertEqual(e[:3], bytes([0x21, 0xFF, 0x03]))
        self.assertEqual(int.from_bytes(e[3:7], "little"), 0x3FFFFFFF)

    def test_feedback_from_middle(self):
        e = p.effect_feedback(5, 1)
        self.assertEqual(int.from_bytes(e[1:3], "little"), 0b1111100000)
        self.assertEqual(int.from_bytes(e[3:7], "little"), 0)

    def test_weapon(self):
        self.assertEqual(p.effect_weapon(3, 6, 8)[:4], bytes([0x25, 0x48, 0x00, 0x07]))

    def test_weapon_fixes_end_before_start(self):
        e = p.effect_weapon(7, 2, 1)
        self.assertEqual(int.from_bytes(e[1:3], "little"), (1 << 7) | (1 << 8))

    def test_bow(self):
        e = p.effect_bow(1, 6, 6, 4)
        self.assertEqual(e[:4], bytes([0x22, 0x42, 0x00, 5 | (3 << 3)]))

    def test_vibration_frequency_slot(self):
        e = p.effect_vibration(0, 8, 40)
        self.assertEqual(e[0], 0x26)
        self.assertEqual(e[9], 40)

    def test_galloping(self):
        e = p.effect_galloping(0, 9, 1, 4, 3)
        self.assertEqual(e[:5], bytes([0x23, 0x01, 0x02, 4 | (1 << 3), 3]))

    def test_machine(self):
        e = p.effect_machine(0, 9, 2, 7, 20, 5)
        self.assertEqual(e[:6], bytes([0x27, 0x01, 0x02, 2 | (7 << 3), 20, 5]))

    def test_every_mode_encodes_its_defaults(self):
        for mode in p.TRIGGER_MODES:
            self.assertEqual(len(mode.encode(mode.defaults())), p.TRIGGER_SIZE, mode.key)


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.state = p.OutputState(lightbar=(1, 2, 3), player_leds=0b10101,
                                   right_trigger=p.effect_weapon(3, 6, 8))

    def test_usb_layout(self):
        r = p.build_report(self.state)
        self.assertEqual(len(r), p.USB_REPORT_SIZE)
        self.assertEqual(r[0], 0x02)
        common = r[1:]
        self.assertEqual(common[p.OFF_LIGHTBAR:p.OFF_LIGHTBAR + 3], bytes([1, 2, 3]))
        self.assertEqual(common[p.OFF_PLAYER_LEDS], 0b10101 | p.PLAYER_LEDS_INSTANT)
        self.assertEqual(common[p.OFF_RIGHT_TRIGGER], 0x25)
        self.assertEqual(common[p.OFF_LEFT_TRIGGER], 0x05)
        self.assertFalse(common[p.OFF_FLAG0] & p.FLAG0_COMPATIBLE_VIBRATION)

    def test_rumble_only_when_asked(self):
        self.state.rumble = (200, 50)
        common = p.build_report(self.state)[1:]
        self.assertTrue(common[p.OFF_FLAG0] & p.FLAG0_COMPATIBLE_VIBRATION)
        self.assertEqual((common[p.OFF_MOTOR_LEFT], common[p.OFF_MOTOR_RIGHT]), (200, 50))

    def test_bluetooth_crc_and_sequence(self):
        r = p.build_report(self.state, bluetooth=True, seq=3)
        self.assertEqual(len(r), p.BT_REPORT_SIZE)
        self.assertEqual(r[:3], bytes([0x31, 0x30, 0x10]))
        self.assertEqual(r[3:3 + p.COMMON_SIZE], p.build_report(self.state)[1:1 + p.COMMON_SIZE])
        self.assertEqual(int.from_bytes(r[-4:], "little"), zlib.crc32(b"\xa2" + r[:-4]))

    def test_dark_state_turns_everything_off(self):
        common = p.build_common(p.dark_state())
        self.assertEqual(common[p.OFF_LIGHTBAR:p.OFF_LIGHTBAR + 3], bytes(3))
        self.assertEqual(common[p.OFF_PLAYER_LEDS] & 0x1F, 0)
        self.assertEqual(common[p.OFF_MIC_LED], 0)


if __name__ == "__main__":
    unittest.main()
