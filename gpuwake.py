#!/usr/bin/env python3
# Wake the Adreno GPU from runtime suspend over and over, like a browser's startup GPU probe:
# DRM_IOCTL_MSM_GET_PARAM(MSM_PARAM_TIMESTAMP) powers the GPU up to read its counter; random
# gaps around the 66 ms autosuspend delay race the next wake against power-down.
# Usage: gpuwake.py SECONDS [PROCS]
import fcntl, os, random, struct, sys, time
GET_PARAM = 0xC0186440          # DRM_IOWR(0x40 + 0x00, struct drm_msm_param) (24 bytes)
PIPE_3D0, TIMESTAMP = 0x10, 0x05
secs = float(sys.argv[1]); procs = int(sys.argv[2]) if len(sys.argv) > 2 else 2

def run(i):
    fd = os.open("/dev/dri/renderD128", os.O_RDWR); n = 0; end = time.time() + secs
    while time.time() < end:
        buf = bytearray(struct.pack("<IIQII", PIPE_3D0, TIMESTAMP, 0, 0, 0))
        fcntl.ioctl(fd, GET_PARAM, buf); n += 1
        time.sleep(random.uniform(0.0, 0.2))
    print(f"proc {i}: {n} wakes, last ts {struct.unpack_from('<Q', buf, 8)[0]}", flush=True)

kids = []
for i in range(procs):
    pid = os.fork()
    if pid == 0: run(i); os._exit(0)
    kids.append(pid)
for p in kids: os.waitpid(p, 0)
