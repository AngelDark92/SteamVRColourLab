"""Small typed OpenGL loader and renderer; GLFW supplies the live context.

Using ctypes keeps the application dependencies to GLFW and OpenVR. The same
renderer is exercised by the EGL tests; no alternative 'test shader' is used.
"""
from __future__ import annotations

import ctypes as C
import sys
from array import array
from dataclasses import dataclass

from . import shaders
from .core import Settings, gl_matrix, identity

U, I, F, P = C.c_uint, C.c_int, C.c_float, C.c_void_p
UI, II = C.POINTER(U), C.POINTER(I)
FLOATS = C.POINTER(F)
GL_TEXTURE_2D = 0x0DE1
GL_RGBA16F = 0x881A
GL_RGBA = 0x1908
GL_FLOAT = 0x1406
GL_FRAMEBUFFER = 0x8D40
GL_COLOR_ATTACHMENT0 = 0x8CE0
GL_FRAMEBUFFER_COMPLETE = 0x8CD5
GL_COLOR_BUFFER_BIT = 0x4000
GL_TRIANGLES = 0x0004
GL_TEXTURE0 = 0x84C0


class GL:
    def __init__(self, get_proc_address):
        prototype = C.WINFUNCTYPE if sys.platform == "win32" else C.CFUNCTYPE
        # Result type, then argument types. All calls are explicitly typed.
        functions = {
            "GetString": (C.c_char_p, U), "GetError": (U,),
            "GetIntegerv": (None, U, II), "Disable": (None, U),
            "GenTextures": (None, I, UI), "DeleteTextures": (None, I, UI),
            "BindTexture": (None, U, U), "ActiveTexture": (None, U),
            "TexParameteri": (None, U, U, I),
            "TexImage2D": (None, U, I, I, I, I, I, U, U, P),
            "TexSubImage2D": (None, U, I, I, I, I, I, U, U, P),
            "GetTexLevelParameteriv": (None, U, I, U, II),
            "GenFramebuffers": (None, I, UI), "DeleteFramebuffers": (None, I, UI),
            "BindFramebuffer": (None, U, U),
            "FramebufferTexture2D": (None, U, U, U, U, I),
            "CheckFramebufferStatus": (U, U),
            "Viewport": (None, I, I, I, I), "ClearColor": (None, F, F, F, F),
            "Clear": (None, U), "Flush": (None,), "Finish": (None,),
            "CreateShader": (U, U), "ShaderSource": (None, U, I, C.POINTER(C.c_char_p), II),
            "CompileShader": (None, U), "GetShaderiv": (None, U, U, II),
            "GetShaderInfoLog": (None, U, I, II, P), "DeleteShader": (None, U),
            "CreateProgram": (U,), "AttachShader": (None, U, U), "LinkProgram": (None, U),
            "GetProgramiv": (None, U, U, II), "GetProgramInfoLog": (None, U, I, II, P),
            "DeleteProgram": (None, U), "UseProgram": (None, U),
            "GetUniformLocation": (I, U, C.c_char_p),
            "Uniform1i": (None, I, I), "Uniform1f": (None, I, F),
            "Uniform3f": (None, I, F, F, F),
            "UniformMatrix4fv": (None, I, I, C.c_ubyte, FLOATS),
            "GenVertexArrays": (None, I, UI), "DeleteVertexArrays": (None, I, UI),
            "BindVertexArray": (None, U), "DrawArrays": (None, U, I, I),
            "ReadPixels": (None, I, I, I, I, U, U, P),
        }
        self._functions = []  # Retain native function wrappers for their lifetime.
        for name, signature in functions.items():
            address = get_proc_address("gl" + name)
            if not address:
                raise RuntimeError(f"OpenGL function gl{name} is unavailable. OpenGL 3.3 is required.")
            func = prototype(signature[0], *signature[1:])(address)
            self._functions.append(func)
            setattr(self, name, func)

    def check(self, label: str) -> None:
        error = self.GetError()
        if error:
            raise RuntimeError(f"OpenGL error 0x{error:04x} during {label}.")

    def info(self) -> dict:
        return {name: (self.GetString(enum) or b"unknown").decode("utf-8", "replace")
                for name, enum in (("vendor", 0x1F00), ("renderer", 0x1F01),
                                   ("version", 0x1F02), ("glsl", 0x8B8C))}

    def compile_program(self, vertex: str, fragment: str) -> int:
        shader_ids = []
        program = 0
        try:
            for shader_type, source in ((0x8B31, vertex), (0x8B30, fragment)):
                shader = self.CreateShader(shader_type)
                if not shader:
                    raise RuntimeError("OpenGL could not allocate a shader.")
                shader_ids.append(shader)
                text = C.c_char_p(source.encode("utf-8"))
                self.ShaderSource(shader, 1, C.byref(text), None)
                self.CompileShader(shader)
                status = I()
                self.GetShaderiv(shader, 0x8B81, C.byref(status))
                if not status.value:
                    log = C.create_string_buffer(16384)
                    self.GetShaderInfoLog(shader, len(log), None, log)
                    raise RuntimeError("Shader compilation failed:\n" + log.value.decode("utf-8", "replace"))
            program = self.CreateProgram()
            for shader in shader_ids:
                self.AttachShader(program, shader)
            self.LinkProgram(program)
            status = I()
            self.GetProgramiv(program, 0x8B82, C.byref(status))
            if not status.value:
                log = C.create_string_buffer(16384)
                self.GetProgramInfoLog(program, len(log), None, log)
                raise RuntimeError("Shader linking failed:\n" + log.value.decode("utf-8", "replace"))
            return program
        except Exception:
            if program:
                self.DeleteProgram(program)
            raise
        finally:
            for shader in shader_ids:
                self.DeleteShader(shader)


