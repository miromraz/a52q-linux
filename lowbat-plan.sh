#!/bin/bash
# Unattended low-battery freeze test. Waits for the charger to be unplugged, drains to $LOW %
# with on-screen GPU rendering, then runs Firefox launch batches: uncapped, then with
# a52-lowbat-cap.service. Log: ~/linux-a52q/logs-1003/lowbat-plan.log
LOW=${LOW:-20}; L=~/linux-a52q/logs-1003/lowbat-plan.log
say() { echo "$(date '+%m-%d %T') $*" | tee -a "$L"; }
bat() { timeout 20 ssh -o ConnectTimeout=10 -o BatchMode=yes a52w 'echo $(cat /sys/class/power_supply/sm5714_charger/online) $(cat /sys/class/power_supply/sm5714-fg/capacity) $(cat /sys/class/power_supply/sm5714-fg/voltage_now)' 2>/dev/null; }
say "plan start, waiting for unplug"
until read on cap mv < <(bat) && [ "$on" = 0 ]; do sleep 120; done
say "unplugged at $cap % ($mv uV); draining to $LOW %"
while read on cap mv < <(bat); [ -z "$cap" ] || [ "$cap" -gt "$LOW" ]; do
	[ "$on" = 1 ] && { say "charger re-plugged at $cap %, waiting"; sleep 300; continue; }
	ssh a52w 'systemctl --user -M miro@ is-active rend-drain >/dev/null 2>&1 || systemd-run -M miro@ --user --unit=rend-drain --setenv=GSK_RENDERER=gl python3 /var/tmp/rendstress.py 600' >/dev/null 2>&1
	say "draining: $cap % $mv uV"; sleep 300
done
ssh a52w 'systemctl --user -M miro@ stop rend-drain' >/dev/null 2>&1
say "at $cap % ($mv uV): benchmark"; ~/linux-a52q/bench.sh low$cap | tee -a "$L"
read on cap mv < <(bat); say "at $cap % ($mv uV): uncapped Firefox batch"
APP=firefox-esr KILLPAT=firefox-esr ~/linux-a52q/cdbatch.sh lowbat-nocap 20 40 | tee -a "$L"
read on cap mv < <(bat); say "after uncapped batch: charger $on, $cap %, $mv uV; enabling cap"
ssh a52w 'systemctl enable --now a52-lowbat-cap; sleep 12; journalctl -u a52-lowbat-cap -n 2 -o cat --no-pager' | tee -a "$L"
APP=firefox-esr KILLPAT=firefox-esr ~/linux-a52q/cdbatch.sh lowbat-cap 20 40 | tee -a "$L"
read on cap mv < <(bat); say "done: charger $on, $cap %, $mv uV"
