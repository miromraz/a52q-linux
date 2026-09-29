#!/usr/bin/env python3
"""Print the soft-ISP Lsc block for the a52q main camera (S5KGW1P) from the
stock CamX tuning com.samsung.tuned.lsi_s5kgw1p.bin: lsc34_ife, tuning mode 2,
first AEC region (lux index 1..460, single CCT table 1..10000 K), 17x13 nodes,
tables r, gr, gb, b (g = mean of gr, gb). Same path as the UW generator
(cameras/uw/gen-s5k3l6xx-yaml.py), whose decoder this reuses.

  gen-s5kgw1p-lsc.py com.samsung.tuned.lsi_s5kgw1p.bin
"""
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, '..', 'uw'))
sys.path.insert(0, here)
from chromatix import Chromatix
from lscmesh import block

c = Chromatix(sys.argv[1])
_, _, off, size = c.ent[c.top[('lsc34_ife', 2)]]
for idx in (1, 0, 0, 0, 0, 0):      # core, lens pos, drc, hdr, led 0, aec 0, cct 0
    n, cid = c.elems(off, size)[idx]
    _, _, off, size = c.ent[cid]
    size //= n
assert size == 3568, size
t = [c.floats(off + 16 + k * 888, 221) for k in range(4)]
mesh = {'r': t[0], 'g': [(a + b) / 2 for a, b in zip(t[1], t[2])], 'b': t[3]}
assert abs(min(mesh['g']) - 1.0) < 0.02 and max(mesh['r']) < 6
print(block(mesh, ('8.0', '16.0')))
