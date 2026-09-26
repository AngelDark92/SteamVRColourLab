"""Persistent GPU texture for UI overlays; separate from RGBA16F eye targets."""
from __future__ import annotations

import ctypes

from PIL import Image

from .gl import GL_TEXTURE_2D, GL_TEXTURE0, GL_RGBA, U


class OverlayTexture:
    def __init__(self, gl, vr):
        self.gl = gl
        self.name = U()
        self.size = None
        gl.GenTextures(1, ctypes.byref(self.name))
        self.texture = vr.Texture_t()
        self.texture.handle = self.name.value
        self.texture.eType = vr.TextureType_OpenGL
        self.texture.eColorSpace = vr.ColorSpace_Gamma

    def update(self, image):
        # SteamVR can cache the imported GL storage. Never resize a texture
        # after publishing its handle; use another persistent texture instead.
        if self.size is not None and self.size != image.size:
            raise ValueError("Overlay texture dimensions cannot change after allocation.")
        # Upload Pillow's top-left rows in OpenGL's bottom-up storage order.
        # SteamVR's pointer coordinates already match the displayed UI.
        image = image.convert("RGBA").transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        pixels = image.tobytes()
        data = ctypes.create_string_buffer(pixels, len(pixels))
        g = self.gl
        g.ActiveTexture(GL_TEXTURE0)
        g.BindTexture(GL_TEXTURE_2D, self.name.value)
        try:
            if self.size is None:
                for key, value in ((0x2801, 0x2601), (0x2800, 0x2601), (0x2802, 0x812F), (0x2803, 0x812F)):
                    g.TexParameteri(GL_TEXTURE_2D, key, value)
                g.TexImage2D(GL_TEXTURE_2D, 0, 0x8058, image.width, image.height, 0,
                             GL_RGBA, 0x1401, ctypes.cast(data, ctypes.c_void_p))
                self.size = image.size
            else:
                # Updating highlights/settings never destroys/reloads an image.
                g.TexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, image.width, image.height,
                                GL_RGBA, 0x1401, ctypes.cast(data, ctypes.c_void_p))
        finally:
            g.BindTexture(GL_TEXTURE_2D, 0)
        g.check("VR controls texture upload")
        g.Flush()
        return self.texture

    def close(self):
        if self.name.value:
            self.gl.DeleteTextures(1, ctypes.byref(self.name))
            self.name.value = 0
