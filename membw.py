#!/usr/bin/env python3
# DDR bandwidth stress: big memcpy loops (unlike the CPU-only stress, this drives the
# memory bus and DDR frequency scaling). Usage: membw.py CPU SECONDS MB
import os, sys, time
cpu, secs, mb = int(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3])
os.sched_setaffinity(0, {cpu})
a = bytearray(os.urandom(1 << 20) * mb)
b = bytearray(len(a))
end, n = time.monotonic() + secs, 0
while time.monotonic() < end:
    b[:] = a
    a[:] = b
    n += 1
    if n % 3 == 0:
        time.sleep(0.05)  # bursty: let bandwidth votes drop and rise again
print(cpu, n * 2 * mb / secs, "MB/s")
