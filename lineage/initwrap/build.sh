#!/bin/bash
# Build the static aarch64 /init shim, splice it into the LineageOS boot
# ramdisk (rename original init -> init.real, add shim as init), and repack
# the header-v2 boot image as lineage-in-recovery.img. No root needed: the
# cpio is rewritten in python with root ownership forced in the headers.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LIN="$(cd "$HERE/.." && pwd)"          # .../lineage
OUT="$LIN/lineage-in-recovery.img"
SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT

echo "[1/5] compile static aarch64 shim"
aarch64-linux-gnu-gcc -static -Os -Wall -o "$SCRATCH/init" "$HERE/initwrap.c"
file "$SCRATCH/init" | sed 's/^/      /'

echo "[2/5] rewrite ramdisk cpio (init -> init.real, add shim)"
gzip -dc "$LIN/u_boot.img/ramdisk" > "$SCRATCH/ramdisk.cpio"
python3 "$HERE/repack_cpio.py" "$SCRATCH/ramdisk.cpio" "$SCRATCH/init" "$SCRATCH/new.cpio"
gzip -9 -n < "$SCRATCH/new.cpio" > "$SCRATCH/new.ramdisk.gz"

echo "[3/5] repack boot image (header v2)"
# boot.args carries relative paths (u_boot.img/...), so run from lineage/.
# --ramdisk appears twice; argparse keeps the last, overriding to our ramdisk.
( cd "$LIN" && eval mkbootimg $(cat boot.args) \
    --ramdisk "$SCRATCH/new.ramdisk.gz" \
    --recovery_dtbo u_recovery.img/recovery_dtbo \
    -o "$OUT" )
ls -l "$OUT" | sed 's/^/      /'

echo "[4/5] unpack rebuilt image for verification"
VER="$SCRATCH/verify"
mkdir -p "$VER"
unpack_bootimg --boot_img "$OUT" --out "$VER" >/dev/null

echo "[5/5] verify kernel/dtb/recovery_dtbo bytes unchanged + ramdisk listing"
cmp "$VER/kernel"       "$LIN/u_boot.img/kernel"              && echo "      kernel: identical"
cmp "$VER/dtb"          "$LIN/u_boot.img/dtb"                 && echo "      dtb: identical"
cmp "$VER/recovery_dtbo" "$LIN/u_recovery.img/recovery_dtbo"  && echo "      recovery_dtbo: identical"
echo "      ramdisk entries:"
gzip -dc "$VER/ramdisk" | cpio -itv 2>/dev/null | sed 's/^/        /'
echo "DONE: $OUT"
