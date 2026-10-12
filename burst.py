#!/usr/bin/env python3
# Bursty load pinned to one CPU: random short busy spins and sleeps, so the core keeps
# entering/leaving cpuidle and schedutil keeps changing the big-cluster frequency
# (constant 100% load never hit the cpu7 hard lockup; Claude Desktop's bursty load did).
# Usage: burst.py CPU SECONDS
import os, random, sys, time
cpu, secs = int(sys.argv[1]), float(sys.argv[2])
os.sched_setaffinity(0, {cpu})
end = time.monotonic() + secs
n = 0
while time.monotonic() < end:
    t = time.monotonic() + random.uniform(0.0005, 0.03)
    while time.monotonic() < t:
        pass
    time.sleep(random.choice((0.0002, 0.001, 0.005, 0.02, 0.08)))
    n += 1
print(cpu, n)
