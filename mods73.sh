#!/bin/bash
# Install the modules of an OBS mainline kernel .deb into the phone's a52qdev sysext,
# replacing any previous build with the same KERNELRELEASE (6.14 modules untouched).
# Usage: mods73.sh <dir where linux-image-*.deb was extracted with dpkg-deb -x>
set -euo pipefail
X=$1
KVER=$(ls "$X/lib/modules")
H=${H:-a52r}
E=/var/lib/extensions/a52qdev/usr/lib/modules
tar -C "$X/lib/modules" -cf - "$KVER" | ssh $H "rm -rf $E/$KVER && mkdir -p $E && tar -C $E -xf - --no-same-owner && \
	B=/var/lib/extensions/a52qdev; ln -sfn usr/lib \$B/lib; depmod -b \$B $KVER; rm \$B/lib;  systemd-sysext refresh --always-refresh=yes >/dev/null && ls /usr/lib/modules/$KVER/modules.dep"
