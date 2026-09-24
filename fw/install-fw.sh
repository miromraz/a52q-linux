#!/usr/bin/env bash
# install-fw.sh - install proprietary firmware onto a Samsung Galaxy A52 4G
# (samsung-a52q, SM7125) running postmarketOS, over SSH.
#
# Pulls the split PIL images from the phone's read-only Android partitions
# (apnhlos + modem), squashes them into single .mbn files on the laptop, and
# installs them to /lib/firmware on the phone's root filesystem, then updates
# the initramfs so the builtin DRM/MSM GPU firmware is present at early probe.
#
# Idempotent: safe to re-run. Only ever writes to the phone's root fs;
# Android partitions are mounted read-only.
#
# Usage: install-fw.sh [--reboot]   (--reboot: reboot + wait + run acceptance checks)
set -euo pipefail

PHONE=user@172.16.42.1
PW=a52q
HERE=$(cd "$(dirname "$0")" && pwd)
SQUASH="$HERE/pil-squash.py"

SSHOPT=(-q -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15)
ssh_() { ssh "${SSHOPT[@]}" "$PHONE" "$@"; }
# run a command as root on the phone (busybox sudo, password on stdin)
rsudo() { ssh_ "echo $PW | sudo -S -p '' sh -c '$1'"; }

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# firmware-name paths come straight from the a52q device tree:
#   qcom/sm7125/a52q/{adsp,cdsp,ipa_fws,venus,modem,a615_zap}.mbn
#   qca/sm7125/a52q/apnv11.bin  (BT NVM)
# Split PIL sources live under image/ on apnhlos (adsp..zap, wlan) and modem (modem).
NH_IMAGES="adsp cdsp ipa_fws venus a615_zap"   # on apnhlos partition
DSP_IMAGES="modem"                              # on modem partition

echo "== ensuring Android firmware partitions are mounted read-only =="
rsudo 'mountpoint -q /mnt/nh  || { mkdir -p /mnt/nh;  mount -o ro /dev/disk/by-partlabel/apnhlos /mnt/nh; }'
rsudo 'mountpoint -q /mnt/dsp || { mkdir -p /mnt/dsp; mount -o ro /dev/disk/by-partlabel/modem   /mnt/dsp; }'

echo "== pulling split PIL images to laptop =="
mkdir -p "$WORK/nh" "$WORK/dsp"
ssh_ 'cd /mnt/nh/image  && tar cf - adsp.* cdsp.* ipa_fws.* venus.* a615_zap.* wlanmdsp.mbn' | tar xf - -C "$WORK/nh"
ssh_ 'cd /mnt/dsp/image && tar cf - modem.mdt modem.b*'                                       | tar xf - -C "$WORK/dsp"

echo "== squashing to single .mbn (with self-check) =="
OUT="$WORK/out/lib/firmware"
mkdir -p "$OUT/qcom/sm7125/a52q"
for f in $NH_IMAGES;  do python3 "$SQUASH" "$WORK/nh/$f.mdt"   "$OUT/qcom/sm7125/a52q/$f.mbn"; done
for f in $DSP_IMAGES; do python3 "$SQUASH" "$WORK/dsp/$f.mdt"  "$OUT/qcom/sm7125/a52q/$f.mbn"; done
# WiFi (WCN3990) subsystem image is already a single .mbn. The modem fetches it via tqftpserv,
# which looks next to modem.mbn (qcom/sm7125/a52q/) - without it there is no WLFW service and no wlan0.
cp "$WORK/nh/wlanmdsp.mbn" "$OUT/qcom/sm7125/a52q/wlanmdsp.mbn"

echo "== installing firmware to phone /lib/firmware =="
tar czf "$WORK/fw.tgz" -C "$WORK/out/lib/firmware" .
scp "${SSHOPT[@]}" "$WORK/fw.tgz" "$PHONE:/tmp/a52q-fw.tgz" >/dev/null
rsudo 'tar xzf /tmp/a52q-fw.tgz -C /lib/firmware && rm -f /tmp/a52q-fw.tgz'

echo "== BT NVM: qca/sm7125/a52q/apnv11.bin (decompressed generic linux-firmware-qca) =="
# The QCA BT driver loads the plain name; decompress on the laptop (phone has no
# zstd) and push it. Remove any stale .zst/empty file so the plain file wins.
scp "${SSHOPT[@]}" "$PHONE:/lib/firmware/qca/apnv11.bin.zst" "$WORK/apnv11.bin.zst" >/dev/null
zstd -q -d -f "$WORK/apnv11.bin.zst" -o "$WORK/apnv11.bin"
scp "${SSHOPT[@]}" "$WORK/apnv11.bin" "$PHONE:/tmp/apnv11.bin" >/dev/null
rsudo 'mkdir -p /lib/firmware/qca/sm7125/a52q && cp -f /tmp/apnv11.bin /lib/firmware/qca/sm7125/a52q/apnv11.bin && rm -f /lib/firmware/qca/sm7125/a52q/apnv11.bin.zst /tmp/apnv11.bin'

echo "== initramfs firmware list (builtin DRM/MSM probes before rootfs) =="
# GPU zap (device) + generic adreno blobs must be in the initramfs; overwrite the
# stale a72q entry left by the wrong-device firmware package.
rsudo 'cat > /usr/share/mkinitfs/files/30-initramfs-firmware.files <<EOF
/usr/lib/firmware/qcom/sm7125/a52q/a615_zap.mbn
/usr/lib/firmware/qcom/a630_sqe.fw.zst
/usr/lib/firmware/qcom/a630_gmu.bin.zst
EOF'
rsudo 'mkinitfs' 2>&1 | tail -3

echo "== installed files on phone =="
ssh_ 'ls -la /lib/firmware/qcom/sm7125/a52q/ /lib/firmware/qca/sm7125/a52q/'

if [ "${1:-}" = "--reboot" ]; then
    echo "== rebooting phone and waiting for it to come back =="
    rsudo 'reboot' || true
    sleep 25
    for i in $(seq 1 40); do
        if ping -c1 -W2 172.16.42.1 >/dev/null 2>&1 && ssh_ 'true' 2>/dev/null; then
            echo "phone back after ~$((25 + i*3))s"; break
        fi
        sleep 3
    done
    sleep 5
    echo "=== [1] remaining firmware load failures ==="
    ssh_ 'dmesg | grep -iE "firmware load .* failed|request_firmware failed|Direct firmware load .* failed" || echo "(none)"'
    echo "=== [2] remoteproc states ==="
    ssh_ 'for d in /sys/class/remoteproc/*; do echo "$(cat $d/name): $(cat $d/state)"; done'
    echo "=== [3] GPU / adreno ==="
    ssh_ 'dmesg | grep -iE "adreno|msm_dpu|a6[0-9]+_(sqe|gmu)|zap" | tail -15'
    echo "=== [4] WiFi / Bluetooth ==="
    ssh_ 'ip link show wlan0 2>/dev/null || echo "no wlan0"; dmesg | grep -iE "ath10k|hci0|qca|bluetooth" | tail -15'
fi
echo "== done =="
