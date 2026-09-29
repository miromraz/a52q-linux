#!/usr/bin/env python3
"""chromatix-decode.py TUNED.bin [module ...]

Minimal decoder for Qualcomm CamX "QTI Chromatix Header / Parameter Parser
V1.4.0" tuning files (com.samsung.tuned.<vendor>_<sensor>.bin).

Layout (little endian), found by hand on com.samsung.tuned.sony_imx616.bin:
  0xc0 u64 pool_base   file offset of the data pool
  0xf0 descriptor table, 72-byte records until the name stops being ASCII:
       char name[32]; s64 version; s64 flags; s64 off; s64 size; s64 id
       ('off' is relative to pool_base). Records come in two groups:
       - "mod_<module>_<trigger>_data" leaves (ids >= ~536) holding the data,
       - top-level module instances ("cc13_ipe", "lsc34_ife", ...; ids 2..),
         the first ~150 are the default tuning mode, later ones are per-mode
         overrides. A top-level record's payload names its first child id.
  Scalars occupy 8-byte slots (int64, or float32 in the low half); arrays
  are packed float32. Trigger nodes are [start, end, ..., count, next_id].

Decoded here (default tuning mode):
  cc13  per lux-zone x CCT 3x3 colour matrices (row-major RGB, rows sum to 1)
  lsc34 17x13 R/Gr/Gb/B gain meshes
  gamma15 257-entry 10-bit tone curve per channel
  bls12 black level offset (14-bit IFE domain)
  MWBGainV1 manual white-balance R/G/B gains per illuminant
"""
import struct
import sys

import numpy as np


class Tuned:
    def __init__(self, path):
        self.d = open(path, 'rb').read()
        self.pool = struct.unpack_from('<q', self.d, 0xc0)[0]
        self.recs = []
        off = 0xf0
        while off + 72 <= len(self.d):
            name = self.d[off:off + 32].split(b'\0')[0]
            if not name or not all(32 <= c < 127 for c in name):
                break
            _, _, o, s, i = struct.unpack_from('<5q', self.d, off + 32)
            self.recs.append({'n': len(self.recs), 'name': name.decode(),
                              'off': o, 'size': s, 'id': i})
            off += 72
        self.byid = {r['id']: r for r in self.recs}

    def f32(self, r):
        b = self.d[self.pool + r['off']:self.pool + r['off'] + r['size']]
        return np.frombuffer(b[:len(b) // 4 * 4], '<f4')

    def i32(self, r):
        b = self.d[self.pool + r['off']:self.pool + r['off'] + r['size']]
        return np.frombuffer(b[:len(b) // 4 * 4], '<i4')

    def children(self, top_id, name):
        """mod_* records following the top-level instance's first child id."""
        first = min(x for x in self.i32(self.byid[top_id])[::2] if x >= 536)
        start = self.byid[first]['n']
        out = []
        for r in self.recs[start:]:
            if r['name'] == name:
                out.append(r)
            elif out and r['name'] != name and not r['name'].startswith('mod_'):
                break
            elif out and r['name'].startswith('mod_') and \
                    r['name'].split('_')[1] != name.split('_')[1]:
                break
        return out

    def first(self, name):
        return next(r for r in self.recs if r['name'] == name)


def ccms(t):
    top = t.first('cc13_ipe')['id']
    aec = t.children(top, 'mod_cc13_aec_data')[0]
    zones = t.f32(aec).reshape(-1, 12)
    cct = iter(t.children(top, 'mod_cc13_cct_data'))
    for z in zones:
        r = next(cct)
        v = t.f32(r).reshape(-1, 18)
        print(f"lux index {z[0]:.0f}-{z[2]:.0f}:")
        for e in v:
            m = e[4:13].reshape(3, 3)
            print(f"  CCT {e[0]:.0f}-{e[2]:.0f} K  " +
                  " | ".join(" ".join(f"{x:7.4f}" for x in row) for row in m))


def lsc(t):
    r = t.children(t.first('lsc34_bps')['id'], 'mod_lsc34_cct_data')[0]
    v = t.f32(r)[4:]
    m = np.array([v[k * 222:k * 222 + 221] for k in range(4)]).reshape(4, 13, 17)
    for c, n in zip(m, ('R', 'Gr', 'Gb', 'B')):
        print(f"{n}: centre {c[6, 8]:.3f} corners "
              f"{c[0, 0]:.2f} {c[0, -1]:.2f} {c[-1, 0]:.2f} {c[-1, -1]:.2f}")


def gamma(t):
    r = t.children(t.first('gamma15_ipe')['id'], 'mod_gamma15_channel_data')[0]
    g = t.f32(r)[2:259]
    print('gamma15 (257 entries, 10 bit):', ' '.join(f"{x:.0f}" for x in g[::16]))


def bls(t):
    for r in t.children(t.first('bls12_ife')['id'], 'mod_bls12_cct_data'):
        v = t.f32(r)
        print(f"bls12 CCT {v[0]:.0f}-{v[2]:.0f}: offset {v[4]:.0f} (14 bit) "
              f"= {v[4] / 16:.2f} @ 10 bit")


def mwb(t):
    v = t.f32(t.first('MWBGainV1'))[12:]
    for k in range(10):
        r, g, b = v[k * 6], v[k * 6 + 2], v[k * 6 + 4]
        print(f"MWB[{k}] R {r:.4f} G {g:.4f} B {b:.4f}")


def main():
    t = Tuned(sys.argv[1])
    what = sys.argv[2:] or ['ccm', 'lsc', 'gamma', 'bls', 'mwb']
    for w in what:
        {'ccm': ccms, 'lsc': lsc, 'gamma': gamma, 'bls': bls, 'mwb': mwb}[w](t)


if __name__ == '__main__':
    main()
