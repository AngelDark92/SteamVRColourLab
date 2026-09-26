"""Pure-Python numerical and configuration tests."""
import json
import math
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from colourlab.core import (Settings, PRESETS, apply_preset, from_openvr, gl_matrix,
                            hue_endpoints, identity, linear_to_srgb, matmul, panel_model,
                            quantise, rigid_inverse, srgb_to_linear)


class CoreTests(unittest.TestCase):
    def test_srgb_roundtrip(self):
        for i in range(1025):
            s = i / 1024
            self.assertAlmostEqual(linear_to_srgb(srgb_to_linear(s)), s, places=12)

    def test_quantisation_level_count(self):
        for bits in (8, 10):
            samples = [quantise(i / 8192, bits) for i in range(8193)]
            self.assertEqual(len(set(samples)), 1 << bits)
            self.assertEqual(samples[0], 0)
            self.assertEqual(samples[-1], 1)
            self.assertEqual(samples, sorted(samples))

    def test_quantisation_half_up(self):
        for bits in (8, 10):
            n = (1 << bits) - 1
            self.assertEqual(quantise(0.5/n, bits), 1/n)
            self.assertEqual(quantise(-10, bits), 0)
            self.assertEqual(quantise(10, bits), 1)

    def test_invalid_precision(self):
        with self.assertRaises(ValueError):
            quantise(0.5, 9)

    def test_48_presets(self):
        self.assertEqual(len(PRESETS), 48)
        for name in PRESETS:
            s = apply_preset(Settings(mode="10bit", codec="test"), name)
            self.assertEqual(s.mode, "10bit")
            self.assertEqual(s.codec, "test")
            self.assertEqual(s.pattern, "horizontal")
            s.validate()

    def test_hues(self):
        for h in range(0, 361, 15):
            a, b = hue_endpoints(h, .8, .02, .2)
            self.assertAlmostEqual(max(a), .02)
            self.assertAlmostEqual(max(b), .2)
        self.assertEqual(hue_endpoints(0, 1, 0, 1), hue_endpoints(360, 1, 0, 1))

    def test_config_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "settings.json"
            original = Settings(mode="10bit", start_rgb=(0.00123, 0.02456, 0.12678), notes="A/B test")
            original.save(p)
            self.assertEqual(Settings.load(p), original)

    def test_invalid_configs(self):
        for data in (
            {"start_rgb": [0, 0]}, {"end_rgb": [0, 0, 1.1]}, {"start_rgb": [True, 0, 0]},
            {"start_rgb": [float("nan"), 0, 0]}, {"panel_width": -1}, {"mode": "HDR"},
            {"pattern": "image"}, {"labels": "false"}, {"saturation": float("inf")},
            {"stream_depth_requested": "confirmed"}, {"unexpected": 1}, {"notes": 42},
        ):
            with self.subTest(data=data), self.assertRaises(ValueError):
                Settings.from_dict(data)

    def test_matrix_identity(self):
        i = identity()
        self.assertEqual(matmul(i, i), i)
        self.assertEqual(rigid_inverse(i), i)

    def test_rigid_transform_inverse(self):
        for angle in (0, .4, -1.7, math.pi):
            c, s = math.cos(angle), math.sin(angle)
            m = [[c, 0, s, 1.3], [0, 1, 0, 1.7], [-s, 0, c, -.8], [0, 0, 0, 1]]
            for product in (matmul(m, rigid_inverse(m)), matmul(rigid_inverse(m), m)):
                for row in range(4):
                    for col in range(4):
                        self.assertAlmostEqual(product[row][col], float(row == col), places=12)

    def test_openvr_matrix_conversion(self):
        m = SimpleNamespace(m=((1, 0, 0, 2), (0, 1, 0, 3), (0, 0, 1, 4)))
        result = from_openvr(m)
        self.assertEqual(result[3], [0, 0, 0, 1])
        self.assertEqual(gl_matrix(result)[12:15], [2, 3, 4])

    def test_recenter_model(self):
        anchor = identity()
        anchor[0][3], anchor[1][3] = 4, 1.6
        model = panel_model(anchor, Settings())
        view_model = matmul(rigid_inverse(anchor), model)
        self.assertAlmostEqual(view_model[0][3], 0)
        self.assertAlmostEqual(view_model[1][3], 0)
        self.assertAlmostEqual(view_model[2][3], -2.5)


if __name__ == "__main__":
    unittest.main()
