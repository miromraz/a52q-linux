#!/usr/bin/env python3
# subctl.py - list/get/set V4L2 controls on a sensor subdev (no v4l2-ctl on BengalOS).
#   subctl.py NAME_SUBSTR                  list controls
#   subctl.py NAME_SUBSTR id=value ...     set (id: hex CID or name below)
import fcntl, glob, os, struct, sys

NAMES = {"exposure": 0x00980911, "hflip": 0x00980914, "vflip": 0x00980915,
         "vblank": 0x009e0901, "hblank": 0x009e0902, "again": 0x009e0903,
         "dgain": 0x009f0905, "test_pattern": 0x009f0903, "focus": 0x009a090a}


def iowr(nr, size):
    return (3 << 30) | (size << 16) | (ord("V") << 8) | nr


def find(sub):
    for d in sorted(glob.glob("/sys/class/video4linux/v4l-subdev*")):
        if sub in open(d + "/name").read():
            return "/dev/" + os.path.basename(d)
    sys.exit(f"no subdev matching {sub}")


def main():
    fd = os.open(find(sys.argv[1]), os.O_RDWR)
    if len(sys.argv) == 2:
        cid = 0x80000000                       # V4L2_CTRL_FLAG_NEXT_CTRL
        while True:
            q = bytearray(struct.pack("<II32siiiiIII", cid, 0, b"", 0, 0, 0, 0, 0, 0, 0))
            try:
                fcntl.ioctl(fd, iowr(36, len(q)), q, True)
            except OSError:
                break
            i, _, name, mn, mx, st, df, fl, _, _ = struct.unpack("<II32siiiiIII", q)
            v = bytearray(struct.pack("<Ii", i, 0))
            try:
                fcntl.ioctl(fd, iowr(27, 8), v, True)
                val = struct.unpack("<Ii", v)[1]
            except OSError:
                val = "?"
            print(f"0x{i:08x} {name.split(b'\\0')[0].decode():28s} [{mn}..{mx}/{st}] def {df} = {val}")
            cid = i | 0x80000000
        return
    for a in sys.argv[2:]:
        k, v = a.split("=")
        cid = NAMES.get(k) or int(k, 0)
        fcntl.ioctl(fd, iowr(28, 8), bytearray(struct.pack("<Ii", cid, int(v, 0))), True)


if __name__ == "__main__":
    main()
