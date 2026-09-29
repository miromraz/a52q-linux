#!/bin/bash
# Boot-test a kernel/DTB on the a52q without losing the known-good entry: build a UKI
# on the phone from vmlinuz.efi + DTB + the stock UKI's initrd, give it a higher
# version than every other entry and a one-try boot counter (+1). If it fails to
# reach boot-complete, systemd-boot marks it bad and falls back on the next boot.
# (U-Boot exposes EFI variables read-only, so `bootctl set-oneshot` cannot be used.)
# Usage: uki-test.sh VERSION [vmlinuz.efi] [dtb]    e.g. uki-test.sh 0.26.0925.5
set -euo pipefail
VER=$1
K=${2:-$HOME/src/linux-sm7125/arch/arm64/boot/vmlinuz.efi}
D=${3:-$HOME/src/linux-sm7125/arch/arm64/boot/dts/qcom/sm7125-samsung-a52q.dtb}
H=a52r
STOCK=/boot/EFI/Linux/BengalOS_0.26.0925.2_x86-64.efi

scp -q "$K" $H:/var/tmp/vmlinuz.efi
scp -q "$D" $H:/var/tmp/a52q.dtb
ssh $H VER="$VER" STOCK="$STOCK" 'bash -s' <<'EOF'
set -euo pipefail
cd /var/tmp
# .initrd offset/size from the stock UKI's PE section table (not 4 KiB aligned)
read OFF SIZE < <(python3 - "$STOCK" <<'PY'
import struct, sys
d = open(sys.argv[1], "rb").read(4096)
pe = struct.unpack_from("<I", d, 0x3c)[0]
n = struct.unpack_from("<H", d, pe + 6)[0]
opt = struct.unpack_from("<H", d, pe + 20)[0]
for i in range(n):
    name, vs, va, rs, rp = struct.unpack_from("<8sIIII", d, pe + 24 + opt + i * 40)
    if name.rstrip(b"\0") == b".initrd":
        print(rp, vs)
PY
)
python3 - "$STOCK" "$OFF" "$SIZE" <<'PY'
import sys
f = open(sys.argv[1], "rb"); f.seek(int(sys.argv[2]))
open("initrd", "wb").write(f.read(int(sys.argv[3])))
PY
# only one test UKI fits next to the two stock ones on the 1 GiB ESP; the stock
# UKI is the fallback
rm -f /boot/EFI/Linux/a52qtest_*
sed -e "s/^IMAGE_VERSION=.*/IMAGE_VERSION=\"$VER\"/" -e "s/^VERSION_ID=.*/VERSION_ID=$VER/" \
    -e "s/^PRETTY_NAME=.*/PRETTY_NAME=\"a52q kernel test $VER\"/" /etc/os-release > osrel
tr ' ' '\n' < /proc/cmdline | grep -v '^kexectest=' | tr '\n' ' ' > cmdline
ukify build --linux=vmlinuz.efi --initrd=initrd --devicetree=a52q.dtb --cmdline=@cmdline \
    --os-release=@osrel --uname=6.14.7-sm7125 --output="/boot/EFI/Linux/a52qtest_$VER+1.efi" | tail -1
rm -f initrd
sync; ls /boot/EFI/Linux/; df -h /boot | tail -1
EOF
