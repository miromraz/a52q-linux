#!/usr/bin/env python3
# Mimic Chromium's capture-device enumeration: open every /dev/video*, VIDIOC_QUERYCAP, close;
# repeat. On camss each open powers the whole camera pipeline up and down.
# Usage: v4lopen.py ROUNDS
import fcntl, glob, os, sys, time
QUERYCAP = 0x80685600   # _IOR('V', 0, struct v4l2_capability) (104 bytes)
devs = sorted(glob.glob("/dev/video*")); n = 0; t0 = time.time()
for r in range(int(sys.argv[1])):
    for d in devs:
        fd = os.open(d, os.O_RDWR | os.O_NONBLOCK)
        try:
            fcntl.ioctl(fd, QUERYCAP, bytearray(104))
        except OSError:
            pass
        os.close(fd); n += 1
    if r % 10 == 0:
        print(f"round {r} opens {n} {time.time() - t0:.0f}s", flush=True)
print(f"done {n} opens over {len(devs)} devices", flush=True)
