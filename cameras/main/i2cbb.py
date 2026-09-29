#!/usr/bin/env python3
# i2cbb.py - bit-banged I2C on two TLMM GPIOs through the gpio cdev (v1 ABI),
# for probing parts on buses mainline has not enabled (a52q: qup i2c9 =
# gpio46 SDA / gpio47 SCL -> AK7374 VCM @0x0c, M24128 EEPROM @0x50/0x51;
# qup i2c10 = gpio86/87 -> OIS MCU @0x62). Lines are requested open-drain.
#
#   i2cbb.py [--bus 9|10] scan
#   i2cbb.py [--bus 9|10] rd  ADDR REG N [--a16]     (REG 8-bit, or 16-bit with --a16)
#   i2cbb.py [--bus 9|10] wr  ADDR REG BYTE... [--a16]
#   i2cbb.py [--bus 9|10] dump ADDR START LEN OUTFILE (16-bit addressed EEPROM)
#
# The camera rails (VIO for the pull-ups, VAF for the VCM/EEPROM) must be on:
# stream the sensor or `echo on > /sys/bus/i2c/devices/20-002d/power/control`.
import fcntl, os, struct, sys, time

CHIP = "/dev/gpiochip2"          # 3500000.pinctrl (TLMM)
PINS = {9: (46, 47), 10: (86, 87)}
OUT, OD = 1 << 1, 1 << 3
STRETCH = 0.05                  # max clock-stretch wait, s


def _iowr(nr, size):
    return (3 << 30) | (size << 16) | (0xB4 << 8) | nr


GET_LINEHANDLE, GET_VALUES, SET_VALUES = _iowr(3, 364), _iowr(8, 64), _iowr(9, 64)


def line(chip, off):
    b = bytearray(364)
    struct.pack_into("<I", b, 0, off)
    struct.pack_into("<I", b, 256, OUT | OD)
    b[260] = 1                                   # released (high)
    b[324:324 + 5] = b"i2cbb"
    struct.pack_into("<I", b, 356, 1)
    fcntl.ioctl(chip, GET_LINEHANDLE, b, True)
    return struct.unpack_from("<i", b, 360)[0]


class Bus:
    def __init__(self, n):
        fd = os.open(CHIP, os.O_RDONLY)
        self.sda, self.scl = (line(fd, p) for p in PINS[n])
        os.close(fd)

    def _set(self, fd, v):
        b = bytearray(64); b[0] = v
        fcntl.ioctl(fd, SET_VALUES, b)

    def _get(self, fd):
        b = bytearray(64)
        fcntl.ioctl(fd, GET_VALUES, b, True)
        return b[0]

    def scl_hi(self):
        self._set(self.scl, 1)
        t = time.time()
        while not self._get(self.scl):           # clock stretching
            if time.time() - t > STRETCH:
                raise IOError("SCL stuck low")

    def start(self):
        self._set(self.sda, 1); self.scl_hi()
        if not self._get(self.sda):
            raise IOError("SDA stuck low")
        self._set(self.sda, 0); self._set(self.scl, 0)

    def stop(self):
        self._set(self.sda, 0); self.scl_hi(); self._set(self.sda, 1)

    def wbyte(self, v):
        for i in range(7, -1, -1):
            self._set(self.sda, (v >> i) & 1); self.scl_hi(); self._set(self.scl, 0)
        self._set(self.sda, 1); self.scl_hi()
        ack = not self._get(self.sda)
        self._set(self.scl, 0)
        return ack

    def rbyte(self, ack):
        v = 0
        self._set(self.sda, 1)
        for _ in range(8):
            self.scl_hi(); v = (v << 1) | self._get(self.sda); self._set(self.scl, 0)
        self._set(self.sda, 0 if ack else 1); self.scl_hi(); self._set(self.scl, 0)
        self._set(self.sda, 1)
        return v

    def probe(self, a):
        self.start(); ok = self.wbyte(a << 1); self.stop()
        return ok

    def write(self, a, reg, data, a16=False):
        self.start()
        ok = self.wbyte(a << 1)
        for r in ([reg >> 8, reg & 0xff] if a16 else [reg]) + list(data):
            ok = ok and self.wbyte(r)
        self.stop()
        if not ok:
            raise IOError(f"NACK writing 0x{a:02x}")

    def read(self, a, reg, n, a16=False):
        self.start()
        ok = self.wbyte(a << 1)
        for r in ([reg >> 8, reg & 0xff] if a16 else [reg]):
            ok = ok and self.wbyte(r)
        self.start()
        ok = ok and self.wbyte((a << 1) | 1)
        if not ok:
            self.stop()
            raise IOError(f"NACK reading 0x{a:02x}")
        out = [self.rbyte(i < n - 1) for i in range(n)]
        self.stop()
        return bytes(out)


def main():
    args = sys.argv[1:]
    n = 9
    if args[0] == "--bus":
        n = int(args[1]); args = args[2:]
    a16 = "--a16" in args
    args = [x for x in args if x != "--a16"]
    b = Bus(n)
    cmd = args[0]
    if cmd == "scan":
        print("ack:", [hex(a) for a in range(0x08, 0x78) if b.probe(a)])
    elif cmd == "rd":
        a, r, cnt = (int(x, 0) for x in args[1:4])
        print(b.read(a, r, cnt, a16).hex(" "))
    elif cmd == "wr":
        a, r = int(args[1], 0), int(args[2], 0)
        b.write(a, r, [int(x, 0) for x in args[3:]], a16)
    elif cmd == "dump":
        a, s, ln, out = int(args[1], 0), int(args[2], 0), int(args[3], 0), args[4]
        buf = bytearray()
        while len(buf) < ln:
            buf += b.read(a, s + len(buf), min(64, ln - len(buf)), True)
        open(out, "wb").write(buf)
        print(f"wrote {len(buf)} bytes to {out}")


if __name__ == "__main__":
    main()
