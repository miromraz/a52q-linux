#!/usr/bin/env python3
"""Decode the image-quality blocks of com.samsung.tuned.lsi_gc5035_macro.bin
(Qualcomm CamX Chromatix, "Parameter Parser V1.4.0").

usage: chromatix_dump.py TUNED_BIN [--lsc-yaml OUT]

Layout (reverse-engineered, see REPORT.md): the file is the same container as
the sensormodule bins (tools/camx-sensormodule.py). Each leaf block is a
serialised struct: floats/ints in 8-byte slots (value, 4 bytes pad) unless
packed, and every block/entry ends with (count, own descriptor id). The IDs
below are for this one file (A525FXXUAFXL2) and are asserted by name.
"""
import argparse, importlib.util, os, struct

ap = argparse.ArgumentParser()
ap.add_argument('bin'); ap.add_argument('--lsc-yaml')
a = ap.parse_args()
spec = importlib.util.spec_from_file_location(
    'cx', os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       '../../tools/camx-sensormodule.py'))
cx = importlib.util.module_from_spec(spec); spec.loader.exec_module(cx)
C = cx.Camx(a.bin)
BY = {x['id']: x for x in C.desc}

def blk(i, name):
    x = BY[i]
    assert x['name'] == name, (i, x['name'], name)
    return C.d[C.pool_base + x['off']:C.pool_base + x['off'] + x['size']]

def f32(b, w):  # w = 4-byte word index
    return struct.unpack_from('<f', b, 4 * w)[0]

# --- black level: bls12_ife -> mod_bls12_cct_data (14-bit pipeline) ---------
bl = f32(blk(415, 'mod_bls12_cct_data'), 4)
print('BLS12 (IFE) offset %.0f @14bit = %.2f @10bit -> libcamera blackLevel %d'
      % (bl, bl / 16, round(bl / 16) << 6))
for i in (307, 308):
    print('  BLS12 (BPS) entry #%d offset %.0f = %.2f @10bit' % (
        i, f32(blk(i, 'mod_bls12_cct_data'), 4), f32(blk(i, 'mod_bls12_cct_data'), 4) / 16))

# --- CCM: cc13_ipe, 3 AEC (lux index) regions x CCT entries ------------------
aec = blk(511, 'mod_cc13_aec_data')
for r, cid in enumerate((512, 513, 514)):
    e = aec[48 * r:48 * (r + 1)]
    print('CC13 IPE region %d: lux idx %.0f-%.0f, gain %.0f-%.0f' %
          (r, f32(e, 0), f32(e, 2), f32(e, 4), f32(e, 6)))
    b = blk(cid, 'mod_cc13_cct_data')
    for k in range(len(b) // 72):
        v = struct.unpack_from('<18f', b, 72 * k)
        m = v[4:13]
        print('  CCT %5.0f-%5.0f  ccm [%s]' % (v[0], v[2], ', '.join('%.4f' % x for x in m)))

# --- AWB ----------------------------------------------------------------------
rp = blk(121, 'refPtV1')
pts = [(f32(rp, 12 + 4 * i), f32(rp, 14 + 4 * i)) for i in range(10)]
print('AWB refPtV1 (R/G, B/G):', ', '.join('(%.4f, %.4f)' % p for p in pts))
ini = blk(137, 'initDataV1')
print('AWB initDataV1 gains R %.4f G %.4f B %.4f CCT %.0f' %
      (f32(ini, 12), f32(ini, 14), f32(ini, 16), f32(ini, 18)))
sc = blk(138, 'sensorCalV1')
print('AWB sensorCalV1 golden CCTs', [int(f32(sc, 14 + i)) for i in range(6)],
      'R/G %.5f B/G %.5f' % (f32(sc, 20), f32(sc, 22)))

# --- gamma15 (IPE), 257-point curves, 10-bit output --------------------------
for i, name in ((579, 'normal'), (581, 'low light')):
    g = struct.unpack_from('<257f', blk(i, 'mod_gamma15_channel_data'), 8)
    print('gamma15 %-9s y(x) at x=1/64,1/16,1/4,1/2: %s  (x^(1/2.2): 0.151, 0.284, 0.533, 0.730)' % (
        name, ', '.join('%.3f' % (g[k] / 1023) for k in (4, 16, 64, 128))))

# --- AEC ------------------------------------------------------------------------
lt = blk(941, 'luxLumaTargetZone')
zones = [struct.unpack_from('<3f', lt, 0) and (f32(lt, 6 * z), f32(lt, 6 * z + 2), f32(lt, 6 * z + 4))
         for z in range(len(lt) // 24)]
print('AEC luma target (lux idx start, end, target/255):', zones)
kn = blk(1161, 'expKneeEntries')
print('AEC exposure knees (exposure index, gain, exposure time):')
for k in range(7):
    o = 14 + 8 * k
    print('  %6.1f  %5.1fx  1/%.0f s' % (f32(kn, o), f32(kn, o + 2),
                                    1e9 / struct.unpack_from('<I', kn, 4 * (o + 4))[0]))

# --- LSC34 (IFE): 17x13 gain mesh per Bayer channel R, Gr, Gb, B -----------------
def lsc(i):
    b = blk(i, 'mod_lsc34_cct_data' if i != 360 else 'mod_lsc34_golden_cct_data')
    v = struct.unpack_from('<888f', b, 16)  # 4 x (221 gains + 1 pad)
    return [v[c * 222:c * 222 + 221] for c in range(4)]
for i, name in ((358, 'bright'), (359, 'low light'), (360, 'golden')):
    t = lsc(i)
    print('LSC34 %-9s centre/corner gain R %.2f/%.2f G %.2f/%.2f B %.2f/%.2f' % (
        name, min(t[0]), t[0][0], min(t[1]), t[1][0], min(t[3]), t[3][0]))
if a.lsc_yaml:
    t = lsc(358)
    with open(a.lsc_yaml, 'w') as f:
        f.write('# gc5035 macro lens shading, stock Chromatix lsc34_ife (bright table),\n'
                '# 17x13 nodes row-major over the raw frame as streamed, gains >= 1.\n')
        for n, c in (('r', t[0]), ('g', [(x + y) / 2 for x, y in zip(t[1], t[2])]), ('b', t[3])):
            f.write('%s: [\n' % n)
            for row in range(13):
                f.write('  ' + ', '.join('%.4f' % x for x in c[17 * row:17 * row + 17]) + ',\n')
            f.write(']\n')
    print('wrote', a.lsc_yaml)
