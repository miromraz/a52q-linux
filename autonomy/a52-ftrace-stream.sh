#!/bin/sh
# (lean default; a52-ftrace-stream-full.sh adds SCM/RPMh/cpufreq/PSCI events and the VPH_PWR logger)
# Stream runtime-PM / clock / regulator / interconnect trace events to dev over UDP,
# so the last power transitions before a silent hard freeze are captured off-device.
T=/sys/kernel/tracing
mountpoint -q $T || mount -t tracefs nodev $T
echo 0 > $T/tracing_on; echo > $T/set_event
for e in rpm:rpm_resume rpm:rpm_suspend rpm:rpm_return_int clk:clk_enable clk:clk_disable clk:clk_prepare \
	 clk:clk_unprepare regulator:regulator_enable regulator:regulator_disable interconnect:icc_set_bw; do
	echo $e >> $T/set_event
done
for e in rpm_resume rpm_suspend rpm_return_int; do echo '!(name ~ "genpd:*:cpu*")' > $T/events/rpm/$e/filter; done
echo 4096 > $T/buffer_size_kb; echo > $T/trace; echo 1 > $T/tracing_on
exec python3 /var/tmp/udprelay.py 192.168.100.105 6668 < $T/trace_pipe
