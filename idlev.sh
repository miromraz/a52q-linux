#!/bin/bash
# Idle-state DTB variants (baseline / V1 all-level-4 / V2 no-cluster): counters + stress trials. Sibling of idlecl.sh.
# Usage: idlev.sh prep                      push snap.sh/stress.sh to /var/tmp/idlev on the phone
#        idlev.sh stream quiet|lean|leancl  runtime tracefs setup (quiet: nothing streamed; lean: psci cpu6/7 + scm;
#                                           leancl: lean + cluster requests of any CPU)
#        idlev.sh meas TAG SECS             quiet-idle counter delta over SECS (snapshots -> idlev-1011/TAG.snap)
#        idlev.sh trial TAG SECS SLP        idle stress on cpu6+7, counters sampled every 15 s to idlev-1011/TAG.snap
#        idlev.sh delta FILE [SECS]         counter deltas between first and last snapshot of FILE
#        idlev.sh slice TAG                 freeze evidence from /tmp/idlev/TAG.{netcon,ftrace}
#        idlev.sh reboot                    reboot, wait for ssh, wait for uptime 90 s
D=~/mobile-linux/linux-a52q/logs-1003 S=/tmp/idlev E=$D/idlev-1011 log=$D/trials.log
P() { timeout "${T:-12}" ssh -o ConnectTimeout=8 -o BatchMode=yes a52w "$@" 2>/dev/null; }
waitup() { local t0=$(date +%s); until P true; do [ $(( $(date +%s) - t0 )) -gt 600 ] && return 1; sleep 5; done; }
mkdir -p $S $E

case $1 in
prep)
	P 'mkdir -p /var/tmp/idlev; cat > /var/tmp/idlev/snap.sh; chmod +x /var/tmp/idlev/snap.sh' <<-'EOF'
	#!/bin/sh
	echo "== $1 up=$(cut -d' ' -f1 /proc/uptime)"
	cd /sys/devices/system/cpu; grep -H . cpu[0-7]/cpuidle/state[0-9]/usage cpu[0-7]/cpuidle/state[0-9]/rejected cpu[0-7]/cpuidle/state[0-9]/time
	for d in cluster cpu0 cpu1 cpu2 cpu3 cpu4 cpu5 cpu6 cpu7; do sed "1d;s/^/pd-$d /" /sys/kernel/debug/pm_genpd/power-domain-$d/idle_states; done
	EOF
	P 'cat > /var/tmp/idlev/stress.sh; chmod +x /var/tmp/idlev/stress.sh' <<-'EOF'
	#!/bin/sh
	# copy of /root/idlestress.sh: stress.sh SECS TAG SLEEP; workers on cpu6+7, markers, safety reboot = SECS+120
	SECS=$1; TAG=$2; SLP=$3
	systemctl stop idlev-safety.timer 2>/dev/null
	systemd-run -q --on-active=$((SECS + 120)) --unit=idlev-safety systemctl reboot --force --force
	m() { echo "$1" > /dev/kmsg; echo "$1" > /sys/kernel/tracing/trace_marker; }
	/var/tmp/idlev/snap.sh before > /var/tmp/idlev/$TAG.stat
	m "idlev-START $TAG"
	for c in 6 7; do
		taskset -c $c python3 -c "import time
	while True:
	    time.sleep($SLP)" >/dev/null 2>&1 &
		pids="$pids $!"
	done
	sleep $SECS
	kill $pids
	m "idlev-END $TAG"
	/var/tmp/idlev/snap.sh after >> /var/tmp/idlev/$TAG.stat
	systemctl stop idlev-safety.timer
	EOF
	P 'ls -la /var/tmp/idlev' ;;
