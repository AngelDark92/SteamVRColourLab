"""Real rendering context: surfaceless EGL on Linux, hidden GLFW elsewhere."""
import sys


class GraphicsContext:
    def __init__(self):
        self.egl = None
        self.glfw = None
        self.window = None
        if sys.platform.startswith("linux"):
            from tests.egl_context import EGLContext
            self.egl = EGLContext()
        else:
            import glfw
            self.glfw = glfw
            if not glfw.init():
                raise RuntimeError("GLFW could not initialise for render tests.")
            glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
            glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
            glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
            glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
            self.window = glfw.create_window(32, 32, "Colour Lab renderer tests", None, None)
            if not self.window:
                glfw.terminate()
                raise RuntimeError("OpenGL 3.3 is required for render tests.")
            glfw.make_context_current(self.window)

    def get_proc_address(self, name):
        if self.egl:
            return self.egl.get_proc_address(name)
        return self.glfw.get_proc_address(name)

    def close(self):
        if self.egl:
            self.egl.close()
        elif self.glfw:
            if self.window:
                self.glfw.destroy_window(self.window)
            self.glfw.terminate()
