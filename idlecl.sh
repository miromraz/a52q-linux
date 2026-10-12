#!/bin/bash
# A/B test: does the freeze need a cluster power-off (PSCI 0x41xxxx44) involving the Gold cores?
# Usage: idlecl.sh lean [cpu0s2off] [goldoff]      after a boot: lean psci-only stream (+ arm setup), push stress.sh
#        idlecl.sh trial TAG SECS SLEEP "CPUS"     one stress trial (CPUS "" = no workers), logs to trials.log
#        idlecl.sh stats TAG [TMAX]                per-CPU psci_domain_idle_enter counts of a trial
#        idlecl.sh slice TAG                       freeze evidence (per-CPU last seen, last 10 psci events)
#        idlecl.sh reboot                          reboot the phone and wait for ssh
#        idlecl.sh filt lean|clonly|quiet          psci event filter; trial sets it from MODE= (default lean)
#        idlecl.sh cnt TAG SECS                    counter deltas of a trial (genpd/cpuidle "rejected"), no stream needed
# Result 2026-10-11: the firmware refuses every 0x41xxxx44 request (returns in ~70 us); see logs-1003/idlecl-1011/.
# Streams of a trial are tail -F'ed to /tmp/idlecl/TAG.{ftrace,netcon} (survives the 1000 MB rotation).
D=~/mobile-linux/linux-a52q/logs-1003 S=/tmp/idlecl log=$D/trials.log
P() { timeout "${T:-12}" ssh -o ConnectTimeout=8 -o BatchMode=yes a52w "$@" 2>/dev/null; }
waitup() {	# wait up to 600 s for ssh
	local t0=$(date +%s)
	until P true; do [ $(( $(date +%s) - t0 )) -gt 600 ] && return 1; sleep 5; done
}
mkdir -p $S

case $1 in
filt)	# quiet = no psci events leave the phone (each event wakes the relay on a little core, which then is the last CPU down)
	# clonly = only cluster-state requests (0x41...): Gold 0x40000003 events alone are ~130 relay wake-ups/s
	case $2 in quiet) f='cpu_id > 99';; clonly) f='state > 0x40000004';; *) f='state != 0x40000004';; esac
	P "for e in psci_domain_idle_enter psci_domain_idle_exit; do echo '$f' > /sys/kernel/tracing/events/power/\$e/filter; done; cat /sys/kernel/tracing/events/power/psci_domain_idle_enter/filter" ;;
cnt)	# counter deltas of a finished trial (works without the stream): cluster requests = genpd rejected, per CPU = cpuidle rejected
	awk -v d="$3" -F'[: ]+' '/^== after/ { a = 1 } { s = a ? 1 : -1 }
		/^S[0-9]/ { gr += s * $4; gu += s * $3; gt += s * $2 }
		/cpu[67].*state1.rejected/ { g += s * $NF } /cpu0.*state2.rejected/ { c0 += s * $NF }
		/cpu[67].*state1.usage/ { u += s * $NF }
		END { printf "counters: cluster-requests=%d (%.1f/s, all rejected: genpd usage %+d, off-time %d ms) gold-cluster-requests=%d (%.1f/s) cpu0=%d gold-state1-usage=%d (%.1f/s)\n", gr, gr / d, gu, gt, g, g / d, c0, u, u / d }' $S/$2.stat ;;
reboot)
	P 'systemctl reboot'; sleep 25; waitup || { echo NO-RECOVERY; exit 2; }; P 'cut -d" " -f1 /proc/uptime' ;;
