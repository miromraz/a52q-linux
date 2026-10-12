#!/bin/bash
# Rebuild the current a52qtest UKI on the phone with a different cmdline (same kernel,
# initrd, DTB). Usage: H=a52w uki-recmd.sh NEWVER 'extra args' ['args to drop regex']
# DTB=file swaps the device tree too (DTB-only test boot of the same kernel).
set -euo pipefail
H=${H:-a52w}
if [ -n "${DTB:-}" ]; then scp -q "$DTB" $H:/var/tmp/uki-new.dtb; else ssh $H rm -f /var/tmp/uki-new.dtb; fi
ssh $H VER="$1" EXTRA=$(printf %q "$2") DROP=$(printf %q "${3:-^$}") 'bash -s' <<'EOF'
set -euo pipefail
cd /var/tmp
SRC=$(ls /boot/EFI/Linux/a52qtest_*.efi | head -1)
cp "$SRC" /var/tmp/uki-src.efi
python3 - /var/tmp/uki-src.efi <<'PY'
import struct, sys
d = open(sys.argv[1], "rb").read()
pe = struct.unpack_from("<I", d, 0x3c)[0]
n = struct.unpack_from("<H", d, pe + 6)[0]
opt = struct.unpack_from("<H", d, pe + 20)[0]
for i in range(n):
    name, vs, va, rs, rp = struct.unpack_from("<8sIIII", d, pe + 24 + opt + i * 40)
    name = name.rstrip(b"\0").decode()
    if name in (".linux", ".initrd", ".dtb", ".cmdline", ".osrel", ".uname"):
        open("sec" + name, "wb").write(d[rp:rp + min(vs, rs)])
PY
tr -d '\0' < sec.cmdline | tr ' ' '\n' | grep -v '^$' | grep -vE "$DROP" > cmdline.l || true
[ -n "$EXTRA" ] && printf '%s\n' $EXTRA >> cmdline.l
[ -s cmdline.l ] || { echo "empty command line (bad drop regex?), keeping the current UKI"; exit 1; }
tr '\n' ' ' < cmdline.l > cmdline; echo "cmdline: $(cat cmdline)"
sed -e "s/^IMAGE_VERSION=.*/IMAGE_VERSION=\"$VER\"/" -e "s/^VERSION_ID=.*/VERSION_ID=$VER/" \
    -e "s/^PRETTY_NAME=.*/PRETTY_NAME=\"a52q kernel test $VER\"/" < <(tr -d '\0' < sec.osrel) > osrel
[ -f uki-new.dtb ] && mv uki-new.dtb sec.dtb
rm -f /boot/EFI/Linux/a52qtest_*
ukify build --linux=sec.linux --initrd=sec.initrd --devicetree=sec.dtb --cmdline=@cmdline \
    --os-release=@osrel --uname="$(tr -d '\0' < sec.uname)" --output="/boot/EFI/Linux/a52qtest_$VER+1.efi" | tail -1
rm -f sec.* uki-src.efi; sync; ls /boot/EFI/Linux/
EOF
