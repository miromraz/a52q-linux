#!/usr/bin/env python3
# Does touching some physical page hang the core? (missing reserved-memory / hypervisor-owned RAM)
# Faults in anonymous memory chunk by chunk until MemAvailable is nearly gone. After each chunk its
# physical frame ranges (from /proc/self/pagemap) are sent to dev over UDP, so if the core running
# this dies, the last datagrams show which frames had just been handed out (the kernel zeroes a page
# when it faults it in, so the page that kills is in the chunk AFTER the last one reported; chunks
# are small and the allocator mostly walks contiguous frames, so the range is narrow). Each chunk is
# then read back and compared. Run on the phone as root, pinned by the caller:
#   taskset -c 2 python3 memscan.py [KEEP_MB] [CHUNK_PAGES]      (defaults 150, 64)
# ponytail: anonymous pages only (no page cache, no executable mappings); add those if this is clean.
import ctypes, mmap, os, socket, struct, sys

DST = ("192.168.100.105", 6669)
keep_mb = int(sys.argv[1]) if len(sys.argv) > 1 else 150
chunk_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 64
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


keep, total, n = [], 0, 0
pattern = bytes(range(256)) * (PAGE // 256)
sock.sendto(f"memscan start avail={avail_mb()}MB keep={keep_mb}MB chunk={chunk_pages}p\n".encode(), DST)
while avail_mb() > keep_mb:
    m = mmap.mmap(-1, chunk_pages * PAGE, mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)
    for i in range(chunk_pages):          # one write per page faults it in (kernel zeroes it first)
        m[i * PAGE] = 1
    addr = ctypes.addressof(ctypes.c_char.from_buffer(m))
    sock.sendto(f"memscan {n} +{total >> 20}MB pfn {ranges(pfns(addr, chunk_pages))}\n".encode()[:1400], DST)
    for i in range(chunk_pages):          # full-page write, then read back
        m[i * PAGE:(i + 1) * PAGE] = pattern
    for i in range(chunk_pages):
        if m[i * PAGE:(i + 1) * PAGE] != pattern:
            sock.sendto(f"memscan MISMATCH chunk {n} page {i}\n".encode(), DST)
    keep.append(m)
    total += chunk_pages * PAGE
    n += 1
sock.sendto(f"memscan done {total >> 20}MB in {n} chunks, avail={avail_mb()}MB\n".encode(), DST)
print(f"done {total >> 20} MB")
