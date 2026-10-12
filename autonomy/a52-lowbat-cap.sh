#!/bin/sh
# Low-battery power cap (mitigation for app-launch hard freezes on a weak battery; mainline has no
# PM6150 BCL/LMh throttling). On battery and capacity < $CAP_BELOW %: big cores <= 1.7 GHz,
# little <= 1.5 GHz, GPU <= 565 MHz. Lifted when charging or above the threshold (+5 % hysteresis).
# ponytail: capacity-based, not a real VPH-droop limiter; tune CAP_BELOW/frequencies after the test.
CAP_BELOW=${CAP_BELOW:-30}
CPU=/sys/devices/system/cpu/cpufreq GPU=/sys/class/devfreq/5000000.gpu
FG=/sys/class/power_supply/sm5714-fg CHG=/sys/class/power_supply/sm5714_charger
capped=0
while :; do
	cap=$(cat $FG/capacity); online=$(cat $CHG/online)
	if [ "$online" = 0 ] && [ "$cap" -lt $(( CAP_BELOW + 5 * capped )) ]; then want=1; else want=0; fi
	if [ $want != $capped ]; then
		if [ $want = 1 ]; then
			echo 1708800 > $CPU/policy6/scaling_max_freq; echo 1516800 > $CPU/policy0/scaling_max_freq
			echo 565000000 > $GPU/max_freq; echo "lowbat-cap: ON at $cap %"
		else
			cat $CPU/policy6/cpuinfo_max_freq > $CPU/policy6/scaling_max_freq
			cat $CPU/policy0/cpuinfo_max_freq > $CPU/policy0/scaling_max_freq
			echo 750000000 > $GPU/max_freq; echo "lowbat-cap: OFF at $cap % (charger $online)"
		fi
		capped=$want
	fi
	sleep 10
done
