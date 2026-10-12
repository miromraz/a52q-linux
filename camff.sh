#!/bin/bash
# One unattended libcamera `cam` capture trial on the A52 (silent big-core freeze hunt).
# Marker to kmsg + trace_marker, capture with a timeout, verdict OK / CAMFAIL / HANG, wait for
# recovery after a hang, one line appended to logs-1003/trials.log (tag camff-VARIANT-N) and the
# raw netconsole/ftrace slices of the trial saved to /tmp/camff/TAG.{netcon,ftrace}.
# Usage: camff.sh VARIANT N CAMID [cam args...]
# Env:  PRE / POST  shell run on the phone before / after the capture (sysfs variation + restore;
#                   a hang reboots, which restores too)
#       RUN         prefix for cam, e.g. "taskset -c 0-5" or "env LIBCAMERA_SOFTISP_MODE=cpu"
#       FRAMES      frames to capture (3)
tag=camff-$1-$2 cam=$3; shift 3
L=~/linux-a52q/logs-1003 S=/tmp/camff log=~/linux-a52q/logs-1003/trials.log
mkdir -p $S
sshp() { timeout 25 ssh -o ConnectTimeout=10 -o BatchMode=yes a52w "$@" 2>/dev/null; }
# bytes appended to a live log since offset $2; survives one rotation (LOG -> LOG.<ts>.zst)
slice() {
	if [ "$(stat -c %s "$1")" -ge "$2" ]; then tail -c +$(( $2 + 1 )) "$1"
	else z=$(ls -t "$1".*.zst | head -1)
		for _ in 1 2 3 4 5 6 7 8 9; do zstd -tq "$z" 2>/dev/null && break; sleep 10; done	# still being compressed
		nice zstd -dc "$z" | tail -c +$(( $2 + 1 )); cat "$1"; fi > "$3"
}
foff=$(stat -c %s $L/ftrace-dev.log) noff=$(stat -c %s $L/netcon-dev.log) t0=$(date +%s)
out=$(timeout 80 ssh -o ConnectTimeout=10 -o BatchMode=yes -o ServerAliveInterval=5 -o ServerAliveCountMax=4 a52w "
	mkdir -p /var/tmp/camff; cd /var/tmp/camff; up=\$(cut -d' ' -f1 /proc/uptime)
	$PRE
	echo '=== TRIAL $tag ===' > /dev/kmsg; echo 'TRIAL $tag' > /sys/kernel/tracing/trace_marker
	timeout -s INT 45 $RUN cam -c '$cam' --capture=${FRAMES:-3} $* > cam.log 2>&1; rc=\$?
	echo 'END $tag rc='\$rc > /sys/kernel/tracing/trace_marker; echo '=== END $tag ===' > /dev/kmsg
	$POST
	echo \"rc=\$rc frames=\$(grep -c 'seq: ' cam.log) up=\$up cfg=\$(grep -m1 -o 'streams: .*' cam.log)\"
	cp cam.log cam-$tag.log" 2>/dev/null)
dt=$(( $(date +%s) - t0 ))
case $out in
rc=0\ frames=[1-9]*) r="OK $tag $out ${dt}s"; sleep 3 ;;
rc=*) r="CAMFAIL $tag $out ${dt}s"; sleep 3 ;;
*)	if sshp true || { sleep 5; sshp true; }; then r="SSHFAIL $tag (phone alive, no result) ${dt}s"
	else
		until sshp true; do
			[ $(( $(date +%s) - t0 )) -gt 680 ] && { echo "$(date '+%m-%d %T') NO-RECOVERY $tag (needs human)" | tee -a $log; exit 2; }
			sleep 5
		done
		r="HANG $tag after <=${dt}s, back after $(( $(date +%s) - t0 ))s (uptime $(sshp 'cut -d" " -f1 /proc/uptime'))"
	fi ;;
esac
slice $L/ftrace-dev.log $foff $S/$tag.ftrace; slice $L/netcon-dev.log $noff $S/$tag.netcon
echo "$(date '+%m-%d %T') $r" | tee -a $log
case $r in HANG*) exit 1 ;; esac
