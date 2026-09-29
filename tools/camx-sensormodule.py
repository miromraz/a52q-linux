#!/usr/bin/env python3
# camx-sensormodule.py - decode Qualcomm CAMX "QTI Chromatix Header /
# Parameter Parser V1.4.0" sensor-module binaries (Samsung Galaxy A52 4G).
#
# Reverse-engineered layout (little-endian throughout):
#   0x00  char   magic[32]      "QTI Chromatix Header"
#   0x1c  u32    file_size      (overlaps magic tail padding)
#   0x28  char   version[...]   "Parameter Parser V1.4.0 (....)"
#   0xc0  u64    pool_base      absolute file offset of the value/data pool
#   0xc8  u64    pool_size      length of the pool
#   0xf0  descriptor table: fixed 72-byte records until the name is not ASCII
#         struct { char name[32]; s64 type; s64 flag; s64 off; s64 size; s64 id }
#         'off' is RELATIVE to pool_base; 'size' is in bytes; 'id' is a global
#         sequential node id assigned in tree/pre-order.
#
# Values live in the pool. A leaf's (off,size) is its value slice. Container
# nodes serialise their subtree into one pool slice in a tagged post-order
# stream: scalar values, each terminated by the node id they belong to.
#
# sensorDriverData's own blob (pool off 0) carries fixed slots:
#   idx5 = I2C slave address (8-bit), idx8 = sensor-id register address,
#   idx9 = expected sensor-id value, idx10 = id mask (best-effort).
#
# A register setting (regSetting) decodes to entries of
#   [addr, addrType]  (from the tagged blob)   -> register address + addr width
#   [dataType, ...]   (from the tagged blob)   -> data width
#   [delay]           (from the tagged blob)   -> delayUs
# and the register DATA values come from the flat registerData leaf slots.
# Output register lists are [[addr, value, addrBytes, dataBytes, delayUs], ...].
#
# Anything that cannot be decoded confidently is emitted raw (hex / int list).
#
# stdlib only.
import sys, json, struct

class Camx:
    def __init__(self, path):
        self.d = open(path, 'rb').read()
        d = self.d
        self.magic = d[0:0x20].split(b'\0')[0].decode('latin1', 'replace')
        self.version = d[0x28:0x88].split(b'\0')[0].decode('latin1', 'replace')
        self.pool_base = struct.unpack_from('<q', d, 0xc0)[0]
        self.pool_size = struct.unpack_from('<q', d, 0xc8)[0]
        self.desc = self._read_desc()
        self.by_id = {x['id']: x for x in self.desc}

    def _read_desc(self):
        d = self.d
        out = []
        off = 0xf0
        while off + 72 <= len(d):
            name = d[off:off+32].split(b'\0')[0]
            if not name or not all(32 <= c < 127 for c in name):
                break
            t, fl, o, s, i = struct.unpack_from('<5q', d, off + 32)
            out.append({'id': i, 'name': name.decode('latin1'),
                        'type': t, 'flag': fl, 'off': o, 'size': s,
                        'file_off': off})
            off += 72
        return out

    # ---- pool access -------------------------------------------------------
    def _slice(self, off, size):
        a = self.pool_base + off
        return self.d[a:a+size]

    def ints(self, node):
        s = node['size']
        n = s // 8
        if n == 0:
            return []
        return list(struct.unpack_from('<%dq' % n, self.d, self.pool_base + node['off']))

    def string(self, node):
        return self._slice(node['off'], node['size']).split(b'\0')[0].decode('latin1', 'replace')

    def raw_hex(self, node):
        return self._slice(node['off'], node['size']).hex()

    # ---- tagged blob decoder ----------------------------------------------
    # Walk the int64 stream of a container node; buffer scalar values and flush
    # them to leaf `nexttag` whenever the current word equals `nexttag`. Leaf
    # ids of a regSetting/powerSetting are contiguous starting at ownid+1.
    def decode_tagged(self, node, skip_head=2):
        vals = self.ints(node)
        vals = vals[skip_head:]
        nexttag = node['id'] + 1
        leaves = {}
        buf = []
        for v in vals:
            if v == nexttag:
                leaves[nexttag] = buf
                buf = []
                nexttag += 1
            else:
                buf.append(v)
        if buf:
            leaves[nexttag] = buf  # trailing (rare)
        return leaves

    # flat leaf value: read the leaf descriptor slice as a single int (or None)
    def leaf_int(self, node):
        if node['size'] >= 8:
            return struct.unpack_from('<q', self.d, self.pool_base + node['off'])[0]
        return None

# --------------------------------------------------------------------------
POWER_NAMES = {'powerSetting', 'powerUpSequence', 'powerDownSequence'}

