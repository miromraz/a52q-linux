#!/usr/bin/env python3
# Saturate Wi-Fi both ways: 4 threads downloading big.bin from the laptop's http.server,
# 2 threads pushing random data to a laptop socat sink. Usage: wifistress.py SECS HOST
import os, socket, sys, threading, time, urllib.request
secs, host = float(sys.argv[1]), sys.argv[2]; end = time.time() + secs
tot = {"down": 0, "up": 0}; lock = threading.Lock()

def down():
    while time.time() < end:
        try:
            with urllib.request.urlopen(f"http://{host}:8765/big.bin", timeout=20) as r:
                while time.time() < end and (b := r.read(1 << 16)):
                    with lock: tot["down"] += len(b)
        except Exception as e:
            print("down err", e, flush=True); time.sleep(1)

def up():
    buf = os.urandom(1 << 16)
    while time.time() < end:
        try:
            with socket.create_connection((host, 8766), timeout=20) as s:
                while time.time() < end:
                    s.sendall(buf)
                    with lock: tot["up"] += len(buf)
        except Exception as e:
            print("up err", e, flush=True); time.sleep(1)

ts = [threading.Thread(target=down) for _ in range(4)] + [threading.Thread(target=up) for _ in range(2)]
for t in ts: t.start()
for t in ts: t.join()
print(f"down {tot['down'] >> 20} MiB up {tot['up'] >> 20} MiB in {secs:.0f} s", flush=True)
