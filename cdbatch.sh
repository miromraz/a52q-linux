#!/bin/bash
# Run N unattended Claude Desktop trials; after a HANG wait for the phone to come back by
# itself (watchdog/panic reboot). Aborts if it doesn't return in 10 min (needs a human).
# Usage: cdbatch.sh LABEL N SECS [STOP_AT_FIRST_HANG=0]
label=$1 n=$2 secs=$3 stop=${4:-0}
log=~/linux-a52q/logs-1003/trials.log
for i in $(seq "$n"); do
	r=$(${TRIAL:-~/linux-a52q/cdtrial.sh} "$label-$i" "$secs" $TRIALARGS); echo "$(date '+%m-%d %T') $r" | tee -a "$log"
	case $r in HANG*)
		t0=$(date +%s)
		until timeout 15 ssh -o ConnectTimeout=8 -o BatchMode=yes a52w true 2>/dev/null; do
			[ $(( $(date +%s) - t0 )) -gt 600 ] && { echo "$(date '+%m-%d %T') NO-RECOVERY $label-$i (needs human)" | tee -a "$log"; exit 2; }
			sleep 10
		done
		echo "$(date '+%m-%d %T') RECOVERED $label-$i after $(( $(date +%s) - t0 ))s, $(ssh a52w uptime)" | tee -a "$log"
		ssh a52w "journalctl -b -1 -k -o short-monotonic --no-pager | tail -60" > ~/linux-a52q/logs-1003/hang-$label-$i.log 2>&1
		[ "$stop" = 1 ] && exit 1 ;;
	esac
done
