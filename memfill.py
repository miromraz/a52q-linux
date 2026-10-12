#!/usr/bin/env python3
# Touch (and verify) nearly all free RAM in 64 MiB chunks. A page in a firmware-owned
# region that the DT forgot to reserve hangs the touching core (stage-2/XPU fault).
# Usage: memfill.py RESERVE_MB
import mmap, sys, time
reserve = int(sys.argv[1]) << 20
avail = int(next(l for l in open("/proc/meminfo") if l.startswith("MemAvailable")).split()[1]) << 10
chunk, maps = 64 << 20, []
pat = bytes(range(256)) * (chunk // 256)
while avail - len(maps) * chunk > reserve + chunk:
    m = mmap.mmap(-1, chunk)
    m.write(pat)
    maps.append(m)
    print("filled", len(maps) * 64, "MiB", flush=True)
bad = sum(1 for m in maps if m[:] != pat)
print("verify bad chunks:", bad, flush=True)
time.sleep(30)