stream)
	case $2 in quiet) f='cpu_id > 99' scm=0;; leancl) f='cpu_id >= 6 || state > 0x40000004' scm=1;; *) f='cpu_id >= 6' scm=1;; esac
	P "F='$f' SCM=$scm sh -s" <<-'EOF'
	T=/sys/kernel/tracing
	for g in rpm clk regulator interconnect rpmh; do echo 0 > $T/events/$g/enable; done
	echo 0 > $T/events/power/cpu_frequency/enable
	echo $SCM > $T/events/qcom_scm/enable
	for e in psci_domain_idle_enter psci_domain_idle_exit; do echo "$F" > $T/events/power/$e/filter; echo 1 > $T/events/power/$e/enable; done
	pkill -f a52-vphlog.py
	echo "up $(cut -d' ' -f1 /proc/uptime) events: $(cat $T/set_event | tr '\n' ' ') filter: $(cat $T/events/power/psci_domain_idle_enter/filter) vphlog=$(pgrep -fc a52-vphlog.py)"
	EOF
	a=$(stat -c %s $D/ftrace-dev.log); sleep 5; b=$(stat -c %s $D/ftrace-dev.log); echo "stream rate $(( (b - a) / 5 )) B/s" ;;
meas)
	T=$(( $3 + 30 )) P "/var/tmp/idlev/snap.sh before; sleep $3; /var/tmp/idlev/snap.sh after" > $E/$2.snap
	$0 delta $E/$2.snap ;;
delta)
	python3 - "$2" <<-'EOF'
	import re, sys
	snaps = []
	for l in open(sys.argv[1]):
	    l = l.strip()
	    if l.startswith('== '):
	        snaps.append({'up': float(l.split('up=')[1])}); continue
	    if not snaps: continue
	    m = re.match(r'cpu(\d)/cpuidle/state(\d)/(\w+):(\d+)', l)
	    if m: snaps[-1][('c', int(m[1]), int(m[2]), m[3])] = int(m[4]); continue
	    f = l.split()
	    if len(f) >= 5 and f[0].startswith('pd-'):
	        s64 = lambda v: v - (1 << 64) if v >= 1 << 63 else v	# usage goes "negative" (pm_genpd_inc_rejected bug)
	        snaps[-1][('p', f[0][3:], f[1])] = (int(f[2]), s64(int(f[3])), int(f[4]))
	if len(snaps) < 2: sys.exit('fewer than 2 complete snapshots')
	a, b = snaps[0], snaps[-1]
	if len(b) < len(a): b = snaps[-2]	# last sample cut by the freeze
	d = b['up'] - a['up']
	print(f'interval {d:.1f}s (uptime {a["up"]:.0f}..{b["up"]:.0f}), {len(snaps)} snapshots')
	tot = rej = 0
	for c in range(8):
	    o = []
	    for s in range(4):
	        if ('c', c, s, 'usage') not in a: continue
	        u, r, t = (b[('c', c, s, k)] - a[('c', c, s, k)] for k in ('usage', 'rejected', 'time'))
	        if s: tot += u + r; rej += r
	        o.append(f's{s} {u / d:7.1f}/s rej {r:6d} time {100 * t / d / 1e6:5.1f}%')
	    print(f'cpu{c}: ' + ' | '.join(o))
	print(f'PSCI calls (states>=1, usage+rejected): {tot} = {tot / d:.1f}/s, of which rejected {rej} = {rej / d:.1f}/s')
	cu = cr = 0
	for k in sorted(k for k in a if k[0] == 'p'):
	    t, u, r = (b[k][i] - a[k][i] for i in range(3))
	    if k[1] == 'cluster':
	        cu += u; cr += r; print(f'pd-cluster {k[2]}: usage {u:+d} rejected {r:+d} time {t} ms')
	print(f'cluster domain: accepted {cu} ({cu / d:.1f}/s) rejected {cr} ({cr / d:.1f}/s) requests {(cu + cr) / d:.1f}/s')
	print('cpu pd usage/s: ' + ' '.join(f'{k[1]}/{k[2]}={(b[k][1] - a[k][1]) / d:.1f}' for k in sorted(k for k in a if k[0] == 'p' and k[1] != 'cluster')))
	EOF
	;;
