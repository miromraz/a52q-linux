#!/usr/bin/env python3
# Does the JIT code-patching sequence that V8 and SpiderMonkey use hang the core? Both flush with
# `dc civac` from user space (not `dc cvau` like libgcc's __clear_cache, which also skips the D-side
# when CTR_EL0.IDC is set), after flipping the page RW -> RX with mprotect. The flight-recorder dumps
# of the Firefox freeze end right after an mprotect(PROT_READ|PROT_EXEC) of the dying thread.
# One worker process per listed CPU: mprotect(RW), write a tiny function, mprotect(RX), flush, call.
#   jitciv.py MODE SECONDS CPU[,CPU...]     MODE: civac | cvau | noflush (mprotect + call only)
# Progress (iterations per worker) goes to dev over UDP once a second.
# ponytail: one page per worker, no concurrent execution of the page by other threads; add if needed.
import ctypes, mmap, os, socket, struct, sys, time

DST = ("192.168.100.105", 6669)
mode, secs, cpus = sys.argv[1], float(sys.argv[2]), [int(c) for c in sys.argv[3].split(",")]
PAGE = 4096
DC = {"civac": 0xd50b7e20, "cvau": 0xd50b7b20}  # dc civac, x0 / dc cvau, x0
# flush(x0 = start, x1 = end), 64-byte lines: D loop, dsb ish, I loop (ic ivau), dsb ish, isb
FLUSH = [0xaa0003e2,                               # mov x2, x0
         DC.get(mode, 0xd503201f), 0x91010000, 0xeb01001f, 0x54ffffa3,  # 1: dc ..; add x0,#64; cmp; b.lo 1b
         0xd5033b9f,                               # dsb ish
         0xd50b7522, 0x91010042, 0xeb01005f, 0x54ffffa3,  # 2: ic ivau, x2; add x2,#64; cmp x2,x1; b.lo 2b
         0xd5033b9f, 0xd5033fdf, 0xd65f03c0]       # dsb ish; isb; ret
libc = ctypes.CDLL(None, use_errno=True)
libc.mprotect.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]


def code_page(words):
    m = mmap.mmap(-1, PAGE, mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS, mmap.PROT_READ | mmap.PROT_WRITE)
    m[:4 * len(words)] = struct.pack(f"<{len(words)}I", *words)
    addr = ctypes.addressof(ctypes.c_char.from_buffer(m))
    assert libc.mprotect(addr, PAGE, mmap.PROT_READ | mmap.PROT_EXEC) == 0
    return m, addr


def worker(cpu):
    os.sched_setaffinity(0, {cpu})
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    keep, faddr = code_page(FLUSH)
    flush = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)(faddr)
    jit, jaddr = code_page([0x52800000, 0xd65f03c0])           # mov w0, #0; ret
    call = ctypes.CFUNCTYPE(ctypes.c_int)(jaddr)
    n, end, tick = 0, time.monotonic() + secs, time.monotonic() + 1
    while time.monotonic() < end:
        v = n & 0xffff
        libc.mprotect(jaddr, PAGE, mmap.PROT_READ | mmap.PROT_WRITE)
        jit[:4] = struct.pack("<I", 0x52800000 | v << 5)         # mov w0, #v
        libc.mprotect(jaddr, PAGE, mmap.PROT_READ | mmap.PROT_EXEC)
        if mode != "noflush":
            flush(jaddr, jaddr + 64)
            assert call() == v, f"stale code on cpu{cpu} at {n}"  # only meaningful when flushed
        else:
            call()
        n += 1
        if time.monotonic() > tick:
            tick += 1
            sock.sendto(f"jitciv {mode} cpu{cpu} n={n}\n".encode(), DST)
    sock.sendto(f"jitciv {mode} cpu{cpu} done n={n}\n".encode(), DST)


pids = [os.fork() or (worker(c), os._exit(0)) for c in cpus]
bad = [p for p in pids if os.waitpid(p, 0)[1]]
print("FAILED workers:", len(bad)) if bad else print("done")
sys.exit(bool(bad))
