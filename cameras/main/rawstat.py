#!/usr/bin/env python3
# rawstat.py - stats / preview for camss RDI RAW10-CSI2P frames of the s5kgw1p.
#   rawstat.py FILE [W H STRIDE] [--png out.png] [--bars]
# Prints per-Bayer-site mean/std/percentiles (sites named by position 00 01 10 11),
# optional 2x2-binned grey-world PNG, and with --bars the column-band means of
# row 0/1 (to identify the colour-bar test pattern -> Bayer order).
import sys
import numpy as np


def load(path, w=4624, h=3468, stride=5792):
    raw = np.fromfile(path, dtype=np.uint8)[:h * stride].reshape(h, stride)
    g = w // 4
    p = raw[:, :g * 5].reshape(h, g, 5).astype(np.uint16)
    px = np.empty((h, g, 4), np.uint16)
    for i in range(4):
        px[:, :, i] = (p[:, :, i] << 2) | ((p[:, :, 4] >> (2 * i)) & 3)
    return px.reshape(h, w)


def main():
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    opts = sys.argv[1:]
    w, h, s = (int(x) for x in a[1:4]) if len(a) >= 4 else (4624, 3468, 5792)
    b = load(a[0], w, h, s)
    for dy in (0, 1):
        for dx in (0, 1):
            c = b[dy::2, dx::2].astype(np.float64)
            print(f"site{dy}{dx}: mean {c.mean():7.2f} std {c.std():6.2f} "
                  f"p1 {np.percentile(c, 1):5.0f} p50 {np.percentile(c, 50):5.0f} "
                  f"p99 {np.percentile(c, 99):5.0f} max {c.max():5.0f}")
    rows_filled = int((b.max(axis=1) > 0).sum())
    print(f"rows with data {rows_filled}/{h}")
    if "--bars" in opts:
        for dy in (0, 1):
            for dx in (0, 1):
                r = b[dy::2, dx::2][:16].mean(axis=0)
                n = 8
                print(f"site{dy}{dx} bars:", [int(r[i * len(r) // n:(i + 1) * len(r) // n].mean()) for i in range(n)])
    if "--png" in opts:
        from PIL import Image
        out = opts[opts.index("--png") + 1]
        f = np.clip(b.astype(np.float32) - 64, 0, None)
        s00, s01, s10, s11 = f[0::2, 0::2], f[0::2, 1::2], f[1::2, 0::2], f[1::2, 1::2]
        # GRBG: 00=Gr 01=R 10=B 11=Gb
        rgb = np.dstack([s01, (s00 + s11) / 2, s10])
        m = rgb.reshape(-1, 3).mean(axis=0)
        rgb *= m.mean() / np.maximum(m, 1e-6)
        rgb = np.clip(rgb / max(np.percentile(rgb, 99), 1e-6), 0, 1) ** (1 / 2.2)
        Image.fromarray((rgb * 255).astype(np.uint8)).save(out)
        print("wrote", out)


if __name__ == "__main__":
    main()
