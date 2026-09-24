#!/bin/bash
# Install pmOS split images onto the A52q UFS LUN0 exposed by U-Boot `ums 0 scsi 0`.
# No repartitioning: Samsung ABL checks GPT against the PIT ("GPT and PIT is mismatched"),
# so reuse existing partitions: pmOS boot (FAT ESP) -> cache (600 MiB), root -> userdata.
set -euo pipefail
cd "$(dirname "$0")/out"
BOOT=qcom-sm7125-boot.img ROOT=qcom-sm7125-root.img

part() { readlink -f "/dev/disk/by-partlabel/$1"; }
disk_of() { echo "/dev/$(lsblk -no PKNAME "$1")"; }

C=$(part cache) U=$(part userdata)
D=$(disk_of "$U")
# Sanity: must be the phone's LUN0 (cache, userdata, super and efs on one disk).
for p in cache super efs; do [ "$(disk_of "$(part $p)")" = "$D" ] || { echo "$p not on $D - refusing"; exit 1; }; done
[ "$(stat -c%s $BOOT)" -le "$(sudo blockdev --getsize64 "$C")" ] || { echo "boot image larger than cache"; exit 1; }

sudo dd if=$BOOT of="$C" bs=4M conv=fsync status=progress
sudo dd if=$ROOT of="$U" bs=4M conv=fsync status=progress
sudo e2fsck -fy "$U" && sudo resize2fs "$U"
sync; lsblk -o NAME,SIZE,PARTLABEL,FSTYPE,LABEL,UUID "$C" "$U"