lean)
	# the stream service (re)programs tracefs ~38 s after boot: wait for its relay, and for boot to settle
	until [ "$(P 'pgrep -f udprelay.py >/dev/null && cut -d. -f1 /proc/uptime' || echo 0)" -ge "${SETTLE:-90}" ]; do sleep 5; done
	P "A2='$2' A3='$3' sh -s" <<-'EOF'
	T=/sys/kernel/tracing
	for g in rpm clk regulator interconnect rpmh qcom_scm; do echo 0 > $T/events/$g/enable; done
	echo 0 > $T/events/power/cpu_frequency/enable
	# all CPUs, minus the little cores' own CPU-only state: unfiltered = 4000 ev/s, cpu0 (relay) cycling 900x/s
	for e in psci_domain_idle_enter psci_domain_idle_exit; do echo "state != 0x40000004" > $T/events/power/$e/filter; done
	pkill -f a52-vphlog.py
	case "$A2$A3" in *cpu0s2off*) echo 1 > /sys/devices/system/cpu/cpu0/cpuidle/state2/disable;; esac
	case "$A2$A3" in *goldoff*) for c in 6 7; do echo 1 > /sys/devices/system/cpu/cpu$c/cpuidle/state1/disable; done;; esac
	mkdir -p /var/tmp/idlecl
	cat > /var/tmp/idlecl/stress.sh <<-'EOS'
	#!/bin/sh
	# stress.sh SECS TAG SLEEP "CPUS": /root/idlestress.sh with a cpu list, trace markers, safety = SECS+120
	SECS=$1; TAG=$2; SLP=$3; CPUS=$4
	systemctl stop idlecl-safety.timer 2>/dev/null
	systemd-run -q --on-active=$((SECS + 120)) --unit=idlecl-safety systemctl reboot --force --force
	m() { echo "$1" > /dev/kmsg; echo "$1" > /sys/kernel/tracing/trace_marker; }
	st() { echo "== $1"; cat /sys/kernel/debug/pm_genpd/power-domain-cluster/idle_states; grep -H . /sys/devices/system/cpu/cpu[067]/cpuidle/state[12]/usage /sys/devices/system/cpu/cpu[067]/cpuidle/state[12]/rejected; }
	st before > /var/tmp/idlecl/$TAG.stat
	m "idlecl-START $TAG"
	for c in $CPUS; do
		taskset -c $c python3 -c "import time
	while True:
	    time.sleep($SLP)" >/dev/null 2>&1 &
		pids="$pids $!"
	done
	sleep $SECS
	[ -n "$pids" ] && kill $pids
	m "idlecl-END $TAG"
	st after >> /var/tmp/idlecl/$TAG.stat
	systemctl stop idlecl-safety.timer
	EOS
	chmod +x /var/tmp/idlecl/stress.sh
	echo "uptime $(cut -d' ' -f1 /proc/uptime) events: $(cat $T/set_event | tr '\n' ' ')"
	echo "filters: $(cat $T/events/power/psci_domain_idle_enter/filter) / $(cat $T/events/power/psci_domain_idle_exit/filter)"
	echo "disable cpu0/state2=$(cat /sys/devices/system/cpu/cpu0/cpuidle/state2/disable) cpu6/state1=$(cat /sys/devices/system/cpu/cpu6/cpuidle/state1/disable) cpu7/state1=$(cat /sys/devices/system/cpu/cpu7/cpuidle/state1/disable) vphlog=$(pgrep -fc a52-vphlog.py)"
	EOF
	a=$(stat -c %s $D/ftrace-dev.log); sleep 5; b=$(stat -c %s $D/ftrace-dev.log)
	echo "stream rate $(( (b - a) / 5000 )) KB/s" ;;
trial)
	tag=$2 secs=$3 slp=$4 cpus=$5 mode=${MODE:-lean}	# MODE=quiet: no psci events streamed, counters + heartbeats only
	[ -f $S/$tag.mode ] && mode=$(cat $S/$tag.mode)
	$0 filt $mode >/dev/null
	tail -n0 -F $D/ftrace-dev.log > $S/$tag.ftrace 2>/dev/null & t1=$!
	tail -n0 -F $D/netcon-dev.log > $S/$tag.netcon 2>/dev/null & t2=$!
	sleep 1
	P "setsid nohup /var/tmp/idlecl/stress.sh $secs $tag $slp '$cpus' >/dev/null 2>&1 &" || { kill $t1 $t2; echo "start failed"; exit 1; }
	t0=$(date +%s) fail=0 r=OK
	while [ $(( $(date +%s) - t0 )) -lt $((secs + 4)) ]; do
		sleep 10
		if T=9 P true; then fail=0; else fail=$((fail + 1)); fi
		[ $fail -ge 3 ] && { r=HANG; break; }	# ssh unreachable for 30 s
	done
	if [ $r = HANG ]; then
		waitup || { kill $t1 $t2; echo "$(date '+%m-%d %T') NO-RECOVERY $tag (needs human)" | tee -a $log; exit 2; }
	else
		P "cat /var/tmp/idlecl/$tag.stat" > $S/$tag.stat; extra=" $($0 cnt $tag $secs)"
	fi
	sleep 2; kill $t1 $t2
	if [ $r = HANG ]; then
		mkdir -p $D/idlecl-1011
		$0 slice $tag > $D/idlecl-1011/$tag.txt 2>&1
		tmax=$(sed -n 's/^DEAD cpu[0-7] last ftrace event at \([0-9.]*\).*/\1/p' $D/idlecl-1011/$tag.txt)
		extra=" $(grep -m1 '^HB-DEAD' $D/idlecl-1011/$tag.txt)"
		[ $mode != quiet ] && extra="$extra $(grep -m1 '^DEAD' $D/idlecl-1011/$tag.txt)"
	fi
	[ $mode != quiet ] && st=$($0 stats $tag $tmax | head -1)
	echo "$(date '+%m-%d %T') $r $tag slp=$slp cpus=${cpus// /,} stream=$mode $st$extra" | tee -a $log
	[ $mode != quiet ] && $0 stats $tag $tmax | tail -n +2 ;;
