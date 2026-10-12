#!/bin/bash
# Like cdtrial.sh but launches rendstress.py in miro's session. Usage: rendtrial.sh LABEL SECS RENDERER
label=$1 secs=$2 rend=$3
until ssh -o ConnectTimeout=5 a52w 'pgrep -u miro -x phosh' >/dev/null 2>&1; do sleep 5; done
sleep 10
ssh a52w "echo '=== REND $label ===' > /dev/kmsg; systemd-run -M miro@ --user --unit=rend-\$RANDOM --setenv=GSK_RENDERER=$rend python3 /var/tmp/rendstress.py $secs" >/dev/null 2>&1
t0=$(date +%s); last=
while [ $(( $(date +%s) - t0 )) -lt "$secs" ]; do
	sleep 15
	r=$(timeout 25 ssh -o ConnectTimeout=20 a52w 'cut -d" " -f1 /proc/uptime' 2>/dev/null)
	[ -z "$r" ] && r=$(timeout 25 ssh -o ConnectTimeout=20 a52w 'cut -d" " -f1 /proc/uptime' 2>/dev/null)
	[ -z "$r" ] && { echo "HANG $label after $(( $(date +%s) - t0 ))s (last uptime $last)"; exit 1; }
	last=$r
done
echo "OK $label ${secs}s $(ssh a52w "journalctl -M miro@ --user -o cat --no-pager -n 200 | grep -a '^frames' | tail -1" 2>/dev/null)"
