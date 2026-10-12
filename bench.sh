#!/bin/bash
# SoC benchmark + power stress on the A52: CPU (stress-ng), GPU (glmark2), then both at once.
# Samples battery V/I, CPU/GPU clocks and max temp every 2 s. Usage: bench.sh LABEL
# Results: ~/linux-a52q/logs-1003/bench-LABEL.{txt,csv}
label=$1; out=~/linux-a52q/logs-1003/bench-$label
ssh -o ServerAliveInterval=10 -o ServerAliveCountMax=3 a52w 'bash -s' "$label" > $out.txt 2>&1 <<'EOF' || echo "BENCH $label: ssh lost rc=$? at $(date +%T) (hang?)" | tee -a $out.txt
cd /var/tmp/bench; export LD_LIBRARY_PATH=/var/tmp/bench/lib
S=/var/tmp/bench/sample.csv; P=/sys/class/power_supply
echo "t,phase,cap,uV,uA,f0,f6,gpu,tempmax" > $S
phase=idle
sample() { while :; do
	t=$(cut -d" " -f1 /proc/uptime); tm=$(cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null | sort -n | tail -1)
	echo "$t,$(cat /var/tmp/bench/phase),$(cat $P/sm5714-fg/capacity),$(cat $P/sm5714-fg/voltage_now),$(cat $P/sm5714-fg/current_now),$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq),$(cat /sys/devices/system/cpu/cpufreq/policy6/scaling_cur_freq),$(cat /sys/class/devfreq/*gpu*/cur_freq 2>/dev/null | head -1),$tm" >> $S
	sleep 2; done; }
ph() { echo $1 > /var/tmp/bench/phase; echo "=== $1 $(date +%T) cap=$(cat $P/sm5714-fg/capacity)% $(cat $P/sm5714-fg/voltage_now)uV charger=$(cat $P/sm5714_charger/online)"; echo "BENCH $1" > /dev/kmsg; }
gl() { systemd-run -M miro@ --user --wait --pipe -q /var/tmp/bench/usr/bin/glmark2-es2-wayland --data-path /var/tmp/bench/usr/share/glmark2 -s 1080x2400 "$@" 2>&1 | grep -E "Score|FPS" | tail -${N:-40}; }
ph idle; sample & SP=$!; sleep 20
ph cpu1; usr/bin/stress-ng --cpu 1 --cpu-method matrixprod -t 30 --metrics-brief 2>&1 | grep -E "cpu "
ph cpu8; usr/bin/stress-ng --cpu 8 --cpu-method matrixprod -t 60 --metrics-brief 2>&1 | grep -E "cpu "
ph cool; sleep 30
ph gpu; gl
ph cool; sleep 30
ph all; usr/bin/stress-ng --cpu 8 --cpu-method matrixprod -t 90 --metrics-brief > /var/tmp/bench/all-cpu.txt 2>&1 & N=1 gl --run-forever 2>/dev/null & sleep 90; pkill -u miro -x glmark2-es2-way; wait %2; grep -E "cpu " /var/tmp/bench/all-cpu.txt
ph done; sleep 4; kill $SP
EOF
scp -q a52w:/var/tmp/bench/sample.csv $out.csv
grep -E "===|cpu |Score" $out.txt
awk -F, 'NR>1{n[$2]++; i[$2]+=$5; if($4<v[$2]||!v[$2])v[$2]=$4; if($9>T[$2])T[$2]=$9} END{for(p in n) printf "%s: avg %d mA, min %.3f V, max temp %.1f C\n", p, -i[p]/n[p]/1000, v[p]/1e6, T[p]/1000}' $out.csv