stats)
	nice awk -v tag="$2" -v tmax="$3" '
	{ if (!match($0, /\[00[0-7]\] +[^ ]+ +[0-9]+\.[0-9]+: /)) next
	  s = substr($0, RSTART, RLENGTH); c = substr(s, 4, 1) + 0; sub(/^.*\] +[^ ]+ +/, "", s); t = s + 0
	  if (index($0, "idlecl-START " tag)) { on = 1; t0 = t; mx = t; next }
	  if (!on) next
	  if (t < mx - 5) exit				# clock restarted = next boot
	  if (tmax && t > tmax) next
	  if (t > mx) mx = t
	  if (index($0, "idlecl-END " tag)) { tend = t; exit }
	  if (match($0, /psci_domain_idle_enter: cpu_id=[0-7] state=0x[0-9a-f]+/)) {
		st = substr($0, RSTART + RLENGTH - 10, 10)
		if (st ~ /^0x41/) cl[c]++; else cp[c]++
		by[c " " st]++; ent[c] = t
	  } else if ($0 ~ /psci_domain_idle_exit/ && ent[c]) {
		d = t - ent[c]; ent[c] = 0; nx[c]++; res[c] += d
		if (d < 0.0003) sh[c]++			# came straight back: aborted / pending irq
	  } }
	END { dur = (tend ? tend : mx) - t0; if (dur <= 0) { print "no data"; exit }
	  g = cl[6] + cl[7]; for (c = 0; c < 8; c++) a += cl[c]
	  printf "dur=%.1fs goldcl=%d (%.2f/s; cpu6 %d cpu7 %d) allcl=%d (%.2f/s) gold003=%d (%.1f/s)\n", dur, g, g / dur, cl[6], cl[7], a, a / dur, cp[6] + cp[7], (cp[6] + cp[7]) / dur
	  for (c = 0; c < 8; c++) { printf "  cpu%d cluster=%d (%.2f/s) cpu-only=%d (%.1f/s) exits=%d short<0.3ms=%d meanres=%.2fms |", c, cl[c], cl[c] / dur, cp[c], cp[c] / dur, nx[c], sh[c], nx[c] ? 1000 * res[c] / nx[c] : 0
		for (k in by) { split(k, q, " "); if (q[1] == c) printf " %s:%d", q[2], by[k] } print "" } }' $S/$2.ftrace ;;
