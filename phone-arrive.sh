#!/bin/bash
# When the a52q appears on USB: install the latest successful OBS mainline build (if newer than
# what was installed last), boot it, then run the acceptance suite. Everything persistent lives
# under ~/linux-a52q (tmpfs /tmp is wiped on laptop reboots).
set -u
A=~/linux-a52q
K=$A/k73                      # extracted kernel .deb
log=$A/accept-$(date +%m%d-%H%M).log
exec > >(tee -a "$log") 2>&1

until grep -qsl 02:a5:2c:00:00:01 /sys/class/net/*/address || sudo ip -n a52 link 2>/dev/null | grep -q 02:a5:2c:00:00:01; do sleep 20; done
echo "== $(date +%T) phone seen"; sleep 60

st=$(osc results home:realni linux-sm7125-mainline 2>/dev/null | awk '{print $NF}')
sha=$(osc log home:realni linux-sm7125-mainline 2>/dev/null | sed -n 4p | grep -o '[0-9a-f]\{40\}')
echo "OBS: $st $sha (installed: $(cat $K/.sha 2>/dev/null))"
if [ "$st" = succeeded ] && [ "$sha" != "$(cat $K/.sha 2>/dev/null)" ]; then
	rm -rf $K && mkdir -p $K && cd $K || exit 1
	osc getbinaries home:realni linux-sm7125-mainline Debian_13 aarch64 >/dev/null 2>&1
	mkdir x && dpkg-deb -x binaries/linux-image-7.3.0-rc5-sm7125_*_arm64.deb x && rm -rf binaries
	X=$K/x
	$A/mods73.sh $X | tail -1
	ver=0.26.$(date +%m%d.%H%M | sed 's/^0//')
	$A/uki-test.sh $ver $X/boot/vmlinuz-7.3.0-rc5-sm7125 \
		$X/usr/lib/linux-image-7.3.0-rc5-sm7125/qcom/sm7125-samsung-a52q.dtb 7.3.0-rc5-sm7125 | tail -2 \
		&& echo "$sha" > $K/.sha
fi
$A/accept73.sh 8
echo "== $(date +%T) done, log $log"
