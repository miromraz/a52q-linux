#!/bin/bash
# Write the BengalOS a52q raw image (nested GPT, 4 KiB sectors) into the `linux` partition while U-Boot
# "Enable USB mass storage" exposes LUN0. Streams from the build container (laptop disk is too small),
# verifies by sha256, and wipes the old pmOS ESP in `cache` so EFI boot only finds BengalOS.
set -euo pipefail
RAW=${1:-/mnt/sunfish-image/a52q/out/BengalOS_0.26.0924.1.raw}

part() { readlink -f "/dev/disk/by-partlabel/$1"; }
disk_of() { echo "/dev/$(lsblk -no PKNAME "$1")"; }

L=$(part linux) C=$(part cache); D=$(disk_of "$L")
for p in cache userdata super efs; do [ "$(disk_of "$(part $p)")" = "$D" ] || { echo "$p not on $D - refusing"; exit 1; }; done
! grep -qE "^($L|$C) " /proc/mounts || { echo "target mounted"; exit 1; }
SIZE=$(ssh build stat -c%s "$RAW")
[ "$SIZE" -le "$(sudo blockdev --getsize64 "$L")" ] || { echo "image larger than linux partition"; exit 1; }

ssh build cat "$RAW" | sudo dd of="$L" bs=4M oflag=direct status=progress
LOCAL=$(sudo head -c "$SIZE" "$L" | sha256sum | cut -d' ' -f1)
REMOTE=$(ssh build sha256sum "$RAW" | cut -d' ' -f1)
[ "$LOCAL" = "$REMOTE" ] || { echo "CHECKSUM MISMATCH $LOCAL != $REMOTE"; exit 1; }
echo "verified $LOCAL"

sudo wipefs -a "$C"
sync; sudo sgdisk -p "$L" | tail -6