reboot)
	P 'systemctl reboot'; sleep 25; waitup || { echo NO-RECOVERY; exit 2; }
	until [ "$(P 'pgrep -f udprelay.py >/dev/null && cut -d. -f1 /proc/uptime' || echo 0)" -ge 90 ]; do sleep 5; done
	P 'uname -r; ls /boot/EFI/Linux/; cut -d" " -f1 /proc/uptime' ;;
trial)
	tag=$2 secs=$3 slp=$4
	tail -n0 -F $D/ftrace-dev.log > $S/$tag.ftrace 2>/dev/null & t1=$!
	tail -n0 -F $D/netcon-dev.log > $S/$tag.netcon 2>/dev/null & t2=$!
	sleep 1
	P "setsid nohup /var/tmp/idlev/stress.sh $secs $tag $slp >/dev/null 2>&1 &" || { kill $t1 $t2; echo "start failed"; exit 1; }
	timeout $((secs + 20)) ssh -o ConnectTimeout=8 -o BatchMode=yes a52w 'while :; do /var/tmp/idlev/snap.sh s; sleep 15; done' > $E/$tag.snap 2>/dev/null & t3=$!
	t0=$(date +%s) fail=0 r=OK
	while [ $(( $(date +%s) - t0 )) -lt $((secs + 4)) ]; do
		sleep 10
		if T=9 P true; then fail=0; else fail=$((fail + 1)); fi
		[ $fail -ge 3 ] && { r=HANG; break; }	# ssh unreachable for 30 s
	done
	kill $t3 2>/dev/null
	if [ $r = HANG ]; then
		waitup || { kill $t1 $t2; echo "$(date '+%m-%d %T') NO-RECOVERY $tag (needs human)" | tee -a $log; exit 2; }
		sleep 2; kill $t1 $t2
		$0 slice $tag > $E/$tag.txt 2>&1
		{ echo "# counters up to the last 15 s sample before the freeze:"; $0 delta $E/$tag.snap; } >> $E/$tag.txt 2>&1
		extra="$(grep -m1 '^HB-DEAD' $E/$tag.txt) | $(grep -m1 '^DEAD' $E/$tag.txt) | back on $(P 'uname -r; ls /boot/EFI/Linux/ | grep a52qtest' | tr '\n' ' ')"
	else
		sleep 2; kill $t1 $t2
		P "cat /var/tmp/idlev/$tag.stat" > $E/$tag.stat
		$0 delta $E/$tag.stat > $E/$tag.delta
		extra=$(python3 - $E/$tag.delta <<-'EOF'
		import re, sys
		t = open(sys.argv[1]).read()
		g = [l for l in t.splitlines() if l.startswith(('cpu6', 'cpu7'))]
		deep = sum(float(re.findall(r's\d +([\d.]+)/s', l)[-1]) for l in g)
		print(f'gold-deep={deep:.1f}/s | ' + ' | '.join(l for l in t.splitlines() if l.startswith(('PSCI', 'cluster domain'))))
		EOF
		)
		extra="$extra | traced psci enters: $(nice awk '/psci_domain_idle_enter/ { s = $0; sub(/.*state=/, "", s); sub(/ .*/, "", s); n[s]++ } END { for (k in n) printf "%s=%d ", k, n[k]; if (!length(n)) printf "none" }' $S/$tag.ftrace)"
		rm -f $S/$tag.ftrace $S/$tag.netcon
	fi
	echo "$(date '+%m-%d %T') $r $tag slp=$slp cpus=6,7 secs=$secs stream=${MODE:-lean} $extra" | tee -a $log ;;
