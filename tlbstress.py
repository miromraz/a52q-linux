#!/usr/bin/env python3
# Stress broadcast TLB invalidation: N processes (one per CPU) loop mmap/touch/mprotect/
# madvise/munmap. Each mprotect/munmap/madvise issues TLBI ...IS + DSB to every core.
# Usage: tlbstress.py SECONDS [NPROC] [MB]
import ctypes, os, sys, time
secs = float(sys.argv[1]); nproc = int(sys.argv[2]) if len(sys.argv) > 2 else os.cpu_count()
size = (int(sys.argv[3]) if len(sys.argv) > 3 else 4) << 20
libc = ctypes.CDLL(None, use_errno=True)
libc.mmap.restype = ctypes.c_void_p
libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_long]
libc.mprotect.argtypes = libc.munmap.argtypes = libc.madvise.argtypes = None
R, RW, PRIV_ANON, DONTNEED, PG = 1, 3, 0x22, 4, 4096

def worker(cpu):
    os.sched_setaffinity(0, {cpu % os.cpu_count()})
    end = time.time() + secs; n = 0
    while time.time() < end:
        a = libc.mmap(None, size, RW, PRIV_ANON, -1, 0)
        ctypes.memset(a, n & 0xff, size)
        for off in range(0, size, 64 * PG):   # many small range flushes
            libc.mprotect(ctypes.c_void_p(a + off), ctypes.c_size_t(64 * PG), R)
            libc.mprotect(ctypes.c_void_p(a + off), ctypes.c_size_t(64 * PG), RW)
        libc.madvise(ctypes.c_void_p(a), ctypes.c_size_t(size), DONTNEED)
        libc.munmap(ctypes.c_void_p(a), ctypes.c_size_t(size)); n += 1
    print(f"cpu{cpu}: {n} iterations", flush=True)

kids = []
for c in range(nproc):
    pid = os.fork()
    if pid == 0:
        worker(c); os._exit(0)
    kids.append(pid)
for p in kids: os.waitpid(p, 0)
