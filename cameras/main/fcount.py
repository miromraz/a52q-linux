# fcount.py: sensor frame rate from the 0x0005 frame counter over ~2 s
import ctypes, fcntl, os, time
I2C_RDWR = 0x0707
class M(ctypes.Structure): _fields_ = [("a", ctypes.c_uint16), ("f", ctypes.c_uint16), ("l", ctypes.c_uint16), ("b", ctypes.POINTER(ctypes.c_uint8))]
class R(ctypes.Structure): _fields_ = [("m", ctypes.POINTER(M)), ("n", ctypes.c_uint32)]
fd = os.open("/dev/i2c-20", os.O_RDWR)
def rd(reg):
    w = (ctypes.c_uint8 * 2)(reg >> 8, reg & 255); r = (ctypes.c_uint8 * 1)()
    ms = (M * 2)(M(0x2d, 0, 2, ctypes.cast(w, ctypes.POINTER(ctypes.c_uint8))), M(0x2d, 1, 1, ctypes.cast(r, ctypes.POINTER(ctypes.c_uint8))))
    fcntl.ioctl(fd, I2C_RDWR, R(ms, 2)); return r[0]
last = rd(5); t0 = None; n = 0
while True:
    c = rd(5)
    if c != last:
        now = time.monotonic()
        if t0 is None: t0 = now; n = 0
        else: n += (c - last) & 255
        last = c
        if now - t0 > 2.0: break
    time.sleep(0.002)
print("fps %.2f" % (n / (now - t0)))
