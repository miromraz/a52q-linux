#!/bin/bash
# Firefox launches, uncapped, until the battery reaches 3 %. Log: logs-1003/lowbat-plan.log
L=~/linux-a52q/logs-1003/lowbat-plan.log; i=0
cap() { timeout 20 ssh -o ConnectTimeout=10 a52w cat /sys/class/power_supply/sm5714-fg/capacity 2>/dev/null; }
while c=$(cap); [ -z "$c" ] || [ "$c" -gt 3 ]; do
	i=$((i+1)); echo "$(date '+%m-%d %T') empty-$i at $c %" >> $L
	APP=firefox-esr KILLPAT=firefox-esr ~/linux-a52q/cdbatch.sh empty$c-$i 1 40 >> $L 2>&1
done
echo "$(date '+%m-%d %T') empty done at $c %" >> $L
