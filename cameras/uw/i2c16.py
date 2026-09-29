#!/usr/bin/env python3
# i2c16.py BUS ADDR REG [VAL16]  -- 16-bit register read (2 bytes) or 16-bit write, works on claimed addresses
import sys, os, fcntl, struct, ctypes
I2C_RDWR = 0x0707
class msg(ctypes.Structure):
    _fields_ = [('addr', ctypes.c_uint16), ('flags', ctypes.c_uint16), ('len', ctypes.c_uint16), ('buf', ctypes.c_void_p)]
class rdwr(ctypes.Structure):
    _fields_ = [('msgs', ctypes.c_void_p), ('nmsgs', ctypes.c_uint32)]
def xfer(fd, *ms):
    arr = (msg * len(ms))(*ms)
    fcntl.ioctl(fd, I2C_RDWR, rdwr(ctypes.addressof(arr), len(ms)))
bus, addr, reg = int(sys.argv[1]), int(sys.argv[2], 0), int(sys.argv[3], 0)
fd = os.open('/dev/i2c-%d' % bus, os.O_RDWR)
if len(sys.argv) > 4:
    v = int(sys.argv[4], 0)
    b = ctypes.create_string_buffer(struct.pack('>HH', reg, v), 4)
    xfer(fd, msg(addr, 0, 4, ctypes.addressof(b)))
else:
    w = ctypes.create_string_buffer(struct.pack('>H', reg), 2); r = ctypes.create_string_buffer(2)
    xfer(fd, msg(addr, 0, 2, ctypes.addressof(w)), msg(addr, 1, 2, ctypes.addressof(r)))
    print('0x%04x' % struct.unpack('>H', r.raw)[0])
