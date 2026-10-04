#!/usr/bin/env python3
# Camera regression test for the a52q "Snapshot reconfigure -> hard reset" bug:
# restart streaming on one camss video node many times in ONE process, the way
# libcamera/pipewire does on a resolution switch (one-shot `cam` never triggers it).
# Run `cam -c <idx> --capture=1` first so the media links and pad formats are set.
# Usage: camrestream.py [/dev/videoN] [iterations] [frames] [mode]
#   mode: keep (same fd), reopen (close/reopen fd each time), fast (no frames, no delay)
import ctypes as C, fcntl, os, select, sys, time

dev = sys.argv[1] if len(sys.argv) > 1 else "/dev/video0"
iters = int(sys.argv[2]) if len(sys.argv) > 2 else 20
nframes = int(sys.argv[3]) if len(sys.argv) > 3 else 5
mode = sys.argv[4] if len(sys.argv) > 4 else "keep"

def IOWR(nr, size): return (3 << 30) | (size << 16) | (ord('V') << 8) | nr
def IOW(nr, size): return (1 << 30) | (size << 16) | (ord('V') << 8) | nr

MPLANE, MMAP = 9, 1

class Fmt(C.Structure):
    _fields_ = [("type", C.c_uint32), ("_pad", C.c_uint32), ("raw", C.c_uint8 * 200)]
class Req(C.Structure):
    _fields_ = [("count", C.c_uint32), ("type", C.c_uint32), ("memory", C.c_uint32),
                ("caps", C.c_uint32), ("flags", C.c_uint8), ("res", C.c_uint8 * 3)]
class Plane(C.Structure):
    _fields_ = [("bytesused", C.c_uint32), ("length", C.c_uint32), ("m", C.c_uint64),
                ("data_offset", C.c_uint32), ("res", C.c_uint32 * 11)]
class Buf(C.Structure):
    _fields_ = [("index", C.c_uint32), ("type", C.c_uint32), ("bytesused", C.c_uint32),
                ("flags", C.c_uint32), ("field", C.c_uint32), ("_p", C.c_uint32),
                ("ts", C.c_uint64 * 2), ("tc", C.c_uint8 * 16), ("sequence", C.c_uint32),
                ("memory", C.c_uint32), ("planes", C.c_void_p), ("length", C.c_uint32),
                ("res2", C.c_uint32), ("req_fd", C.c_int32), ("_p2", C.c_uint32)]
assert C.sizeof(Fmt) == 208 and C.sizeof(Req) == 20 and C.sizeof(Plane) == 64 and C.sizeof(Buf) == 88

G_FMT, S_FMT, REQBUFS = IOWR(4, 208), IOWR(5, 208), IOWR(8, 20)
QUERYBUF, QBUF, DQBUF = IOWR(9, 88), IOWR(15, 88), IOWR(17, 88)
STREAMON, STREAMOFF = IOW(18, 4), IOW(19, 4)
NBUF = 4

def log(*a): print(f"{time.monotonic():.3f}", *a, flush=True)

def qbuf(fd, i, nplanes):
    planes = (Plane * nplanes)()
    b = Buf(index=i, type=MPLANE, memory=MMAP, planes=C.addressof(planes), length=nplanes)
    fcntl.ioctl(fd, QBUF, b)

def run(fd, it):
    f = Fmt(type=MPLANE)
    fcntl.ioctl(fd, G_FMT, f)
    fcntl.ioctl(fd, S_FMT, f)
    nplanes = f.raw[180] or 1
    r = Req(count=NBUF, type=MPLANE, memory=MMAP)
    fcntl.ioctl(fd, REQBUFS, r)
    for i in range(r.count):
        qbuf(fd, i, nplanes)
    t = C.c_int(MPLANE)
    fcntl.ioctl(fd, STREAMON, t)
    got = 0
    for _ in range(nframes if mode != "fast" else 0):
        if not select.select([fd], [], [], 2.0)[0]:
            log(f"iter {it}: frame timeout")
            break
        planes = (Plane * nplanes)()
        b = Buf(type=MPLANE, memory=MMAP, planes=C.addressof(planes), length=nplanes)
        fcntl.ioctl(fd, DQBUF, b)
        got += 1
        qbuf(fd, b.index, nplanes)
    fcntl.ioctl(fd, STREAMOFF, t)
    fcntl.ioctl(fd, REQBUFS, Req(count=0, type=MPLANE, memory=MMAP))
    log(f"iter {it}: {got} frames")

fd = os.open(dev, os.O_RDWR)
for it in range(iters):
    try:
        run(fd, it)
    except OSError as e:
        log(f"iter {it}: {e}")
    if mode == "reopen":
        os.close(fd)
        fd = os.open(dev, os.O_RDWR)
os.close(fd)
log("done")
