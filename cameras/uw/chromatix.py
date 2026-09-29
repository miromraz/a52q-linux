#!/usr/bin/env python3
"""Decoder for QTI CamX "QTI Chromatix Header / Parameter Parser V1.4.0" blobs
(com.samsung.tuned.*.bin tuning and com.samsung.sensormodule.*.bin).

Layout (little-endian), reverse-engineered on the Galaxy A52 5G blobs:
  0x00a0  3 x {u64 type, u64 offset, u64 size}: 0 = symbol table,
          1 = data pool, 2 = tuning-mode tree (24-byte records)
  symbol table: 72-byte entries {u64 id; char name[40]; s32 mode; u32 pad;
          u64 offset (in pool); u64 size}. mode = -1 for child blobs; for
          top-level modules it is the tuning-mode node (1 bps, 2 ife, 3 ipe,
          4 sw, 5 stats defaults; larger ids are per-usecase overrides).
  struct blobs: every scalar field takes an 8-byte slot (float in the low
          4 bytes, doubles in sensor modules); a sub-struct or array is a
          {u64 count, u64 id} pair pointing at another blob. Arrays of
          scalars are packed 4-byte values padded to 8 bytes (a 17x13 LSC
          table is 221 floats + 4 bytes).

Usage: chromatix.py FILE.bin                 list top-level modules
       chromatix.py FILE.bin MODULE MODE     dump a module tree
"""
import struct, sys


class Chromatix:
    def __init__(self, path):
        self.d = d = open(path, 'rb').read()
        secs = [struct.unpack_from('<QQQ', d, 0xa0 + 24 * i) for i in range(3)]
        self.pool = secs[1][1]
        self.ent, self.top = {}, {}
        for i in range(secs[0][2] // 72):
            o = secs[0][1] + 72 * i
            eid, = struct.unpack_from('<Q', d, o)
            name = d[o + 8:o + 48].split(b'\0')[0].decode()
            mode, _, off, size = struct.unpack_from('<iIQQ', d, o + 48)
            self.ent[eid] = (name, mode, off, size)
            if mode != -1:
                self.top.setdefault((name, mode), eid)

    def slots(self, off, size):
        return [self.d[self.pool + off + 8 * i:self.pool + off + 8 * i + 8]
                for i in range(size // 8)]

    def ref(self, s0, s1):
        """(count, child id) if the slot pair is an array/struct reference."""
        n, cid = struct.unpack('<q', s0)[0], struct.unpack('<q', s1)[0]
        e = self.ent.get(cid)
        if 0 < n < 100000 and e and e[1] == -1 and e[3] > 0 and e[3] % n == 0:
            return n, cid
        return None

    def elems(self, off, size):
        """[(count, id)] references found in a struct blob, in field order."""
        sl, out, i = self.slots(off, size), [], 0
        while i + 1 < len(sl):
            r = self.ref(sl[i], sl[i + 1])
            if r:
                out.append(r); i += 2
            else:
                i += 1
        return out

    def floats(self, off, n):
        return list(struct.unpack_from('<%df' % n, self.d, self.pool + off))

    def dump(self, off, size, ind=0, depth=12):
        sl = self.slots(off, size)
        i, line = 0, []
        while i < len(sl):
            r = self.ref(sl[i], sl[i + 1]) if i + 1 < len(sl) else None
            if r:
                if line:
                    print(' ' * ind + ' '.join(line)); line = []
                n, cid = r
                name, _, coff, csize = self.ent[cid]
                print(' ' * ind + '[%d] %s x%d (id %d, %dB)' % (i, name, n, cid, csize))
                if depth:
                    for k in range(n):
                        print(' ' * (ind + 2) + '#%d' % k)
                        self.dump(coff + k * csize // n, csize // n, ind + 4, depth - 1)
                i += 2
                continue
            if len(sl) > 60:
                print(' ' * ind + '<%d-byte table>' % size)
                return
            v = struct.unpack('<q', sl[i])[0]
            f = struct.unpack('<f', sl[i][:4])[0]
            line.append('[%d]%s' % (i, ('%.6g' % f) if sl[i][4:] == b'\0' * 4 and abs(v) >= 0x10000 else v))
            i += 1
        if line:
            print(' ' * ind + ' '.join(line))


if __name__ == '__main__':
    c = Chromatix(sys.argv[1])
    if len(sys.argv) == 2:
        for (name, mode), eid in sorted(c.top.items(), key=lambda x: x[1]):
            print(eid, name, mode)
    else:
        _, _, off, size = c.ent[c.top[(sys.argv[2], int(sys.argv[3]))]]
        c.dump(off, size)
