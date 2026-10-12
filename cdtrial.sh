#!/bin/bash
# One unattended Claude Desktop trial on the A52 (autologin session). Waits for phosh,
# launches the app with optional extra env/prefix, watches up to $2 s for a hang.
# Prints OK or HANG <uptime-at-last-contact>. Usage: cdtrial.sh LABEL SECS [PREFIX...]
label=$1 secs=$2; shift 2
until ssh -o ConnectTimeout=5 a52w 'pgrep -u miro -x phosh' >/dev/null 2>&1; do sleep 5; done
sleep 10
ssh a52w "echo '=== TRIAL $label ===' > /dev/kmsg; echo 'TRIAL $label' > /sys/kernel/tracing/trace_marker 2>/dev/null; systemd-run -M miro@ --user --unit=cdtrial-\$RANDOM --setenv=CLAUDE_USE_WAYLAND=1 --setenv=CLAUDE_DISABLE_GPU=1 $* ${APP:-/home/miro/.local/opt/claude-desktop/AppRun --ozone-platform=wayland --enable-features=WaylandWindowDecorations}" >/dev/null 2>&1
t0=$(date +%s); last=
while [ $(( $(date +%s) - t0 )) -lt "$secs" ]; do
	sleep 15
	r=$(timeout 25 ssh -o ConnectTimeout=20 a52w 'cut -d" " -f1 /proc/uptime' 2>/dev/null)
	if [ -z "$r" ]; then
		r=$(timeout 25 ssh -o ConnectTimeout=20 a52w 'cut -d" " -f1 /proc/uptime' 2>/dev/null)
		[ -z "$r" ] && { echo "HANG $label after $(( $(date +%s) - t0 ))s (last uptime $last)"; exit 1; }
	fi
	last=$r
done
ssh a52w "pkill -u miro -f '${KILLPAT:-claude-desktop}'" 2>/dev/null
echo "OK $label ${secs}s"
