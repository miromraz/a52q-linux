#!/bin/bash
# Overlay the device-a52q profile's /usr (and rebuilt kernel modules) onto a running
# BengalOS a52q as a systemd-sysext, so profile changes can be tested without an image
# rebuild (/usr is dm-verity). Undo: ssh a52r 'rm -rf /var/lib/extensions/a52qdev; systemd-sysext refresh'
# Usage: [EXTRA=dir] sysext-dev.sh [module.ko ...]   (modules go to lib/modules/<kver>/updates)
set -euo pipefail
PROFILE=${PROFILE:-$HOME/pixel-a4-linux/BengalOS/recipes/mkosi.conf.d/mkosi.profiles/device-a52q/mkosi.extra}
KVER=6.14.7-sm7125
H=a52r
S=$(mktemp -d); trap 'rm -rf "$S"' EXIT

mkdir -p "$S/usr/lib/extension-release.d"
cp -a "$PROFILE/usr/." "$S/usr/"
# the image keeps /etc content in /usr/share/factory/etc (symlinked from /etc)
[ -d "$PROFILE/etc" ] && mkdir -p "$S/usr/share/factory/etc" && cp -a "$PROFILE/etc/." "$S/usr/share/factory/etc/"
# EXTRA: a dir with a usr/ tree (e.g. unpacked .debs not yet in the image)
[ -n "${EXTRA:-}" ] && cp -a "$EXTRA/usr/." "$S/usr/"
echo "ID=_any" > "$S/usr/lib/extension-release.d/extension-release.a52qdev"

if [ $# -gt 0 ]; then
  M=/var/lib/a52qdev-mods
  ssh $H "rm -rf $M && mkdir -p $M/usr/lib/modules $M/lib 2>/dev/null; rmdir $M/lib; ln -s usr/lib $M/lib; \
          cp -a /usr/lib/modules/$KVER $M/usr/lib/modules/ && mkdir -p $M/usr/lib/modules/$KVER/updates"
  scp -q "$@" $H:$M/usr/lib/modules/$KVER/updates/
  ssh $H "depmod -b $M $KVER"
  mkdir -p "$S/usr/lib/modules/$KVER"
  ssh $H "cd $M/usr/lib/modules/$KVER && tar -cf - updates modules.*" | tar -C "$S/usr/lib/modules/$KVER" -xf -
fi

ssh $H 'rm -rf /var/lib/extensions/a52qdev && mkdir -p /var/lib/extensions/a52qdev'
tar -C "$S" -cf - usr | ssh $H 'tar -C /var/lib/extensions/a52qdev -xf - --no-same-owner 2>/dev/null; systemd-sysext refresh && systemctl daemon-reload && systemd-sysext status'
