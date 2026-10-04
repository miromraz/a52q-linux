#!/usr/bin/env python3
# Exercise the geni-i2c GPI multi-message read path (write reg + read) on the touch bus.
# Reads FTS5CU56A fw-version register 0x24 (read-only, harmless). Usage: i2cstress.py [N]
import ctypes, fcntl, os, sys, time
I2C_RDWR, I2C_M_RD = 0x0707, 0x0001
class msg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16),
                ("len", ctypes.c_uint16), ("buf", ctypes.c_void_p)]
class ioctl_data(ctypes.Structure):
    _fields_ = [("msgs", ctypes.POINTER(msg)), ("nmsgs", ctypes.c_uint32)]
n = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
fd = os.open("/dev/i2c-7", os.O_RDWR)
wbuf = (ctypes.c_uint8 * 1)(0x24); rbuf = (ctypes.c_uint8 * 8)()
msgs = (msg * 2)(msg(0x49, 0, 1, ctypes.addressof(wbuf)), msg(0x49, I2C_M_RD, 8, ctypes.addressof(rbuf)))
data = ioctl_data(msgs, 2)
ok = err = 0; t0 = time.time()
for i in range(n):
    try:
        fcntl.ioctl(fd, I2C_RDWR, data); ok += 1
    except OSError as e:
        err += 1
        if err == 1: print(f"first error at transfer {i}: {e}")
        if err >= 5: break
print(f"ok={ok} err={err} in {time.time()-t0:.1f}s fw={bytes(rbuf).hex()}")
