"""Real OpenGL shader/buffer tests; Linux EGL or Windows GLFW, never a mock."""
import math
import unittest
from dataclasses import replace

from colourlab.core import Settings, MODES, PATTERNS, PRESETS, apply_preset, linear_to_srgb, quantise, srgb_to_linear
from colourlab.diagnostics import check_source_precision
from colourlab.gl import GL, Renderer, GL_RGBA16F
from tests.graphics_context import GraphicsContext


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = GraphicsContext()
        cls.gl = GL(cls.context.get_proc_address)
        cls.renderer = Renderer(cls.gl)
        cls.target = cls.renderer.create_target(384, 96)

    @classmethod
    def tearDownClass(cls):
        cls.renderer.close()
        cls.context.close()

    def render(self, settings, seconds=0):
        self.renderer.draw(self.target, settings, seconds=seconds)
        return self.renderer.read_pixels(self.target)

    def pixel(self, data, x, y):
        index = (y * self.target.width + x) * 4
        return tuple(data[index:index+4])

    def test_actual_float_format(self):
        self.assertEqual(self.target.internal_format, GL_RGBA16F)
        self.assertEqual(self.target.channel_bits, [16, 16, 16, 16])

    def test_source_precision(self):
        result = check_source_precision(self.renderer)
        self.assertEqual(result["unique_red_levels"]["8bit"], 256)
        self.assertEqual(result["unique_red_levels"]["10bit"], 1024)
        self.assertGreater(result["unique_red_levels"]["reference"], 1024)

    def test_compare_top_bottom(self):
        base = Settings(labels=False, start_rgb=(0, 0, 0), end_rgb=(1, 1, 1))
        eight = self.render(replace(base, mode="8bit"))
        ten = self.render(replace(base, mode="10bit"))
        comp = self.render(replace(base, mode="compare"))
        swap = self.render(replace(base, mode="compare", swap=True))
        for x in range(0, self.target.width, 7):
            self.assertEqual(self.pixel(comp, x, 75), self.pixel(eight, x, 75))
            self.assertEqual(self.pixel(comp, x, 20), self.pixel(ten, x, 20))
            self.assertEqual(self.pixel(swap, x, 75), self.pixel(ten, x, 75))
            self.assertEqual(self.pixel(swap, x, 20), self.pixel(eight, x, 20))

    def test_three_section_order(self):
        base = Settings(labels=False, start_rgb=(0, 0, 0), end_rgb=(1, 1, 1))
        expected = [self.render(replace(base, mode=mode)) for mode in ("8bit", "10bit", "reference")]
        comp = self.render(replace(base, mode="three"))
        for i, y in enumerate((80, 48, 16)):
            for x in range(0, self.target.width, 11):
                self.assertEqual(self.pixel(comp, x, y), self.pixel(expected[i], x, y))

    def test_vertical_restarts_in_each_section(self):
        s = Settings(labels=False, pattern="vertical", start_rgb=(0, 0, 0), end_rgb=(1, 1, 1))
        values = self.render(s)
        for y in range(self.target.height):
            bits = 8 if y >= 48 else 10
            local = (y % 48 + .5) / 48
            expected = quantise(local, bits)
            actual = linear_to_srgb(self.pixel(values, 190, y)[0])
            self.assertAlmostEqual(actual, expected, delta=.0005)

    def test_dither_is_deterministic_and_bounded(self):
        s = Settings(mode="dither8", pattern="solid", labels=False, start_rgb=(.4007, .2632, .1731))
        first, second = self.render(s), self.render(s)
        self.assertEqual(first.tobytes(), second.tobytes())
        for channel in range(3):
            encoded = [linear_to_srgb(x) for x in first[channel::4]]
            self.assertAlmostEqual(sum(encoded)/len(encoded), s.start_rgb[channel], delta=.00015)
            self.assertLess(max(encoded)-min(encoded), 1/255+.0005)

    def test_motion_changes_pattern_but_static_ignores_time(self):
        s = Settings(labels=False, mode="10bit")
        self.assertEqual(self.render(s, 0).tobytes(), self.render(s, 5).tobytes())
        self.assertNotEqual(self.render(replace(s, animate=True), 0).tobytes(),
                            self.render(replace(s, animate=True), 5).tobytes())

    def test_all_presets(self):
        for name in PRESETS:
            s = replace(apply_preset(Settings(), name), labels=False, mode="10bit")
            data = self.render(s)
            for x in (0, 100, 200, 383):
                pixel = self.pixel(data, x, 48)
                self.assertEqual(pixel[3], 1)
                for ch in range(3):
                    t = (x+.5)/self.target.width
                    expected = quantise(s.start_rgb[ch]*(1-t)+s.end_rgb[ch]*t, 10)
                    self.assertAlmostEqual(linear_to_srgb(pixel[ch]), expected, delta=.0005, msg=name)

    def test_all_patterns_modes_and_labels(self):
        for pattern in PATTERNS:
            for mode in MODES:
                for labels in (False, True):
                    with self.subTest(pattern=pattern, mode=mode, labels=labels):
                        data = self.render(Settings(pattern=pattern, mode=mode, labels=labels))
                        self.assertTrue(all(math.isfinite(x) and 0 <= x <= 1 for x in data))
                        self.assertTrue(all(x == 1 for x in data[3::4]))

    def test_no_gl_errors(self):
        self.gl.check("test completion")


if __name__ == "__main__":
    unittest.main()
