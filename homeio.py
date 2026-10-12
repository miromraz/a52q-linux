#!/usr/bin/env python3
# Write-heavy I/O on a directory (meant for the LUKS homed home): 3 big-file writers with
# periodic fsync + 2 small-file churners (browser-profile-like create/write/fsync/rename/unlink).
# Usage: homeio.py DIR SECONDS
import os, random, shutil, sys, time
# own scratch subdirectory: the cleanup at the end must never take DIR itself with it
d, secs = os.path.join(sys.argv[1], f"homeio.{os.getpid()}"), float(sys.argv[2]); end = time.time() + secs; os.makedirs(d)
def big(i):
    buf = os.urandom(1 << 20); n = 0
    while time.time() < end:
        with open(f"{d}/big{i}", "wb") as f:
            for k in range(256):
                f.write(buf); n += 1
                if k % 32 == 31: f.flush(); os.fsync(f.fileno())
                if time.time() > end: break
    print(f"big{i}: {n} MiB", flush=True)
def small(i):
    n = 0
    while time.time() < end:
        p = f"{d}/s{i}-{n % 500}"
        with open(p + ".tmp", "wb") as f:
            f.write(os.urandom(random.randint(100, 64 << 10))); f.flush(); os.fsync(f.fileno())
        os.replace(p + ".tmp", p)
        if n % 7 == 0: os.unlink(p)
        n += 1
    print(f"small{i}: {n} files", flush=True)
kids = []
for i, fn in enumerate([big, big, big, small, small]):
    pid = os.fork()
    if pid == 0: fn(i); os._exit(0)
    kids.append(pid)
for p in kids: os.waitpid(p, 0)
shutil.rmtree(d)
