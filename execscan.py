#!/usr/bin/env python3
# Does EXECUTING from some physical page hang the core? memscan.py showed that reading and writing
# every free frame is fine; the Firefox freeze ends right after a JIT page is made executable, and
# hypervisors can deny execution (stage 2) on frames they still let the guest read and write.
# Faults in anonymous memory chunk by chunk until MemAvailable is nearly gone; each page gets a tiny
# function. The chunk's physical frame ranges (/proc/self/pagemap) are sent to dev over UDP FIRST,
# then the chunk is made executable and every page is called. If the core dies, the last datagram
# names the frames it was about to execute. Run on the phone as root, pinned by the caller:
#   taskset -c 2 python3 execscan.py [KEEP_MB] [CHUNK_PAGES]      (defaults 150, 16)
import ctypes, mmap, os, socket, struct, sys

DST = ("192.168.100.105", 6669)
keep_mb = int(sys.argv[1]) if len(sys.argv) > 1 else 150
chunk_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 16
PAGE = 4096
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
pagemap = os.open("/proc/self/pagemap", os.O_RDONLY)


def avail_mb():
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable"):
            return int(line.split()[1]) >> 10


def pfns(addr, n):
    raw = os.pread(pagemap, 8 * n, addr // PAGE * 8)
    return [v & ((1 << 55) - 1) for (v,) in struct.iter_unpack("<Q", raw) if v >> 63]


def ranges(frames):
    out, frames = [], sorted(frames)
    for f in frames:
        if out and f == out[-1][1] + 1:
            out[-1][1] = f
        else:
            out.append([f, f])
    return " ".join(f"{a:x}-{b:x}" if a != b else f"{a:x}" for a, b in out)


libc = ctypes.CDLL(None)
libc.mprotect.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
FN = ctypes.CFUNCTYPE(ctypes.c_int)
keep, total, n = [], 0, 0
sock.sendto(f"execscan start avail={avail_mb()}MB keep={keep_mb}MB chunk={chunk_pages}p\n".encode(), DST)
while avail_mb() > keep_mb:
    m = mmap.mmap(-1, chunk_pages * PAGE, mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)
    for i in range(chunk_pages):          # mov w0, #i; ret  at the start of every page
        m[i * PAGE:i * PAGE + 8] = struct.pack("<II", 0x52800000 | i << 5, 0xd65f03c0)
    addr = ctypes.addressof(ctypes.c_char.from_buffer(m))
    sock.sendto(f"execscan {n} +{total >> 20}MB pfn {ranges(pfns(addr, chunk_pages))}\n".encode()[:1400], DST)
    # a first-time executable mapping makes the kernel sync the I-cache for the page; no user flush needed
    libc.mprotect(addr, chunk_pages * PAGE, mmap.PROT_READ | mmap.PROT_EXEC)
    for i in range(chunk_pages):
        if FN(addr + i * PAGE)() != i:
            sock.sendto(f"execscan WRONG RESULT chunk {n} page {i}\n".encode(), DST)
    keep.append(m)
    total += chunk_pages * PAGE
    n += 1
sock.sendto(f"execscan done {total >> 20}MB in {n} chunks, avail={avail_mb()}MB\n".encode(), DST)
print(f"done {total >> 20} MB")
