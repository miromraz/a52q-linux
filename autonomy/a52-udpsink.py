#!/usr/bin/env python3
# UDP sinks on dev for the phone's freeze-debug streams (netconsole, strace relay, ftrace relay).
# Raw datagrams appended like `socat -u UDP-RECV:PORT -`, but size-capped, because a full disk on
# dev takes T3 Code down: at CAP_MB the log is renamed to NAME.<YYYYmmdd-HHMMSS> (time of rotation),
# compressed to .zst, and the oldest rotated files are deleted until they total <= CAP_MB again.
# So each stream uses at most ~2x its cap (live file + archives); read archives with zstdcat.
# Binds to dev's own address, not 0.0.0.0, so LAN broadcasts (Tuya devices on 6666/6667) stay out.
# Usage: a52-udpsink.py DIR BIND_IP PORT:NAME:CAP_MB ...
import glob, os, selectors, socket, subprocess, sys, threading, time

def archive(path, rotated, cap):
    subprocess.run(["nice", "-n", "15", "zstd", "-q", "-9", "--rm", rotated])  # fails -> stays raw, still pruned
    old = sorted(glob.glob(glob.escape(path) + ".*"), key=os.path.getmtime)
    while len(old) > 1 and sum(map(os.path.getsize, old)) > cap:
        os.remove(old.pop(0))

d = sys.argv[1]; sel = selectors.DefaultSelector()
for spec in sys.argv[3:]:
    port, name, cap = spec.split(":")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind((sys.argv[2], int(port)))
    path = os.path.join(d, name)
    sel.register(s, selectors.EVENT_READ, [path, open(path, "ab"), int(cap) << 20])
last = time.monotonic()
while True:
    for key, _ in sel.select(1):
        st = key.data
        st[1].write(key.fileobj.recv(65535))
        if st[1].tell() >= st[2]:
            st[1].close(); rot = st[0] + time.strftime(".%Y%m%d-%H%M%S"); os.replace(st[0], rot)
            st[1] = open(st[0], "ab")
            threading.Thread(target=archive, args=(st[0], rot, st[2])).start()
    if time.monotonic() - last >= 1:  # at most ~1 s of a stream sits in the buffer
        last = time.monotonic()
        for key in sel.get_map().values():
            key.data[1].flush()