def decode_regsetting(cx, node):
    """Return dict with register list [[addr,val,addrBytes,dataBytes,delayUs]]
    plus the raw group data for transparency."""
    leaves = cx.decode_tagged(node)
    base = node['id'] + 1
    # collect flat data values for this regSetting's registerData leaves
    # (leaf ids: base+3k+1). registerData leaf slices hold the real data words.
    regs = []
    k = 0
    while True:
        s_id, d_id, e_id = base + 3*k, base + 3*k + 1, base + 3*k + 2
        if s_id not in leaves and d_id not in leaves:
            break
        sg = leaves.get(s_id, [])
        dg = leaves.get(d_id, [])
        eg = leaves.get(e_id, [])
        addr = sg[0] if len(sg) >= 1 else None
        delay = eg[0] if len(eg) >= 1 else 0
        # data value: prefer the flat registerData leaf slot
        val = None
        nd = cx.by_id.get(d_id)
        if nd is not None:
            val = cx.leaf_int(nd)
        # registerData leaf = (regAddrType, regDataType, ...): CamX
        # I2CRegAddrDataType, 1 = byte, 2 = word. Do NOT infer widths from the
        # values: a 16-bit register written with a small value as one byte
        # lands in the high byte and silently corrupts the table.
        addr_bytes = dg[0] if len(dg) >= 1 and dg[0] in (1, 2) else \
            (2 if (addr is not None and addr > 0xff) else 1)
        data_bytes = dg[1] if len(dg) >= 2 and dg[1] in (1, 2) else \
            (2 if (val is not None and val > 0xff) else 1)
        regs.append([addr, val, addr_bytes, data_bytes, delay])
        k += 1
    return regs

def collect_regsettings(cx):
    """Group regSetting nodes and label each by the nearest preceding
    container/section name in descriptor order."""
    SECTIONS = {'initSettings', 'resolutionData', 'streamConfiguration',
                'masterSettings', 'slaveSettings', 'iHDRSettings',
                'testPatternData', 'SPCSettings', 'powerUpSequence',
                'powerDownSequence', 'activeSettings', 'standbySettings',
                'movieModeSettings', 'stillModeSettings', 'deInitSettings',
                'scenario', 'region', 'centeringOnSettings',
                'centeringOffSettings', 'sceneOisSettings'}
    section = None
    out = []
    for x in cx.desc:
        if x['name'] in SECTIONS:
            section = x['name']
        if x['name'] == 'regSetting':
            regs = decode_regsetting(cx, x)
            out.append({'id': x['id'], 'section': section,
                        'count': len(regs), 'registers': regs})
    return out

def decode_power(cx, node):
    """Power sequence blob is a flat array of [seqType, configValue, delayUs]
    triples (no node-id tags). configValue is a regulator voltage in microvolts
    for supply types, or a pin level. Returns decoded triples + raw ints."""
    iv = cx.ints(node)
    seq = []
    for k in range(0, len(iv) - 2, 3):
        seq.append({'seqType': iv[k], 'configValue': iv[k+1], 'delayUs': iv[k+2]})
    return {'triples': seq, 'raw_ints': iv}

def decode_modes(cx):
    """Parse the resolutionData blob into per-mode records. Each mode is laid
    out as [flags, subCount, nodeTag, lineLength, frameLength, x, y,
    opPixelClock, ..., fps(double)@+10, ...]. Output pixel W/H per mode are not
    stored separately in V1.4.0 (derived from line/frame length minus blanking
    plus the crop region), so line/frame length and op clock are the reliable
    geometry; sensor-wide active W/H comes from streamConfiguration."""
    node = next((x for x in cx.desc if x['name'] == 'resolutionData'), None)
    if not node:
        return []
    v = cx.ints(node)
    ids = set(cx.by_id)
    modes = []
    i = 0
    while i + 11 < len(v):
        # mode start: flags in (2,3,4), a running descriptor id at +2, a
        # plausible pixel clock at +7.
        if v[i] in (2, 3, 4) and v[i+2] in ids and v[i+7] > 1_000_000:
            fps = struct.unpack('<d', struct.pack('<q', v[i+10]))[0]
            modes.append({
                'lineLength': v[i+3], 'frameLength': v[i+4],
                'opPixelClock': v[i+7],
                'fps': round(fps, 3) if 0 < fps < 10000 else None,
                'fps_raw': v[i+10],
                'raw': v[i:i+11],
            })
            i += 11
        else:
            i += 1
    return modes

def named_scalar(cx, name):
    for x in cx.desc:
        if x['name'] == name:
            iv = cx.ints(x)
            if not iv:
                return None
            return iv if len(iv) > 1 else iv[0]
    return None