@dataclass
class Target:
    texture: int
    framebuffer: int
    width: int
    height: int
    internal_format: int
    channel_bits: list[int]


class Renderer:
    def __init__(self, gl: GL):
        self.gl = gl
        self.targets: list[Target] = []
        self.program = 0
        self.preview_program = 0
        self.vao = U()
        self._uniforms = {}
        try:
            self.program = gl.compile_program(shaders.VERTEX, shaders.FRAGMENT)
            self.preview_program = gl.compile_program(shaders.PREVIEW_VERTEX, shaders.PREVIEW_FRAGMENT)
            gl.GenVertexArrays(1, C.byref(self.vao))
            # Neither the float eye buffers nor the desktop preview use automatic
            # sRGB writes. Both conversions are explicit in the corresponding shader.
            for flag in (0x8DB9, 0x0BD0, 0x0BE2, 0x0B71, 0x0B44, 0x809D):
                gl.Disable(flag)  # FRAMEBUFFER_SRGB, DITHER, BLEND, DEPTH, CULL, MSAA
            gl.check("renderer initialisation")
        except Exception:
            self.close()
            raise

    def create_target(self, width: int, height: int) -> Target:
        g = self.gl
        max_size = I()
        g.GetIntegerv(0x0D33, C.byref(max_size))
        if min(width, height) < 1 or max(width, height) > max_size.value:
            raise ValueError(f"Invalid render target {width}x{height}; maximum dimension {max_size.value}.")
        tex, fbo = U(), U()
        try:
            g.GenTextures(1, C.byref(tex))
            g.BindTexture(GL_TEXTURE_2D, tex.value)
            # A single level; no mipmaps and no app-side texture compression.
            for param, value in ((0x2801, 0x2600), (0x2800, 0x2600),
                                 (0x2802, 0x812F), (0x2803, 0x812F)):
                g.TexParameteri(GL_TEXTURE_2D, param, value)
            g.TexImage2D(GL_TEXTURE_2D, 0, GL_RGBA16F, width, height, 0, GL_RGBA, GL_FLOAT, None)
            fmt = I()
            g.GetTexLevelParameteriv(GL_TEXTURE_2D, 0, 0x1003, C.byref(fmt))
            bits = []
            for pname in (0x805C, 0x805D, 0x805E, 0x805F):
                value = I()
                g.GetTexLevelParameteriv(GL_TEXTURE_2D, 0, pname, C.byref(value))
                bits.append(value.value)
            if fmt.value != GL_RGBA16F or bits != [16, 16, 16, 16]:
                raise RuntimeError(f"RGBA16F unavailable: actual format {fmt.value:#x}, channel bits {bits}. No 8-bit fallback.")
            g.GenFramebuffers(1, C.byref(fbo))
            g.BindFramebuffer(GL_FRAMEBUFFER, fbo.value)
            g.FramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex.value, 0)
            status = g.CheckFramebufferStatus(GL_FRAMEBUFFER)
            if status != GL_FRAMEBUFFER_COMPLETE:
                raise RuntimeError(f"Float framebuffer is incomplete: {status:#x}.")
            g.check("float render target creation")
            target = Target(tex.value, fbo.value, width, height, fmt.value, bits)
            self.targets.append(target)
            return target
        except Exception:
            if fbo.value:
                g.DeleteFramebuffers(1, C.byref(fbo))
            if tex.value:
                g.DeleteTextures(1, C.byref(tex))
            raise
        finally:
            g.BindFramebuffer(GL_FRAMEBUFFER, 0)
            g.BindTexture(GL_TEXTURE_2D, 0)

    def loc(self, name: str, program=None) -> int:
        program = self.program if program is None else program
        key = program, name
        if key not in self._uniforms:
            self._uniforms[key] = self.gl.GetUniformLocation(program, name.encode("ascii"))
        return self._uniforms[key]

    def draw(self, target: Target, settings: Settings, mvp=None, seconds: float = 0) -> None:
        g = self.gl
        for flag in (0x8DB9, 0x0BD0, 0x0BE2, 0x0B71, 0x0B44, 0x809D):
            g.Disable(flag)  # Reassert state after the compositor has used the context.
        g.BindFramebuffer(GL_FRAMEBUFFER, target.framebuffer)
        g.Viewport(0, 0, target.width, target.height)
        g.ClearColor(0.001, 0.001, 0.001, 1.0)
        g.Clear(GL_COLOR_BUFFER_BIT)
        g.UseProgram(self.program)
        matrix = (F * 16)(*gl_matrix(identity() if mvp is None else mvp))
        g.UniformMatrix4fv(self.loc("u_mvp"), 1, 0, matrix)
        g.Uniform3f(self.loc("u_start"), *settings.start_rgb)
        g.Uniform3f(self.loc("u_end"), *settings.end_rgb)
        modes = {"8bit": 0, "10bit": 1, "reference": 2, "compare": 3, "three": 4, "dither8": 5}
        patterns = {"horizontal": 0, "vertical": 1, "radial": 2, "solid": 3, "hue": 4, "atlas": 5}
        for name, value in (("u_mode", modes[settings.mode]), ("u_pattern", patterns[settings.pattern]),
                            ("u_labels", int(settings.labels)), ("u_swap", int(settings.swap))):
            g.Uniform1i(self.loc(name), value)
        for name, value in (("u_seconds", seconds if settings.animate else 0), ("u_hue", settings.hue / 360),
                            ("u_sat", settings.saturation), ("u_low", settings.value_min), ("u_high", settings.value_max)):
            g.Uniform1f(self.loc(name), value)
        g.BindVertexArray(self.vao.value)
        g.DrawArrays(GL_TRIANGLES, 0, 6)
        g.BindVertexArray(0)
        g.BindFramebuffer(GL_FRAMEBUFFER, 0)

    def preview(self, target: Target, width: int, height: int) -> None:
        if width < 1 or height < 1:
            return
        g = self.gl
        g.BindFramebuffer(GL_FRAMEBUFFER, 0)
        g.Viewport(0, 0, width, height)
        g.UseProgram(self.preview_program)
        g.ActiveTexture(GL_TEXTURE0)
        g.BindTexture(GL_TEXTURE_2D, target.texture)
        g.Uniform1i(self.loc("u_texture", self.preview_program), 0)
        g.BindVertexArray(self.vao.value)
        g.DrawArrays(GL_TRIANGLES, 0, 3)
        g.BindVertexArray(0)
        g.BindTexture(GL_TEXTURE_2D, 0)

    def read_pixels(self, target: Target) -> array:
        """Return bottom-up float32 RGBA values from the actual source eye buffer."""
        data = array("f", [0.0]) * (target.width * target.height * 4)
        view = (F * len(data)).from_buffer(data)
        self.gl.BindFramebuffer(GL_FRAMEBUFFER, target.framebuffer)
        self.gl.ReadPixels(0, 0, target.width, target.height, GL_RGBA, GL_FLOAT, C.cast(view, P))
        self.gl.BindFramebuffer(GL_FRAMEBUFFER, 0)
        self.gl.check("float pixel readback")
        return data

    def close(self) -> None:
        for target in self.targets:
            fbo, tex = U(target.framebuffer), U(target.texture)
            self.gl.DeleteFramebuffers(1, C.byref(fbo))
            self.gl.DeleteTextures(1, C.byref(tex))
        self.targets.clear()
        if self.vao.value:
            self.gl.DeleteVertexArrays(1, C.byref(self.vao))
            self.vao.value = 0
        for name in ("program", "preview_program"):
            value = getattr(self, name)
            if value:
                self.gl.DeleteProgram(value)
                setattr(self, name, 0)
