#!/bin/bash
# Split A52q LUN0 `userdata` (p31) into `linux` (p31, 64 GiB, keeps the pmOS ext4 that lives
# at its start) + a new smaller `userdata` (p32, rest) for LineageOS. GPT-only edit: Samsung
# ABL's GPT-vs-PIT check runs only on Odin Re-Partition, never use Re-Partition afterwards.
# Run while U-Boot "Enable USB mass storage" exposes LUN0. Backups: backup/lun0-gpt-*.bin
set -euo pipefail
LINUX_SIZE=64G
UD_GUID=1B81E7E6-F50D-419B-A739-2AEEF8DA3335   # Samsung: type GUID == unique GUID

part() { readlink -f "/dev/disk/by-partlabel/$1"; }
disk_of() { echo "/dev/$(lsblk -no PKNAME "$1")"; }

if [ -e /dev/disk/by-partlabel/linux ]; then echo "already split"; lsblk -o NAME,SIZE,PARTLABEL "$(disk_of "$(part linux)")" | tail -3; exit 0; fi
U=$(part userdata); D=$(disk_of "$U")
for p in cache super efs; do [ "$(disk_of "$(part $p)")" = "$D" ] || { echo "$p not on $D - refusing"; exit 1; }; done
[ "$U" = "${D}31" ] || { echo "userdata is not partition 31 - refusing"; exit 1; }
! grep -q "^$U " /proc/mounts || { echo "$U is mounted"; exit 1; }
S=$(sudo sgdisk -i 31 "$D" | awk '/First sector/{print $3}')

sudo e2fsck -fy "$U"
sudo resize2fs "$U" 60G
sudo sgdisk -d 31 \
	-n 31:"$S":+"$LINUX_SIZE" -c 31:linux -t 31:8300 \
	-n 32:0:0 -c 32:userdata -t 32:"$UD_GUID" -u 32:"$UD_GUID" "$D"
sudo partprobe "$D"; sleep 2
sudo resize2fs "$(part linux)"
sudo wipefs -a "$(part userdata)"   # LineageOS recovery formats it
sudo sgdisk -v "$D"; lsblk -o NAME,SIZE,PARTLABEL,FSTYPE,LABEL "$D" | tail -4
