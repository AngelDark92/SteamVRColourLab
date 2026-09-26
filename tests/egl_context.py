"""Dependency-free surfaceless EGL context for Linux render validation only."""
import ctypes as C


class EGLContext:
    def __init__(self):
        self.egl = C.CDLL("libEGL.so.1")
        e = self.egl
        e.eglGetProcAddress.argtypes = [C.c_char_p]
        e.eglGetProcAddress.restype = C.c_void_p
        get_platform = C.CFUNCTYPE(C.c_void_p, C.c_uint, C.c_void_p, C.POINTER(C.c_int))(
            e.eglGetProcAddress(b"eglGetPlatformDisplayEXT"))
        self.display = get_platform(0x31DD, None, None)  # EGL_PLATFORM_SURFACELESS_MESA
        for name, result, args in (
            ("eglInitialize", C.c_uint, [C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_int)]),
            ("eglBindAPI", C.c_uint, [C.c_uint]),
            ("eglChooseConfig", C.c_uint, [C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_void_p), C.c_int, C.POINTER(C.c_int)]),
            ("eglCreatePbufferSurface", C.c_void_p, [C.c_void_p, C.c_void_p, C.POINTER(C.c_int)]),
            ("eglCreateContext", C.c_void_p, [C.c_void_p, C.c_void_p, C.c_void_p, C.POINTER(C.c_int)]),
            ("eglMakeCurrent", C.c_uint, [C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p]),
            ("eglDestroyContext", C.c_uint, [C.c_void_p, C.c_void_p]),
            ("eglDestroySurface", C.c_uint, [C.c_void_p, C.c_void_p]),
            ("eglTerminate", C.c_uint, [C.c_void_p]),
        ):
            func = getattr(e, name)
            func.restype, func.argtypes = result, args
        major, minor = C.c_int(), C.c_int()
        if not e.eglInitialize(self.display, C.byref(major), C.byref(minor)):
            raise RuntimeError("EGL initialisation failed")
        if not e.eglBindAPI(0x30A2):
            raise RuntimeError("Could not bind OpenGL API")
        attrs = (C.c_int * 13)(0x3033, 1, 0x3040, 8, 0x3024, 8, 0x3023, 8, 0x3022, 8, 0x3021, 8, 0x3038)
        config, count = C.c_void_p(), C.c_int()
        if not e.eglChooseConfig(self.display, attrs, C.byref(config), 1, C.byref(count)) or not count.value:
            raise RuntimeError("No EGL config")
        pb = (C.c_int * 5)(0x3057, 16, 0x3056, 16, 0x3038)
        self.surface = e.eglCreatePbufferSurface(self.display, config, pb)
        ctx = (C.c_int * 7)(0x3098, 3, 0x30FB, 3, 0x30FD, 1, 0x3038)
        self.context = e.eglCreateContext(self.display, config, None, ctx)
        if not self.surface or not self.context or not e.eglMakeCurrent(self.display, self.surface, self.surface, self.context):
            raise RuntimeError("Could not create EGL OpenGL 3.3 context")

    def get_proc_address(self, name):
        return self.egl.eglGetProcAddress(name.encode("ascii"))

    def close(self):
        e = self.egl
        e.eglMakeCurrent(self.display, None, None, None)
        e.eglDestroyContext(self.display, self.context)
        e.eglDestroySurface(self.display, self.surface)
        e.eglTerminate(self.display)
