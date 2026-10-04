#!/bin/bash
# On-device acceptance run for the a52q mainline (7.3) kernel. Read-only checks plus
# N reboots (modem DOG stall regression). Needs the phone on USB (ssh a52r).
# Usage: flock /tmp/claude-1000/a52phone.lock ~/linux-a52q/accept73.sh [reboots] > log
set -u
N=${1:-8}
H=a52r
s() { timeout "${T:-60}" ssh -o ConnectTimeout=6 $H "$@" 2>&1; }

wait_boot() {
	local t0=$(date +%s)
	local kicked=0
	until up=$(s 'cut -d. -f1 /proc/uptime') && [ "$up" -lt 400 ] 2>/dev/null; do
		sleep 8; [ $(( $(date +%s) - t0 )) -gt 900 ] && { echo "NO RETURN"; return 1; }
		# phone still up on the old boot after 2 min: the reboot request was lost, resend it
		if [ "${up:-0}" -ge 400 ] 2>/dev/null && [ $kicked -eq 0 ] && [ $(( $(date +%s) - t0 )) -gt 120 ]; then
			echo "  reboot request lost (up=$up), resending"; s 'systemd-run --on-active=2 systemctl reboot' >/dev/null; kicked=1
		fi
	done
	s 'touch /run/keep73' >/dev/null
	T=300 s 'for i in $(seq 100); do case $(systemctl is-system-running) in starting|initializing) sleep 3;; *) break;; esac; done'
}

checks() {
	T=240 s '
	echo "kernel $(uname -r) state $(systemctl is-system-running) failed: $(systemctl --failed --no-legend | awk "{print \$2}" | tr "\n" " ")"
	echo "modem_crash $(dmesg | grep -c "crash detected in modem") wld0 $(ip -br l show wld0 2>/dev/null | grep -c UP) bt $(ls /sys/class/bluetooth | wc -l) nfc $(ls /sys/class/nfc | wc -l)"
	echo "input $(grep Name= /proc/bus/input/devices | cut -d\" -f2 | tr "\n" ,)"
	echo "deferred $(cat /sys/kernel/debug/devices_deferred | wc -l) warns $(dmesg | grep -c "cut here")"
	echo "registry $(ls /var/lib/droid-juicer/sensors/sensors/registry 2>/dev/null | wc -l) hexagonrpcd $(systemctl is-active hexagonrpcd) proxy $(systemctl is-active iio-sensor-proxy)"
	timeout 6 monitor-sensor --accel 2>&1 | grep -m1 -iE "accel|orientation|Waiting"
	cd /var/tmp; n=$(cam -l 2>/dev/null | grep -c "^[0-9]*:"); echo "cameras $n"
	for c in $(seq 1 $n); do rm -f acc-*; timeout 30 cam -c$c --capture=2 --file=acc-#.bin >/dev/null 2>&1
		echo "  cam$c frames $(ls acc-* 2>/dev/null | wc -l)"; rm -f acc-*; done
	'
}

echo "== $(date +%T) initial"; checks
for i in $(seq 1 "$N"); do
	s 'systemd-run --on-active=2 systemctl reboot' >/dev/null
	sleep 30
	wait_boot || exit 1
	sleep 60
	echo "== $(date +%T) boot $i: $(T=30 s 'echo crash=$(dmesg | grep -c "crash detected in modem") wld0=$(ip -br l show wld0 2>/dev/null | grep -c UP) up=$(cut -d. -f1 /proc/uptime)')"
done
echo "== $(date +%T) final"; checks
