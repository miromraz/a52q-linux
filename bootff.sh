#!/bin/bash
# Reboot, then launch Firefox as soon as phosh is up; repeat. Tests the "early after boot" pattern.
# Usage: bootff.sh N
log=~/linux-a52q/logs-1003/trials.log
for i in $(seq "$1"); do
	ssh a52w 'systemctl reboot' 2>/dev/null; sleep 30
	t0=$(date +%s)
	until timeout 12 ssh -o ConnectTimeout=8 -o BatchMode=yes a52w true 2>/dev/null; do
		[ $(( $(date +%s) - t0 )) -gt 600 ] && { echo "$(date '+%m-%d %T') NO-RECOVERY ${TAG:-bootff}-$i (needs human)" | tee -a $log; exit 2; }
		sleep 5
	done
	up=$(ssh a52w 'cut -d" " -f1 /proc/uptime')
	[ -n "$BIGCAP" ] && [ $((i % 2)) = 0 ] && ssh a52w "echo $BIGCAP > /sys/devices/system/cpu/cpufreq/policy6/scaling_max_freq" && tag=cap || tag=nocap
	r=$(APP=${APP:-firefox-esr} KILLPAT=firefox-esr ~/linux-a52q/cdtrial.sh "${TAG:-bootff}-$i${BIGCAP:+-$tag}" 40)
	echo "$(date '+%m-%d %T') $r (ssh up at uptime $up)" | tee -a $log
	case $r in HANG*)
		t0=$(date +%s)
		until timeout 12 ssh -o ConnectTimeout=8 -o BatchMode=yes a52w true 2>/dev/null; do
			[ $(( $(date +%s) - t0 )) -gt 600 ] && { echo "$(date '+%m-%d %T') NO-RECOVERY ${TAG:-bootff}-$i (needs human)" | tee -a $log; exit 2; }
			sleep 5
		done
		ssh a52w "journalctl -b -1 -o short-monotonic --no-pager | grep -v 'hb .* not attached' | tail -80" > ~/linux-a52q/logs-1003/hang-${TAG:-bootff}-$i.log 2>&1 ;;
	esac
done
