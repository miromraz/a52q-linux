#!/usr/bin/env python3
"""Rewrite a newc (SVR4) cpio archive with no root privileges.

Renames the `init` entry to `init.real`, appends a new `init` entry (mode
0750, uid/gid 0) holding the shim binary, and keeps every other entry byte
for byte. Ownership is forced in the header so the result is correct even
though we run as an unprivileged user.

Usage: repack_cpio.py <in.cpio> <shim-binary> <out.cpio>
"""
import sys

FIELDS = ("ino", "mode", "uid", "gid", "nlink", "mtime", "filesize",
          "devmajor", "devminor", "rdevmajor", "rdevminor", "namesize", "check")


def pad4(n):
    return (4 - (n % 4)) % 4


def parse(data):
    entries, off = [], 0
    while True:
        magic = data[off:off + 6]
        if magic != b"070701":
            raise SystemExit("not a newc cpio (bad magic at %d)" % off)
        vals = {f: int(data[off + 6 + i * 8: off + 6 + i * 8 + 8], 16)
                for i, f in enumerate(FIELDS)}
        off += 110
        name = data[off:off + vals["namesize"] - 1]  # drop NUL
        off += vals["namesize"]
        off += pad4(110 + vals["namesize"])
        fdata = data[off:off + vals["filesize"]]
        off += vals["filesize"]
        off += pad4(vals["filesize"])
        if name == b"TRAILER!!!":
            break
        entries.append([name, vals, fdata])
    return entries


def emit(name, vals, fdata):
    hdr = b"070701" + b"".join(b"%08X" % vals[f] for f in FIELDS)
    rec = hdr + name + b"\0"
    rec += b"\0" * pad4(len(rec))
    rec += fdata
    rec += b"\0" * pad4(len(fdata))
    return rec


def main():
    src, shim, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(src, "rb") as f:
        entries = parse(f.read())
    with open(shim, "rb") as f:
        shim_data = f.read()

    max_ino = max((v["ino"] for _, v, _ in entries), default=0)
    saw_init = False
    for e in entries:
        if e[0] == b"init":
            e[0] = b"init.real"      # keep original mode/ownership/data
            e[1]["namesize"] = len(e[0]) + 1   # name grew: fix header field
            saw_init = True
    if not saw_init:
        raise SystemExit("no `init` entry found in ramdisk")

    # new shim init: regular file, 0750, root:root
    shim_hdr = {"ino": max_ino + 1, "mode": 0o100750, "uid": 0, "gid": 0,
                "nlink": 1, "mtime": 0, "filesize": len(shim_data),
                "devmajor": 0, "devminor": 0, "rdevmajor": 0, "rdevminor": 0,
                "namesize": len(b"init") + 1, "check": 0}
    entries.append([b"init", shim_hdr, shim_data])

    out = b"".join(emit(n, v, d) for n, v, d in entries)
    trailer = {"ino": 0, "mode": 0, "uid": 0, "gid": 0, "nlink": 1, "mtime": 0,
               "filesize": 0, "devmajor": 0, "devminor": 0, "rdevmajor": 0,
               "rdevminor": 0, "namesize": len(b"TRAILER!!!") + 1, "check": 0}
    out += emit(b"TRAILER!!!", trailer, b"")
    out += b"\0" * pad4(len(out))    # pad archive to 512? newc uses 4; kernel ok
    with open(dst, "wb") as f:
        f.write(out)


if __name__ == "__main__":
    main()
