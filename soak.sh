#!/bin/bash
# Unattended freeze soak with the flight recorder armed: per cycle reboot, Firefox as soon as the
# session is up (bootff.sh), then a main-camera capture (camff.sh) around 2 min of uptime.
# Freezes are logged by the two harnesses in logs-1003/trials.log; the dead core's last events
# arrive by themselves in logs-1003/blackbox-dev.log. Usage: [NOCAM=1] [NAME=tag] soak.sh CYCLES
cd ~/linux-a52q || exit 1
for n in $(seq "$1"); do
	TAG=${NAME:-soak}ff-$n ./bootff.sh 1 || exit 2	# 2 = phone did not come back, needs a human
	[ -n "$NOCAM" ] || ./camff.sh "${NAME:-soak}" "$n" /base/soc@0/cci@ac4a000/i2c-bus@0/camera@2d
done
