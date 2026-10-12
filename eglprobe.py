#!/usr/bin/env python3
# Mimic a browser's startup GPU probe in a loop: surfaceless EGL init, GLES context, upload a
# texture + clear an FBO, glFinish (real GPU work), read the renderer string, tear everything
# down, then pause so the GPU can power-collapse before the next probe.
# Usage: eglprobe.py ROUNDS [MAX_GAP_S]
import ctypes as C, random, sys, time
egl = C.CDLL("libEGL.so.1"); gl = C.CDLL("libGLESv2.so.2")
egl.eglGetProcAddress.restype = C.c_void_p
for f in ("eglGetPlatformDisplay", "eglCreateContext", "eglGetDisplay"):
    getattr(egl, f).restype = C.c_void_p
gl.glGetString.restype = C.c_char_p
SURFACELESS, NONE, GLES_API = 0x31DD, 0x3038, 0x30A0
ctx_attr = (C.c_int * 3)(0x3098, 2, NONE)   # EGL_CONTEXT_CLIENT_VERSION 2
rounds = int(sys.argv[1]); gap = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5
for r in range(rounds):
    d = C.c_void_p(egl.eglGetPlatformDisplay(SURFACELESS, None, None))
    assert egl.eglInitialize(d, None, None), "eglInitialize"
    egl.eglBindAPI(GLES_API)
    ctx = C.c_void_p(egl.eglCreateContext(d, None, None, ctx_attr))   # EGL_NO_CONFIG_KHR
    assert ctx.value and egl.eglMakeCurrent(d, None, None, ctx), "context"
    tex, fbo = C.c_uint(), C.c_uint()
    gl.glGenTextures(1, C.byref(tex)); gl.glBindTexture(0x0DE1, tex)
    gl.glTexImage2D(0x0DE1, 0, 0x1908, 1024, 1024, 0, 0x1908, 0x1401, (C.c_ubyte * (1024 * 1024 * 4))())
    gl.glGenFramebuffers(1, C.byref(fbo)); gl.glBindFramebuffer(0x8D40, fbo)
    gl.glFramebufferTexture2D(0x8D40, 0x8CE0, 0x0DE1, tex, 0)
    gl.glClearColor(C.c_float(random.random()), C.c_float(0.5), C.c_float(0.5), C.c_float(1)); gl.glClear(0x4000)
    gl.glFinish(); name = gl.glGetString(0x1F01)
    gl.glDeleteFramebuffers(1, C.byref(fbo)); gl.glDeleteTextures(1, C.byref(tex))
    egl.eglMakeCurrent(d, None, None, None); egl.eglDestroyContext(d, ctx); egl.eglTerminate(d)
    if r % 20 == 0: print(f"round {r} {name.decode()}", flush=True)
    time.sleep(random.uniform(0, gap))
print("done", rounds, flush=True)