slice)
	tag=$2
	echo "## $tag"
	nice awk -v tag="$tag" '
	{ if (!match($0, /\[ *[0-9]+\.[0-9]+\]/)) next
	  t = substr($0, RSTART + 1, RLENGTH - 2) + 0
	  if (index($0, "idlev-START " tag)) { on = 1; mx = t; t0 = t; print "netconsole start marker at " t; next }
	  if (!on) next
	  if (t < mx - 5) exit
	  if (t > mx) mx = t
	  if (match($0, /cpuhb[0-7]/)) hb[substr($0, RSTART + 5, 1)] = t; else other[++n] = $0 }
	END { for (c = 0; c < 8; c++) printf "cpuhb%d %s  ", c, hb[c]; print ""
	      d = 0; for (c = 1; c < 8; c++) if (hb[c] < hb[d]) d = c
	      printf "HB-DEAD cpu%d last heartbeat at %.2f = +%.0fs after start, %.0fs before the last netconsole line\n", d, hb[d], hb[d] - t0, mx - hb[d]
	      print "last netconsole line at " mx "; non-heartbeat lines after the marker: " n + 0
	      for (i = (n > 12 ? n - 11 : 1); i <= n; i++) print "  " substr(other[i], 1, 220) }' $S/$tag.netcon
	nice awk -v tag="$tag" '
	{ if (!match($0, /\[00[0-7]\] +[^ ]+ +[0-9]+\.[0-9]+: /)) next
	  s = substr($0, RSTART, RLENGTH); c = substr(s, 4, 1) + 0; sub(/^.*\] +[^ ]+ +/, "", s); t = s + 0
	  if (index($0, "idlev-START " tag)) { on = 1; t0 = t; mx = t }
	  if (!on) next
	  if (t < mx - 5) exit
	  if (t > mx) mx = t
	  last[c] = t; n[c]++; L[c, n[c] % 10] = $0
	  if ($0 ~ /psci_domain_idle_enter/) { open[c] = $0; ne[c]++; st = $0; sub(/.*state=/, "", st); sub(/ .*/, "", st); by[c " " st]++ }
	  else if ($0 ~ /psci_domain_idle_exit/) open[c] = "" }
	END { printf "# ftrace: start marker %.6f, last line of this boot %.6f (+%.1fs)\n", t0, mx, mx - t0
	  d = -1; for (c = 6; c < 8; c++) if (open[c] != "" && (d < 0 || last[c] < last[d])) d = c
	  for (c = 0; c < 8; c++) if (c in last) printf "cpu%d last event %.6f (%.3fs before the end) events %d: %s\n", c, last[c], mx - last[c], n[c], (open[c] != "" ? "INSIDE psci (enter without exit): " substr(open[c], index(open[c], "psci_")) : "last psci event was an exit / none")
	  if (d >= 0) printf "DEAD cpu%d inside %s at +%.1fs, %.3fs before the stream stopped\n", d, substr(open[d], index(open[d], "state=")), last[d] - t0, mx - last[d]
	  else print "DEAD none of cpu6/7 inside psci at the end of the stream"
	  printf "psci entries in this trial:"; for (k in by) printf " cpu%s:%d", k, by[k]; print ""
	  for (c = 6; c < 8; c++) { print "# cpu" c " last 10 psci/scm events:"; for (i = n[c] - 9; i <= n[c]; i++) if (i > 0) print "  " L[c, i % 10] } }' $S/$tag.ftrace
	echo "# raw stream, last 60 lines of the boot that froze:"
	nice awk -v tag="$tag" '
	{ if (index($0, "idlev-START " tag)) on = 1
	  if (!on) next
	  if (match($0, /\] +[^ ]+ +[0-9]+\.[0-9]+: /)) { s = substr($0, RSTART, RLENGTH); sub(/^\] +[^ ]+ +/, "", s); t = s + 0; if (t < mx - 5) exit; if (t > mx) mx = t }
	  B[++n % 60] = $0 }
	END { for (i = n - 59; i <= n; i++) if (i > 0) print B[i % 60] }' $S/$tag.ftrace ;;
esac
