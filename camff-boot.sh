#!/bin/bash
# fresh-boot loop: reboot, capture as soon as ssh + trace stream are up. Usage: camff-boot.sh VARIANT FIRST LAST CAMID
v=$1 a=$2 b=$3 cam=$4
for i in $(seq $a $b); do
	ssh -o ConnectTimeout=10 a52w 'systemctl reboot' 2>/dev/null; sleep 30; t0=$(date +%s)
	until timeout 12 ssh -o ConnectTimeout=8 -o BatchMode=yes a52w 'pgrep -f udprelay >/dev/null && pgrep -u miro -x phosh >/dev/null' 2>/dev/null; do
		[ $(( $(date +%s) - t0 )) -gt 600 ] && { echo "NO-RECOVERY before $v-$i"; exit 2; }; sleep 3
	done
	~/linux-a52q/camff.sh $v $i $cam
done
