#!/usr/bin/env python3
# oisproto.py - userspace prototype of the Samsung a52q main-camera OIS bring-up
# (STM32G MCU @0x62 on QUP i2c10 = gpio86/87, bit-banged via i2cbb.py).
# Mirrors the downstream cam_ois_mcu_stm32g.c normal camera-open path ONLY:
# no flash, no bootloader, no calibration/EEPROM writes (see WRITABLE).
#
#   oisproto.py probe             read-only: versions, status, errors, cal regs
#   oisproto.py dump [secs]       read-only: which bytes of 0x0000-0x00ff / 0x0200-0x02ff move
#   oisproto.py run MODE [secs]   Android init + centering, then MODE (0 still, 1 movie,
#                                 5 centering), sample status/hall, servo off, reset
#
# Needs the main camera rails (VAF l7, gpio63 AVDD1P8, VIO l3) on; the script
# forces the s5kgw1p runtime-PM on for the duration. Run under the camera lock:
#   flock /run/a52cam.lock python3 oisproto.py probe
import fcntl, os, struct, sys, time
sys.path.insert(0, "/var/tmp/camwork/main")
import i2cbb

ADDR = 0x62
NRST, BOOT0 = 32, 43
SENSOR_PM = "/sys/bus/i2c/devices/20-002d/power/control"
# The only registers this script may write: those the downstream driver writes
# on every camera open (cam_ois_init + cam_ois_set_ois_mode + servo off).
WRITABLE = {0x0000, 0x0002, 0x0039, 0x003A, 0x003B, 0x00BE,
            *range(0x0238, 0x023C), *range(0x0240, 0x0243), *range(0x0248, 0x024C),
            *range(0x0254, 0x025C), *range(0x0348, 0x034C), *range(0x03D8, 0x03DC),
            0x0552, 0x0553}

# a52q values (downstream CONFIG_SEC_A52Q_PROJECT / module EEPROM / EFS)
GYRO_ORIENT = bytes([0x00, 0x01, 0x00])      # 0x0240: Wx pole, Wy pole, orientation
TELE_POLE = bytes([0x00, 0x00])              # 0x0552
ANGLE_COMP = bytes([0x06, 0x81, 0x55, 0x3F])  # float 0.834 -> 0x0348 and 0x03D8
EFS_GYRO_CAL = "0.342,-1.192"                 # sec_efs:/FactoryApp/camera_ois_gyro_cal
EEPROM = "/var/tmp/camwork/main/eeprom50.bin"  # module EEPROM dump, OIS cal @0x170


def gyro_offset(s):
    """EFS 'x,y' string -> (XGZERO, YGZERO) exactly like cam_ois_get_offset_data +
    cam_ois_write_gyro_sensor_calibration (dots dropped, *114/1000, C truncation)."""
    return tuple(int(int(v.replace(".", "")) * 114 / 1000) for v in s.split(","))


assert gyro_offset("0.342,-1.192") == (38, -135)


def line(chip, off, val):
    b = bytearray(364); struct.pack_into("<I", b, 0, off); struct.pack_into("<I", b, 256, 1 << 1)
    b[260] = val; b[324:331] = b"oisprot"; struct.pack_into("<I", b, 356, 1)
    fcntl.ioctl(chip, i2cbb.GET_LINEHANDLE, b, True)
    return struct.unpack_from("<i", b, 360)[0]


def setv(fd, v):
    b = bytearray(64); b[0] = v; fcntl.ioctl(fd, i2cbb.SET_VALUES, b)


class Mcu:
    def __init__(self):
        i2cbb.STRETCH = 2.0
        self.bus = i2cbb.Bus(10)

    def rd(self, reg, n=1):
        return self.bus.read(ADDR, reg, n, a16=True)

    def wr(self, reg, data):
        assert all(r in WRITABLE for r in range(reg, reg + len(data))), hex(reg)
        self.bus.write(ADDR, reg, list(data), a16=True)

    def wait_idle(self, tries=20):
        for _ in range(tries):
            try:
                s = self.rd(0x0001)[0]
                if s in (0x01, 0x13):
                    return s
            except IOError:
                pass
            time.sleep(0.005)
        raise IOError("OIS MCU not idle")


def u16(b):
    return struct.unpack("<h", b)[0]


def power_on():
    old = open(SENSOR_PM).read().strip()
    open(SENSOR_PM, "w").write("on")
    time.sleep(0.05)
    chip = os.open(i2cbb.CHIP, os.O_RDONLY)
    boot = line(chip, BOOT0, 0)              # BOOT0 low BEFORE reset release: main flash
    rst = line(chip, NRST, 0)
    time.sleep(0.005)
    setv(rst, 1)                             # release NRST
    time.sleep(0.05)                         # downstream: 14 ms; sysboot: 50 ms
    return old, rst, boot


def power_off(old, rst):
    setv(rst, 0)
    open(SENSOR_PM, "w").write(old)


