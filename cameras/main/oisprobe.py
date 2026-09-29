# oisprobe.py: release the STM32G OIS MCU from reset (gpio32 NRST high, gpio43 BOOT0 low),
# read status/version over bit-banged i2c10, then put it back into reset.
import os, fcntl, struct, time, sys
sys.path.insert(0, "/var/tmp/camwork/main")
import i2cbb
def hold(chip, off, val):
    b = bytearray(364); struct.pack_into("<I", b, 0, off); struct.pack_into("<I", b, 256, 1 << 1)
    b[260] = val; b[324:331] = b"oisprob"; struct.pack_into("<I", b, 356, 1)
    fcntl.ioctl(chip, i2cbb.GET_LINEHANDLE, b, True); return struct.unpack_from("<i", b, 360)[0]
chip = os.open(i2cbb.CHIP, os.O_RDONLY)
boot = hold(chip, 43, 0)
rst = hold(chip, 32, 0); time.sleep(0.005)
b = bytearray(64); b[0] = 1; fcntl.ioctl(rst, i2cbb.SET_VALUES, b)   # release NRST
time.sleep(0.5)
i2cbb.STRETCH = 2.0
bus = i2cbb.Bus(10)
def rd2(reg, n):
    bus.start(); ok = bus.wbyte(0x62 << 1) and bus.wbyte(reg >> 8) and bus.wbyte(reg & 0xff); bus.stop()
    time.sleep(0.002)
    bus.start(); ok = ok and bus.wbyte((0x62 << 1) | 1)
    r = bytes(bus.rbyte(i < n - 1) for i in range(n)); bus.stop(); return ok, r
for reg, n in ((0x0001, 1), (0x0004, 2), (0x00F8, 4), (0x007C, 4), (0x0000, 1), (0x0002, 1)):
    try: ok, r = rd2(reg, n); print(hex(reg), ok, r.hex(" "))
    except IOError as e: print(hex(reg), e)
b[0] = 0; fcntl.ioctl(rst, i2cbb.SET_VALUES, b)                      # back into reset
print("MCU back in reset")
