#!/usr/bin/env python3
"""Stats + development of one camss RAW10-packed (pRAA) frame.

usage: rawdev.py in.raw [out.png] [--w 2592 --h 1944 --bpl 3248 --order rggb
                         --bl 64 --wb R,B --ccm 9 floats --gamma 2.2 --rot 270]
Without --wb, grey-world. Without --ccm, identity. Prints per-channel stats
(10-bit codes) so black level / clipping / colour balance can be compared.
"""
import argparse
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('src'); ap.add_argument('dst', nargs='?')
ap.add_argument('--w', type=int, default=2592); ap.add_argument('--h', type=int, default=1944)
ap.add_argument('--bpl', type=int, default=3248); ap.add_argument('--order', default='rggb')
ap.add_argument('--bl', type=float, default=64); ap.add_argument('--wb')
ap.add_argument('--ccm'); ap.add_argument('--gamma', type=float, default=2.2)
ap.add_argument('--rot', type=int, default=270); ap.add_argument('--gain', type=float, default=0)
a = ap.parse_args()

raw = np.fromfile(a.src, np.uint8)[:a.h * a.bpl].reshape(a.h, a.bpl)
p = raw[:, :a.w // 4 * 5].reshape(a.h, -1, 5).astype(np.uint16)
px = np.stack([(p[:, :, i] << 2) | ((p[:, :, 4] >> (2 * i)) & 3) for i in range(4)], -1)
b = px.reshape(a.h, a.w).astype(np.float32)
pos = {'rggb': ((0, 0), (0, 1), (1, 0), (1, 1)), 'bggr': ((1, 1), (0, 1), (1, 0), (0, 0)),
       'grbg': ((0, 1), (0, 0), (1, 1), (1, 0)), 'gbrg': ((1, 0), (0, 0), (1, 1), (0, 1))}[a.order]
R, G1, G2, B = (b[y::2, x::2] for y, x in pos)
for n, c in zip(('R', 'Gr', 'Gb', 'B'), (R, G1, G2, B)):
    print('%-2s mean %7.2f  p0.1 %4d  p1 %4d  p50 %4d  p99 %4d  max %4d  clip%% %.3f' %
          (n, c.mean(), *np.percentile(c, (0.1, 1, 50, 99)), c.max(), 100 * (c >= 1020).mean()))
if not a.dst:
    raise SystemExit
from PIL import Image
rgb = np.dstack([R, (G1 + G2) / 2, B]) - a.bl
rgb = np.clip(rgb, 0, None) / (1023 - a.bl)
if a.wb:
    gr, gb = map(float, a.wb.split(','))
else:
    m = rgb.reshape(-1, 3).mean(0); gr, gb = m[1] / m[0], m[1] / m[2]
rgb *= [gr, 1, gb]
print('wb gains R %.3f B %.3f' % (gr, gb))
if a.ccm:
    M = np.array(list(map(float, a.ccm.split(',')))).reshape(3, 3)
    rgb = rgb @ M.T
k = a.gain or min(0.4 / max(np.percentile(rgb[..., 1], 50), 1e-4),
                 1 / max(np.percentile(rgb, 99.5), 1e-4))
rgb = np.clip(rgb * k, 0, 1) ** (1 / a.gamma)
img = Image.fromarray((rgb * 255).astype(np.uint8))
if a.rot:
    img = img.rotate(-a.rot, expand=True)
img.save(a.dst)
print('%s %dx%d exposure scale %.2f' % (a.dst, img.width, img.height, k))