def probe(m):
    print("status 0x0001 =", hex(m.wait_idle()))
    print("err    0x0004 =", m.rd(0x0004, 2).hex())
    print("fwsts  0x00FC =", m.rd(0x00FC, 4).hex(), "(4451 = broken fw update)")
    v = m.rd(0x00F8, 4) + m.rd(0x007C, 4)
    print("module ver    =", (v[3::-1] + v[4:]).decode("latin1"), "(phone blob PSC1NK1M)")
    print("mode/ctrl 0x0002/0x0000 =", m.rd(0x0002).hex(), m.rd(0x0000).hex())
    print("gyro orient 0x0240 =", m.rd(0x0240, 3).hex(), " pole 0x0552 =", m.rd(0x0552, 2).hex())
    g = m.rd(0x0248, 4)
    print("gyro offset 0x0248 = X %d Y %d" % (u16(g[:2]), u16(g[2:])))
    print("XGG/YGG 0x0254 =", m.rd(0x0254, 8).hex())
    print("hall ctr 0x021A/C =", m.rd(0x021A, 2).hex(), m.rd(0x021C, 2).hex())
    print("angle 0x0348 =", m.rd(0x0348, 4).hex(), " 0x03D8 =", m.rd(0x03D8, 4).hex())
    print("shift 0x0039..3B =", m.rd(0x0039, 3).hex(), " ggfade 0x0238 =", m.rd(0x0238, 4).hex())
    print("oissel 0x00BE =", m.rd(0x00BE).hex())


def dump(m, secs, idle=True):
    def snap():
        return b"".join(m.rd(a, 64) for a in list(range(0x0000, 0x0100, 64)) + list(range(0x0200, 0x0300, 64)))
    if idle:
        m.wait_idle()
    a = snap(); t = time.time(); moving = set()
    while time.time() - t < secs:
        b = snap()
        moving |= {i for i in range(len(a)) if a[i] != b[i]}
        a = b
    addr = lambda i: (i if i < 0x100 else i - 0x100 + 0x200)
    print("moving bytes:", " ".join("%04x" % addr(i) for i in sorted(moving)) or "none")
    return a


def android_init(m):
    """cam_ois_init() for a52q, then the CamX init setting and OIS centering."""
    m.wait_idle()
    ee = open(EEPROM, "rb").read()
    if ee[0x1A0] == 0xBB:                               # OIS cal mark
        m.wr(0x0254, ee[0x180:0x188])                   # XGG/YGG (RAM)
    m.wr(0x0240, GYRO_ORIENT)
    m.wr(0x0552, TELE_POLE)
    m.wait_idle(5)
    x, y = gyro_offset(EFS_GYRO_CAL)
    m.wr(0x0248, struct.pack("<hh", x, y))
    m.wait_idle(10)
    m.wr(0x003A, b"\x80"); m.wr(0x003B, b"\x80"); m.wr(0x0039, b"\x01")   # AF-shift comp on
    m.wr(0x0238, struct.pack("<H", 1000)); m.wr(0x023A, struct.pack("<H", 1000))
    m.wr(0x0348, ANGLE_COMP); m.wr(0x03D8, ANGLE_COMP)
    m.wr(0x00BE, b"\x01")                               # CamX initSettings: select wide module
    print("init done: err 0x0004 =", m.rd(0x0004, 2).hex())


def set_mode(m, mode):
    m.wr(0x0002, bytes([mode]))
    m.wr(0x0000, b"\x01")                               # servo on


def sample(m, secs):
    """Status plus the words that move while the servo runs (found with 'dump'):
    0x0082/0x0084, 0x0094..0x009c (int16 LE)."""
    t = time.time()
    while time.time() - t < secs:
        s = m.rd(0x0000, 3); e = m.rd(0x0004, 2)
        w = m.rd(0x0082, 4) + m.rd(0x0094, 10)
        v = [u16(w[i:i + 2]) for i in range(0, len(w), 2)]
        print("%5.2fs ctrl %02x sts %02x mode %02x err %s  82 %6d 84 %6d | 94 %6d 96 %6d 98 %6d 9a %6d 9c %6d" % (
            (time.time() - t, s[0], s[1], s[2], e.hex()) + tuple(v)))
        time.sleep(0.2)


def main():
    cmd = sys.argv[1]
    old, rst, boot = power_on()
    m = Mcu()
    try:
        if cmd == "probe":
            probe(m)
        elif cmd == "dump":
            dump(m, float(sys.argv[2]) if len(sys.argv) > 2 else 3)
        elif cmd == "run":
            mode = int(sys.argv[2], 0); secs = float(sys.argv[3]) if len(sys.argv) > 3 else 3
            android_init(m)
            set_mode(m, 0x05); time.sleep(0.02)          # centering, as the OIS thread does
            print("after centering:", m.rd(0x0000, 3).hex())
            set_mode(m, mode)
            sample(m, secs)
            dump(m, 3, idle=False)
            m.wr(0x0000, b"\x00")                        # servo off
            time.sleep(0.02)
            print("after servo off:", m.rd(0x0000, 3).hex())
    finally:
        power_off(old, rst)
        print("MCU back in reset")


if __name__ == "__main__":
    main()
