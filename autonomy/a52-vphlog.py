#!/usr/bin/env python3
# VPH_PWR (PM6150L ADC, ~1.25 ms per read) sampled every ~5 ms; min/max per 50 ms window go into
# the ftrace stream as trace_marker lines, on the same clock as the power events, so a supply
# droop before a core dies is visible off-device. Fuel gauge voltage/current/capacity once a second.
# Started by a52-ftrace-stream.sh. Pinned to the little cores: the big ones are the ones that die.
import glob, os, time
os.sched_setaffinity(0, {0, 1, 2, 3})
vph = glob.glob("/sys/bus/iio/devices/iio:device*/in_voltage_vph_pwr_input")[0]
fg = "/sys/class/power_supply/sm5714-fg/"
rd = lambda p: open(p).read().strip()
marker = open("/sys/kernel/tracing/trace_marker", "w", buffering=1)
last_fg = 0
while True:
    t = time.monotonic(); lo, hi = 1 << 31, 0
    while time.monotonic() - t < 0.05:
        v = int(rd(vph)); lo, hi = min(lo, v), max(hi, v)
        time.sleep(0.004)  # back-to-back reads cost a third of a little core
    marker.write(f"vph uV min={lo} max={hi}\n")
    if t - last_fg >= 1:
        last_fg = t
        marker.write(f"fg uV={rd(fg + 'voltage_now')} uA={rd(fg + 'current_now')} cap={rd(fg + 'capacity')}\n")
