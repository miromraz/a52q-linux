#!/bin/sh
# FULL variant of a52-ftrace-stream.sh (~300 KB/s, relay costs half a little core): install as
# /etc/a52-ftrace-stream.sh for a debugging session, not for normal running.
# Stream runtime-PM / clock / regulator / interconnect trace events to dev over UDP,
# so the last power transitions before a silent hard freeze are captured off-device.
# Since 2026-10-11 also: SCM calls (enter/return, to catch a core that never comes back from
# TrustZone), RPMh requests + completions, cpufreq changes, big-core deep-idle entry/exit, and the
# VPH_PWR supply voltage (a52-vphlog.py), to tell brown-out from firmware/bus stalls.
T=/sys/kernel/tracing
mountpoint -q $T || mount -t tracefs nodev $T
echo 0 > $T/tracing_on; echo > $T/set_event
for e in rpm:rpm_resume rpm:rpm_suspend rpm:rpm_return_int clk:clk_enable clk:clk_disable clk:clk_prepare \
	 clk:clk_unprepare regulator:regulator_enable regulator:regulator_disable interconnect:icc_set_bw \
	 qcom_scm:scm_smc_request qcom_scm:scm_smc_done rpmh:rpmh_send_msg rpmh:rpmh_tx_done \
	 power:cpu_frequency power:psci_domain_idle_enter power:psci_domain_idle_exit \
	 regulator:regulator_set_voltage regulator:regulator_set_voltage_complete clk:clk_set_rate; do
	echo $e >> $T/set_event
done
for e in rpm_resume rpm_suspend rpm_return_int; do echo '!(name ~ "genpd:*:cpu*")' > $T/events/rpm/$e/filter; done
# deep idle (PSCI) and cpufreq only for the big cores (cpu6/7): power:cpu_idle with every WFI
# made the stream 1.4 MB/s and the relay itself a 75 % CPU load
for e in psci_domain_idle_enter psci_domain_idle_exit cpu_frequency; do echo 'cpu_id >= 6' > $T/events/power/$e/filter; done
echo 4096 > $T/buffer_size_kb; echo > $T/trace; echo 1 > $T/tracing_on
python3 /etc/a52-vphlog.py &
exec python3 /var/tmp/udprelay.py 192.168.100.105 6668 < $T/trace_pipe
