#!/usr/bin/env python3
"""Read the per-camera LSC mesh dumps (cameras/*/…-lsc*.yaml, several ad-hoc
layouts) into {r, g, b} lists of 17x13 floats, and print them as a libcamera
soft-ISP 'Lsc' block (as consumed by the LSC patch of this series).

  lscmesh.py MESHFILE [fadeStart fadeEnd]
"""
import re, sys

GRID = (17, 13)


def load(path):
    text = re.sub(r'#.*', '', open(path).read())
    # section name followed by everything up to the next section name
    secs = dict(re.findall(r'(?m)^\s*(r|g|gr|gb|b)\s*:\s*((?:(?!^\s*(?:r|g|gr|gb|b)\s*:).)*)',
                           text, re.S))
    t = {k: [float(x) for x in re.findall(r'[-+]?\d+\.\d+', v)] for k, v in secs.items()}
    if 'g' not in t:
        t['g'] = [(a + b) / 2 for a, b in zip(t['gr'], t['gb'])]
    n = GRID[0] * GRID[1]
    for k in 'rgb':
        assert len(t[k]) == n, (path, k, len(t[k]))
        assert min(t[k]) >= 0.99 and max(t[k]) < 8, (path, k, min(t[k]), max(t[k]))
    return {k: t[k] for k in 'rgb'}


def block(t, fade=None, indent='  '):
    out = [indent + '- Lsc:', indent + '    grid: [ %d, %d ]' % GRID]
    if fade:
        out.append(indent + '    fadeGain: [ %s, %s ]' % fade)
    for k in 'rgb':
        rows = [', '.join('%.4f' % x for x in t[k][i:i + GRID[0]])
                for i in range(0, len(t[k]), GRID[0])]
        out.append(indent + '    %s: [\n' % k + ',\n'.join(indent + '        ' + r for r in rows) + ' ]')
    return '\n'.join(out)


if __name__ == '__main__':
    t = load(sys.argv[1])
    print(block(t, tuple(sys.argv[2:4]) if len(sys.argv) > 3 else None))