def build(path):
    cx = Camx(path)
    sdd = cx.by_id.get(2) or next((x for x in cx.desc if x['name'] == 'sensorDriverData'), None)
    sdd_ints = cx.ints(sdd) if sdd else []

    def g(i):
        return sdd_ints[i] if i < len(sdd_ints) else None

    slave8 = g(5)
    id_reg = g(8)
    id_val = g(9)
    id_mask = g(10)

    # sensorName leaf
    sname = None
    for x in cx.desc:
        if x['name'] == 'sensorName':
            sname = cx.string(x)
            break

    # sensor-level register widths: max width seen in the largest reg table
    regsets = collect_regsettings(cx)
    addr_bytes = data_bytes = 1
    if regsets:
        big = max(regsets, key=lambda r: r['count'])
        for r in big['registers']:
            addr_bytes = max(addr_bytes, r[2] or 1)
            data_bytes = max(data_bytes, r[3] or 1)

    # power sequences
    power = {}
    for x in cx.desc:
        if x['name'] in POWER_NAMES:
            power.setdefault(x['name'], []).append(
                {'id': x['id'], 'sequence': decode_power(cx, x)})

    out = {
        'file': path.rsplit('/', 1)[-1],
        'header': {'magic': cx.magic, 'version': cx.version,
                   'pool_base': cx.pool_base, 'pool_size': cx.pool_size,
                   'num_descriptors': len(cx.desc)},
        'sensorName': sname,
        'slaveAddress': ({'bit8': slave8, 'bit7': (slave8 >> 1) if slave8 else None}
                         if slave8 is not None else None),
        # LSI/Samsung sensors probe chip-id register 0x0000, so a zero regAddr
        # is valid; treat the id as present when either reg or value is set.
        'sensorId': ({'regAddr': id_reg, 'value': id_val, 'mask_raw': id_mask}
                     if (id_reg not in (None,) and (id_reg or id_val)) else None),
        'registerWidths': {'addrBytes': addr_bytes, 'dataBytes': data_bytes},
        'sensorI2CFrequencyMode': named_scalar(cx, 'sensorI2CFrequencyMode'),
        'laneAssign_raw': named_scalar(cx, 'laneAssign'),
        'capability_raw': named_scalar(cx, 'capability'),
        'integration_gain_addrs': {
            'shortCoarseIntgTimeAddr': named_scalar(cx, 'shortCoarseIntgTimeAddr'),
            'shortGlobalGainAddr': named_scalar(cx, 'shortGlobalGainAddr'),
            'digitalGlobalGainAddr': named_scalar(cx, 'digitalGlobalGainAddr'),
            'frameLengthLines': named_scalar(cx, 'frameLengthLines'),
        },
        'powerSequences': power,
        'regSettings': regsets,
    }

    # streamConfiguration: [_, csiDataType, _, _, width, height, bpp, _]
    sc = named_scalar(cx, 'streamConfiguration')
    stream = None
    if isinstance(sc, list) and len(sc) >= 7:
        stream = {'csiDataType': sc[1], 'width': sc[4], 'height': sc[5],
                  'bpp': sc[6], 'raw_ints': sc}
    out['streamConfiguration'] = stream
    out['modes'] = decode_modes(cx)
    out['resolutionData_raw'] = named_scalar(cx, 'resolutionData')
    out['integrationInfo_raw'] = named_scalar(cx, 'integrationInfo')
    out['dimension_raw'] = named_scalar(cx, 'dimension')

    out['_summary'] = summarize(out)
    return out

def summarize(o):
    name = o.get('sensorName')
    sa = o.get('slaveAddress') or {}
    sid = o.get('sensorId') or {}
    ninit = 0
    for rs in o.get('regSettings', []):
        ninit = max(ninit, rs['count'])
    b8 = sa.get('bit8')
    b7 = sa.get('bit7')
    reg = sid.get('regAddr')
    val = sid.get('value')
    st = o.get('streamConfiguration') or {}
    modes = o.get('modes') or []
    if modes and st.get('width'):
        mstr = ",".join("%dx%d@%s" % (st['width'], st['height'], m['fps'])
                        for m in modes[:8])
    else:
        mstr = ",".join("LL%d/FL%d@%s" % (m['lineLength'], m['frameLength'], m['fps'])
                        for m in modes[:8]) or "-"
    return ("%s | slave 8-bit=%s 7-bit=%s | id reg=%s val=%s | init=%d regs | modes=%d [%s]"
            % (name,
               hex(b8) if b8 is not None else '?',
               hex(b7) if b7 is not None else '?',
               hex(reg) if reg is not None else '?',
               hex(val) if val is not None else '?',
               ninit, len(modes), mstr))

def main():
    if len(sys.argv) != 2:
        sys.stderr.write("usage: camx-sensormodule.py FILE.bin\n")
        sys.exit(2)
    out = build(sys.argv[1])
    print(json.dumps(out, indent=1))

if __name__ == '__main__':
    main()
