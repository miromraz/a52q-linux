#!/usr/bin/env python3
"""geom.py IMG.ppm MODE_WxMODE_H: geometry of s5kgw1p test patterns through the soft ISP.
Colour bars: 8 bars of MODE_W/8 sensor px (white yellow cyan green magenta red blue black).
Fade-to-grey: same bars, pattern restarts every 512 sensor rows (measured on the native
4:3 mode). Prints horizontal/vertical scale (equal = no anamorphic stretch) and which
sensor pixel lands on the output centre (mode centre = centred crop)."""
import sys
import numpy as np
from PIL import Image

PERIOD = 512
BARS = ['white', 'yellow', 'cyan', 'green', 'magenta', 'red', 'blue', 'black']
RGB = np.array([[1, 1, 1], [1, 1, 0], [0, 1, 1], [0, 1, 0], [1, 0, 1], [1, 0, 0], [0, 0, 1], [0, 0, 0]])

a = np.asarray(Image.open(sys.argv[1]).convert('RGB')).astype(int)
H, W = a.shape[:2]
mw, mh = map(int, sys.argv[2].split('x'))
bw = mw / 8
# classify a saturated row: just below a fade restart, or the top row
c0 = a[:, W // 2].sum(axis=1)
r0 = [y for y in range(1, H - 3) if c0[y - 1] - c0[y] > 150]
row = a[r0[0] + 2 if r0 else 2]
cls = np.array([int(np.argmin(((RGB * 255 - p) ** 2).sum(1))) for p in row])
edges = [x for x in range(1, W) if cls[x] != cls[x - 1]]
bnd = [(x, cls[x]) for i, x in enumerate(edges) if i + 1 == len(edges) or edges[i + 1] - x > 8]
bnd = [(x, k) for x, k in bnd if 0 < k]          # boundary at left edge of bar k
xs = np.array([x for x, _ in bnd], float)
ks = np.array([k for _, k in bnd], float)
sx, cx = np.polyfit(ks * bw, xs, 1)             # out_x = sx * sensor_x + cx
sensor_x_centre = (W / 2 - cx) / sx
print(f'{sys.argv[1]}: {W}x{H} from {mw}x{mh}')
print(f'  bar boundaries {[(int(x), BARS[k]) for x, k in bnd]}')
print(f'  horizontal scale {sx:.4f}; output centre = sensor x {sensor_x_centre:.0f} (mode centre {mw/2:.0f})')
xc = int(bnd[0][0] + sx * bw / 2) if bnd else W // 2
col = a[:, xc].sum(axis=1)
j = [y for y in range(1, H) if col[y - 1] - col[y] > 150]
j = [y for i, y in enumerate(j) if i == 0 or y - j[i - 1] > 4]
if len(j) >= 2:
    sy = float(np.median(np.diff(j))) / PERIOD
    print(f'  fade restarts at rows {j} -> vertical scale {sy:.4f}; sx/sy = {sx / sy:.4f}')
    # restart k*512 sensor rows lands at out_y = sy * (512k) + cy; phase of the centre:
    ph = ((H / 2 - j[0]) / sy) % PERIOD
    ph_c = (mh / 2) % PERIOD
    print(f'  output centre row sits {ph:.0f} rows after a restart (centred crop expects {ph_c:.0f})')
elif j:
    print(f'  fade restarts at rows {j}')
