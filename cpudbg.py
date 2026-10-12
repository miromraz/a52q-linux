#!/usr/bin/env python3
# Read ARMv8 external-debug registers of each core via /dev/mem (core n debug block at
# 0x7010000 + n*0x100000 on SM7125, next to its ETM at +0x40000).
# probe: print IDs/status.  sample [SECS] [HOST PORT]: every 0.5 s read EDPCSR/EDVIDSR per core
# (PC sample + exception level) and send one UDP line to the laptop (survives a disk/journal stall).
import mmap, os, socket, struct, sys, time
BASE, STRIDE = 0x7010000, 0x100000
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = [mmap.mmap(fd, 0x1000, offset=BASE + n * STRIDE) for n in range(8)]
rd = lambda n, off: struct.unpack_from("<I", m[n], off)[0]
wr = lambda n, off, v: struct.pack_into("<I", m[n], off, v)

if sys.argv[1] == "probe":
    for n in range(8):
        cidr = [rd(n, 0xff0 + 4 * i) & 0xff for i in range(4)]
        print(f"cpu{n} CIDR {cidr} DEVARCH {rd(n, 0xfbc):#x} PIDR0 {rd(n, 0xfe0):#x} "
              f"EDPRSR {rd(n, 0x314):#x} EDLSR {rd(n, 0xfb4):#x} AUTHSTATUS {rd(n, 0xfb8):#x}", flush=True)
    sys.exit()

secs = float(sys.argv[2]); dst = (sys.argv[3], int(sys.argv[4]))
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
for n in range(8): wr(n, 0xfb0, 0xC5ACCE55)	# software lock off (harmless if not implemented)
end = time.time() + secs
while time.time() < end:
    out = [f"{time.time():.1f}"]
    for n in range(8):
        lo = rd(n, 0x0a0); vid = rd(n, 0x0a8); hi = rd(n, 0x0ac)	# EDPCSR lo latches hi/CIDSR/VIDSR
        el = "EL3" if vid & (1 << 30) else ("EL2" if vid & (1 << 29) else "EL01")
        out.append(f"c{n}={hi:08x}{lo:08x}/{el}/{vid >> 31}")
    s.sendto((" ".join(out) + "\n").encode(), dst)
    time.sleep(0.5)
