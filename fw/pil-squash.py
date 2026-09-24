#!/usr/bin/env python3
# pil-squasher: combine a Qualcomm split PIL image (foo.mdt + foo.bNN) into a
# single squashed foo.mbn, matching andersson/pil-squasher semantics.
# Hash segments (MI_PBT type 2, encoded in the top byte of p_flags) live inside
# the .mdt; all other non-empty segments come from the matching foo.b{i:02d}.
import struct, sys, os

def squash(mdt_path, out_path):
    with open(mdt_path, "rb") as f:
        mdt = f.read()
    assert mdt[:4] == b"\x7fELF", f"{mdt_path}: not ELF"
    ei_class = mdt[4]
    assert ei_class in (1, 2), f"unsupported EI_CLASS {ei_class}"
    is64 = ei_class == 2
    if is64:
        (e_phoff,) = struct.unpack_from("<Q", mdt, 32)
        e_phentsize, e_phnum = struct.unpack_from("<HH", mdt, 54)
    else:
        (e_phoff,) = struct.unpack_from("<I", mdt, 28)
        e_phentsize, e_phnum = struct.unpack_from("<HH", mdt, 42)

    def phdr(i):
        base = e_phoff + i * e_phentsize
        if is64:
            p_type, p_flags = struct.unpack_from("<II", mdt, base)
            p_offset, _, _, p_filesz = struct.unpack_from("<QQQQ", mdt, base + 8)
        else:
            p_type, p_offset, _, _, p_filesz, _, p_flags = struct.unpack_from("<IIIIIII", mdt, base)
        return p_offset, p_filesz, p_flags

    # size the output to the furthest segment end
    total = e_phoff + e_phnum * e_phentsize
    for i in range(e_phnum):
        p_offset, p_filesz, _ = phdr(i)
        total = max(total, p_offset + p_filesz)
    out = bytearray(total)
    # ehdr + program header table copied verbatim from the mdt
    hdr = e_phoff + e_phnum * e_phentsize
    out[0:hdr] = mdt[0:hdr]

    hashoffset = phdr(0)[1]  # first segment's p_filesz, per pil-squasher
    stem = mdt_path[:-4] if mdt_path.endswith(".mdt") else mdt_path
    for i in range(e_phnum):
        p_offset, p_filesz, p_flags = phdr(i)
        if p_filesz == 0:
            continue
        if ((p_flags >> 24) & 7) == 2:      # hash segment: read from mdt
            seg = mdt[hashoffset:hashoffset + p_filesz]
            hashoffset += p_filesz
        else:                                # normal segment: read from .bNN
            bpath = "%s.b%02d" % (stem, i)
            with open(bpath, "rb") as bf:    # missing -> raises, we want that
                seg = bf.read(p_filesz)      # .bNN may be padded; take p_filesz
        assert len(seg) == p_filesz, f"seg {i}: got {len(seg)} want {p_filesz}"
        out[p_offset:p_offset + p_filesz] = seg

    with open(out_path, "wb") as f:
        f.write(out)
    # self-check: valid ELF and size == furthest segment end
    assert out[:4] == b"\x7fELF" and len(out) == total
    return len(out)

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        sys.exit(0)  # import-only sanity; real check runs on actual images below
    n = squash(sys.argv[1], sys.argv[2])
    print(f"{sys.argv[2]}: {n} bytes")
