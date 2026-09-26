"""Tk control checks. On Linux run under xvfb-run; no SteamVR required."""
import unittest
from colourlab.core import Settings, MODES, PATTERNS
from colourlab.ui import Controls


class FakeApp:
    def __init__(self): self.settings = Settings()
    def change(self, settings, reason): self.settings = settings.validate()
    def stop(self): pass
    def recenter(self): pass
    def save_report(self): pass
    def set_cycle(self, enabled): pass
    def note(self, text): pass


class UITests(unittest.TestCase):
    def setUp(self):
        self.app = FakeApp()
        self.ui = Controls(self.app)
        self.ui.pump()
    def tearDown(self): self.ui.close()

    def test_default_readback(self):
        self.assertEqual(self.ui.read(), self.app.settings)

    def test_custom_fractional_rgb(self):
        self.ui.rgb_vars[0][0].set("0.0123456789")
        self.ui.mode.set(MODES["10bit"])
        self.assertTrue(self.ui.apply())
        self.assertEqual(self.app.settings.start_rgb[0], .0123456789)
        self.assertEqual(self.app.settings.mode, "10bit")

    def test_invalid_input_keeps_last_valid_configuration(self):
        initial = self.app.settings
        self.ui.rgb_vars[0][0].set("not a number")
        self.assertFalse(self.ui.apply())
        self.assertEqual(self.app.settings, initial)

    def test_hue_and_atlas_controls(self):
        self.ui.hsv_vars["hue"].set("120")
        self.ui.hsv_vars["saturation"].set("1")
        self.ui.make_hue()
        self.assertAlmostEqual(self.app.settings.end_rgb[1], .2)
        self.assertAlmostEqual(self.app.settings.end_rgb[0], 0)
        self.ui.show_atlas()
        self.assertEqual(self.app.settings.pattern, "atlas")

    def test_selected_preset_updates_navigation_index(self):
        from colourlab.core import PRESETS
        name = list(PRESETS)[17]
        self.ui.preset.set(name)
        self.ui.choose_preset()
        self.assertEqual(self.app.preset_index, 17)
        self.assertEqual(self.app.settings.start_rgb, PRESETS[name][0])

    def test_stream_request_does_not_change_source_mode(self):
        self.ui.depth.set("10")
        self.assertTrue(self.ui.apply())
        self.assertEqual(self.app.settings.mode, "compare")
        self.assertEqual(self.app.settings.stream_depth_requested, "10")


if __name__ == "__main__":
    unittest.main()
