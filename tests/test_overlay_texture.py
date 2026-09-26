"""Real GPU overlay uploads/readback, without starting or calling SteamVR."""
import ctypes as C
import sys
import unittest
from unittest.mock import patch

import openvr
from PIL import Image

from colourlab.diagnostics import check_source_precision
from colourlab.gl import (GL, Renderer, I, U, GL_TEXTURE_2D, GL_RGBA,
                          GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_FRAMEBUFFER_COMPLETE)
from colourlab.overlay_texture import OverlayTexture
from tests.graphics_context import GraphicsContext


class OverlayTextureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = GraphicsContext()
        cls.gl = GL(cls.context.get_proc_address)
        prototype = C.WINFUNCTYPE if sys.platform == "win32" else C.CFUNCTYPE
        cls.is_texture = prototype(C.c_ubyte, U)(cls.context.get_proc_address("glIsTexture"))

    @classmethod
    def tearDownClass(cls):
        cls.context.close()

    def setUp(self):
        self.texture = OverlayTexture(self.gl, openvr)
        self.addCleanup(self.texture.close)

    def readback(self):
        """Read attached GPU storage in native bottom-to-top framebuffer order."""
        width, height = self.texture.size
        framebuffer = U()
        self.gl.GenFramebuffers(1, C.byref(framebuffer))
        try:
            self.gl.BindFramebuffer(GL_FRAMEBUFFER, framebuffer.value)
            self.gl.FramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D,
                                         self.texture.name.value, 0)
            self.assertEqual(self.gl.CheckFramebufferStatus(GL_FRAMEBUFFER), GL_FRAMEBUFFER_COMPLETE)
            pixels = (C.c_ubyte * (width * height * 4))()
            self.gl.ReadPixels(0, 0, width, height, GL_RGBA, 0x1401, C.cast(pixels, C.c_void_p))
            self.gl.check("test overlay texture readback")
            return bytes(pixels)
        finally:
            self.gl.BindFramebuffer(GL_FRAMEBUFFER, 0)
            self.gl.DeleteFramebuffers(1, C.byref(framebuffer))

    def texture_parameter(self, parameter):
        value = I()
        self.gl.BindTexture(GL_TEXTURE_2D, self.texture.name.value)
        try:
            self.gl.GetTexLevelParameteriv(GL_TEXTURE_2D, 0, parameter, C.byref(value))
            self.gl.check("test overlay texture format")
            return value.value
        finally:
            self.gl.BindTexture(GL_TEXTURE_2D, 0)

    def test_gpu_rgba8_retains_encoded_pixels_and_flips_pillow_rows_for_opengl(self):
        # 2 distinguishable rows, including alpha and midtones, catch inversion,
        # channel swapping, and accidental sRGB-to-linear conversion on upload.
        top = bytes((255, 0, 0, 255, 0, 128, 0, 64))
        bottom = bytes((0, 0, 255, 128, 17, 33, 65, 255))
        image = Image.frombytes("RGBA", (2, 2), top + bottom)
        submitted = self.texture.update(image)
        self.assertEqual(submitted.handle, self.texture.name.value)
        self.assertEqual(submitted.eType, openvr.TextureType_OpenGL)
        self.assertEqual(submitted.eColorSpace, openvr.ColorSpace_Gamma)
        self.assertEqual(self.texture_parameter(0x1003), 0x8058)  # GL_RGBA8
        self.assertEqual([self.texture_parameter(p) for p in (0x805C, 0x805D, 0x805E, 0x805F)], [8] * 4)
        self.assertEqual(self.readback(), bottom + top)

    def test_same_size_update_changes_gpu_pixels_without_reallocating_storage(self):
        first = Image.new("RGBA", (3, 2), (19, 39, 59, 255))
        second = Image.new("RGBA", (3, 2), (201, 141, 81, 127))
        with patch.object(self.gl, "TexImage2D", wraps=self.gl.TexImage2D) as allocate, \
                patch.object(self.gl, "TexSubImage2D", wraps=self.gl.TexSubImage2D) as update, \
                patch.object(self.gl, "GenTextures", wraps=self.gl.GenTextures) as generate, \
                patch.object(self.gl, "DeleteTextures", wraps=self.gl.DeleteTextures) as delete:
            submitted = self.texture.update(first)
            name = self.texture.name.value
            before = self.readback()
            self.assertIs(self.texture.update(second), submitted)
            self.assertEqual(self.texture.name.value, name)
            self.assertEqual(self.readback(), second.tobytes())
            self.assertNotEqual(self.readback(), before)
            self.assertEqual(allocate.call_count, 1)
            self.assertEqual(update.call_count, 1)
            generate.assert_not_called()
            delete.assert_not_called()

    def test_resize_rejected_before_gl_calls_preserves_content_and_cleanup_deletes_once(self):
        original = Image.new("RGB", (2, 2), (31, 63, 127))
        self.texture.update(original)
        name = self.texture.name.value
        self.assertTrue(self.is_texture(name))
        before = self.readback()
        self.assertEqual(before, original.convert("RGBA").tobytes())
        resized = Image.new("RGBA", (5, 3), "red")
        with patch.object(self.gl, "ActiveTexture", wraps=self.gl.ActiveTexture) as active, \
                patch.object(self.gl, "BindTexture", wraps=self.gl.BindTexture) as bind, \
                patch.object(self.gl, "TexImage2D", wraps=self.gl.TexImage2D) as allocate, \
                patch.object(self.gl, "TexSubImage2D", wraps=self.gl.TexSubImage2D) as update:
            with self.assertRaises(ValueError):
                self.texture.update(resized)
            active.assert_not_called()
            bind.assert_not_called()
            allocate.assert_not_called()
            update.assert_not_called()
        self.assertEqual(self.texture.name.value, name)
        self.assertEqual(self.texture.size, (2, 2))
        self.assertEqual(self.texture_parameter(0x1000), 2)  # GL_TEXTURE_WIDTH
        self.assertEqual(self.texture_parameter(0x1001), 2)  # GL_TEXTURE_HEIGHT
        self.assertEqual(self.readback(), before)
        with patch.object(self.gl, "DeleteTextures", wraps=self.gl.DeleteTextures) as delete:
            self.texture.close()
            self.texture.close()
            self.assertEqual(delete.call_count, 1)
        self.assertFalse(self.is_texture(name))
        self.assertEqual(self.texture.name.value, 0)
        self.gl.check("test rejected overlay resize and cleanup")

    def test_overlay_uploads_leave_float_source_precision_unchanged(self):
        renderer = Renderer(self.gl)
        try:
            before = check_source_precision(renderer)
            self.texture.update(Image.new("RGBA", (4, 3), (11, 55, 99, 127)))
            self.texture.update(Image.new("RGBA", (4, 3), (99, 55, 11, 255)))
            after = check_source_precision(renderer)
            self.assertEqual(after, before)
            self.assertEqual(after["unique_red_levels"]["8bit"], 256)
            self.assertEqual(after["unique_red_levels"]["10bit"], 1024)
            self.assertGreater(after["unique_red_levels"]["reference"], 1024)
            self.assertEqual(after["channel_bits"], [16] * 4)
        finally:
            renderer.close()


if __name__ == "__main__":
    unittest.main()