slice)
	tag=$2
	echo "## $tag"
	echo "# netconsole: last cpuhbN (kernel time), non-heartbeat kernel lines of the trial"
	nice awk -v tag="$tag" '
	{ if (!match($0, /\[ *[0-9]+\.[0-9]+\]/)) next
	  t = substr($0, RSTART + 1, RLENGTH - 2) + 0
	  if (index($0, "idlecl-START " tag)) { on = 1; mx = t; t0 = t; print "start marker at " t; next }
	  if (!on) next
	  if (t < mx - 5) exit
	  if (t > mx) mx = t
	  if (match($0, /cpuhb[0-7]/)) hb[substr($0, RSTART + 5, 1)] = t; else other[++n] = $0 }
	END { for (c = 0; c < 8; c++) printf "cpuhb%d %s  ", c, hb[c]; print ""
	      d = 0; for (c = 1; c < 8; c++) if (hb[c] < hb[d]) d = c
	      printf "HB-DEAD cpu%d last heartbeat at %.2f = +%.0fs after start, %.0fs before the last netconsole line\n", d, hb[d], hb[d] - t0, mx - hb[d]
	      print "last netconsole line at " mx "; non-heartbeat lines after the marker: " n + 0
	      for (i = (n > 8 ? n - 7 : 1); i <= n; i++) print "  " substr(other[i], 1, 200) }' $S/$tag.netcon
	# pass 1: per-CPU last ftrace timestamp -> dead CPU = the one silent first
	set -- $(nice awk -v tag="$tag" '
	{ if (!match($0, /\[00[0-7]\] +[^ ]+ +[0-9]+\.[0-9]+: /)) next
	  s = substr($0, RSTART, RLENGTH); c = substr(s, 4, 1) + 0; sub(/^.*\] +[^ ]+ +/, "", s); t = s + 0
	  if (index($0, "idlecl-START " tag)) { on = 1; t0 = t; mx = t }
	  if (!on) next
	  if (t < mx - 5) exit
	  if (t > mx) mx = t
	  last[c] = t }
	END { d = 0; for (c = 1; c < 8; c++) if (last[c] < last[d]) d = c
	      printf "%d %.6f %.6f %.6f", d, last[d], t0, mx; for (c = 0; c < 8; c++) printf " %.6f", last[c] }' $S/$tag.ftrace)
	dead=$1 td=$2 t0=$3 mx=$4; shift 4
	echo "# ftrace: start marker $t0, last line of this boot $mx; per-CPU last event:"
	c=0; for l; do printf 'cpu%d %s  ' $c $l; c=$((c + 1)); done; echo
	echo "DEAD cpu$dead last ftrace event at $td = +$(echo "$td - $t0" | bc)s after start, $(echo "$mx - $td" | bc)s before the stream stopped"
	nice awk -v tag="$tag" -v td="$td" -v dead="$dead" '
	{ if (!match($0, /\[00[0-7]\] +[^ ]+ +[0-9]+\.[0-9]+: /)) next
	  s = substr($0, RSTART, RLENGTH); c = substr(s, 4, 1) + 0; sub(/^.*\] +[^ ]+ +/, "", s); t = s + 0
	  if (index($0, "idlecl-START " tag)) { on = 1; mx = t }
	  if (!on) next
	  if (t < mx - 5) exit
	  if (t > mx) mx = t
	  if ($0 !~ /psci_domain_idle/) next
	  if (t <= td) {
		n[c]++; L[c, n[c] % 10] = $0
		open[c] = ($0 ~ /idle_enter/) ? $0 : ""
		if ($0 ~ /idle_enter.*state=0x41/) { lastcl = $0; clc = c; clback = "" }
		else if (c == clc && lastcl != "" && clback == "") clback = $0
	  } else {
		if (c == clc && lastcl != "" && clback == "") clback = $0
		if (++after[c] <= 3) A[c, after[c]] = $0
		if (t > td + 1 && done++ == 0) nextfile
	  } }
	END { print "# state of every CPU at the moment cpu" dead " went silent (" td "):"
	  for (c = 0; c < 8; c++) print "cpu" c ": " (open[c] != "" ? "INSIDE psci (enter without exit): " substr(open[c], index(open[c], "] ") + 2) : "awake / WFI (last psci event was an exit, or none)")
	  print "# last cluster-state (0x41...) entry on any CPU before that moment, and the next event of that CPU:"
	  print "  " lastcl; print "  -> " (clback != "" ? clback : "NOTHING (never came back)")
	  for (c = 0; c < 8; c++) { print "# cpu" c " last 10 psci events up to " td ":"
		for (i = n[c] - 9; i <= n[c]; i++) if (i > 0) print "  " L[c, i % 10]
		print "# cpu" c " first events after:"; for (i = 1; i <= 3; i++) if ((c, i) in A) print "  " A[c, i] } }' $S/$tag.ftrace
	echo "# raw stream, 0.15 s before to 0.05 s after:"
	nice awk -v tag="$tag" -v td="$td" '
	{ if (!match($0, /\[00[0-7]\] +[^ ]+ +[0-9]+\.[0-9]+: /)) next
	  s = substr($0, RSTART, RLENGTH); sub(/^.*\] +[^ ]+ +/, "", s); t = s + 0
	  if (index($0, "idlecl-START " tag)) on = 1
	  if (on && t >= td - 0.15 && t <= td + 0.05) print
	  if (on && t > td + 1) exit }' $S/$tag.ftrace ;;
esac
