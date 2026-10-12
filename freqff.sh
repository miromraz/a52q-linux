#!/bin/bash
# Gold-cluster frequency-transition stress (silent big-core freeze hunt). Sibling of idlev.sh / camff.sh.
# Usage: freqff.sh prep                     push ff.py to /var/tmp/freqff on the phone
#        freqff.sh stream quiet|lean|full   runtime tracefs setup (quiet: nothing streamed; lean: cpu_frequency +
#                                           psci for cpu6/7, rpmh, scm, clk_set_rate; full: restart the stream service)
#        freqff.sh trial ARM N SECS ARGS    one trial, tag freqff-ARM-N; ARGS = ff.py worker specs (see ff.py)
#        freqff.sh slice TAG                freeze evidence from /tmp/freqff/TAG.{netcon,ftrace}
#        freqff.sh reboot                   reboot, wait for ssh and uptime 90 s
#        freqff.sh clean                    restore knobs + full stream, remove /var/tmp/freqff
# Env for trial: MODE=quiet|lean (quiet)  PRE / POST = shell run on the phone before / after the stress
#                (sysfs variation + restore; a freeze reboots, which restores too)
D=~/mobile-linux/linux-a52q/logs-1003 S=/tmp/freqff E=$D/freqff-1011 log=$D/trials.log
P() { timeout "${T:-12}" ssh -o ConnectTimeout=8 -o BatchMode=yes a52w "$@" 2>/dev/null; }
waitup() { local t0=$(date +%s); until P true; do [ $(( $(date +%s) - t0 )) -gt 600 ] && return 1; sleep 5; done; }
# knobs back to the values recorded at the start of the session (2026-10-11 20:05 phone time)
RESTORE='cd /sys/devices/system/cpu; for p in 0 6; do q=cpufreq/policy$p; echo schedutil > $q/scaling_governor; cat $q/cpuinfo_max_freq > $q/scaling_max_freq; cat $q/cpuinfo_min_freq > $q/scaling_min_freq; echo 1000 > $q/schedutil/rate_limit_us; done; for f in cpu[0-7]/cpuidle/state[1-9]/disable; do echo 0 > $f; done'
mkdir -p $S $E

case $1 in
prep)
	P 'mkdir -p /var/tmp/freqff; cat > /var/tmp/freqff/ff.py' <<-'EOF'
	#!/usr/bin/python3
	# ff.py SECS SPEC...   self-limiting cpufreq stress; every worker exits after SECS (alarm backstop SECS+15)
	#   busy=CPUS                         one 100 % loop pinned on each cpu ("6,7")
	#   burst=CPUS:ON_MS:OFF_MS           one busy/sleep worker pinned on each cpu
	#   tog=POLICY:KNOB:F1,F2..:SLEEP_MS:CPUS   rewrite scaling_{max_freq|min_freq|setspeed} (KNOB max|min|set)
	#                                     cycling through the values, sleeping SLEEP_MS between writes (0 = none),
	#                                     the writer itself allowed on CPUS
	# Parent: pauses the workers (SIGSTOP) while any cpu thermal zone is above 80 C, prints writer counts.
	import glob, os, signal, sys, time
	secs = float(sys.argv[1]); end = time.monotonic() + secs
	cp = '/sys/devices/system/cpu/cpufreq/'
	def cpus(s): return {int(c) for c in s.split(',')}
	def busy(c):
	    os.sched_setaffinity(0, {c})
	    while time.monotonic() < end: pass
	def burst(c, on, off):
	    os.sched_setaffinity(0, {c})
	    while time.monotonic() < end:
	        t = time.monotonic() + on
	        while time.monotonic() < t: pass
	        time.sleep(off)
	def tog(pol, knob, freqs, slp, on):
	    os.sched_setaffinity(0, on)
	    f = os.open(cp + pol + '/' + {'max': 'scaling_max_freq', 'min': 'scaling_min_freq', 'set': 'scaling_setspeed'}[knob], os.O_WRONLY)
	    n = err = 0
	    while time.monotonic() < end:
	        for v in freqs:
	            try: os.pwrite(f, v, 0); n += 1
	            except OSError: err += 1
	            if slp: time.sleep(slp)
	    print(f'tog {pol} {knob} writes={n} errors={err} rate={n / secs:.0f}/s', flush=True)
	jobs = []
	for spec in sys.argv[2:]:
	    k, v = spec.split('=', 1); a = v.split(':')
	    if k == 'busy': jobs += [(busy, (c,)) for c in cpus(a[0])]
	    elif k == 'burst': jobs += [(burst, (c, float(a[1]) / 1e3, float(a[2]) / 1e3)) for c in cpus(a[0])]
	    elif k == 'tog': jobs.append((tog, (a[0], a[1], [x.encode() for x in a[2].split(',')], float(a[3]) / 1e3, cpus(a[4]))))
	    else: sys.exit('bad spec ' + spec)
	pids = []
	for fn, args in jobs:
	    pid = os.fork()
	    if not pid:
	        signal.alarm(int(secs) + 15); fn(*args); os._exit(0)
	    pids.append(pid)
	signal.alarm(int(secs) + 20)
	zones = [z + '/temp' for z in glob.glob('/sys/class/thermal/thermal_zone*') if open(z + '/type').read().startswith('cpu')]
	hot = False; paused = 0
	while time.monotonic() < end:
	    time.sleep(2)
	    t = max(int(open(z).read()) for z in zones)
	    if (t > 80000) != hot and (t > 80000 or t < 70000):
	        hot = not hot
	        for p in pids: os.kill(p, signal.SIGSTOP if hot else signal.SIGCONT)
	        open('/dev/kmsg', 'w').write(f'freqff THERMAL-{"PAUSE" if hot else "RESUME"} {t}\n')
	    paused += 2 * hot
	for p in pids: os.kill(p, signal.SIGCONT)
	for p in pids: os.waitpid(p, 0)
	print(f'thermal-paused={paused}s', flush=True)
	EOF
	P 'ls -la /var/tmp/freqff' ;;
stream)
	case $2 in
	full) P 'systemctl restart a52-ftrace-stream; sleep 3; echo "events: $(cat /sys/kernel/tracing/set_event | wc -l) vphlog=$(pgrep -fc a52-vphlog.py)"' ;;
	*)	[ "$2" = lean ] && on=1 || on=0
		P "ON=$on sh -s" <<-'EOF'
		T=/sys/kernel/tracing
		for g in rpm clk regulator interconnect rpmh qcom_scm; do echo 0 > $T/events/$g/enable; done
		for e in cpu_frequency psci_domain_idle_enter psci_domain_idle_exit; do echo 'cpu_id >= 6' > $T/events/power/$e/filter; echo $ON > $T/events/power/$e/enable; done
		for e in rpmh qcom_scm clk/clk_set_rate; do echo $ON > $T/events/$e/enable; done
		pkill -f a52-vphlog.py
		echo "up $(cut -d' ' -f1 /proc/uptime) events: $(cat $T/set_event | tr '\n' ' ') vphlog=$(pgrep -fc a52-vphlog.py)"
		EOF
	esac
	a=$(stat -c %s $D/ftrace-dev.log); sleep 5; b=$(stat -c %s $D/ftrace-dev.log); echo "stream rate $(( (b - a) / 5 )) B/s" ;;
reboot)
	P 'systemctl reboot'; sleep 25; waitup || { echo NO-RECOVERY; exit 2; }
	until [ "$(P 'pgrep -f udprelay.py >/dev/null && cut -d. -f1 /proc/uptime' || echo 0)" -ge 90 ]; do sleep 5; done
	P 'uname -r; ls /boot/EFI/Linux/; cut -d" " -f1 /proc/uptime' ;;
clean)
	P "$RESTORE; rm -rf /var/tmp/freqff; systemctl restart a52-ftrace-stream; sleep 3; grep -H . /sys/devices/system/cpu/cpufreq/policy[06]/scaling_governor /sys/devices/system/cpu/cpufreq/policy[06]/scaling_m??_freq /sys/devices/system/cpu/cpufreq/policy[06]/schedutil/rate_limit_us; echo disabled-idle-states=\$(cat /sys/devices/system/cpu/cpu[0-7]/cpuidle/state[1-9]/disable | grep -c 1) events=\$(wc -l < /sys/kernel/tracing/set_event) vphlog=\$(pgrep -fc a52-vphlog.py); ls /var/tmp/freqff 2>&1" ;;
trial)
	arm=$2 tag=freqff-$2-$3 secs=$4; shift 4; mode=${MODE:-quiet}
	until [ "$(P 'cut -d. -f1 /proc/uptime' || echo 0)" -ge 90 ]; do sleep 5; done	# let a fresh boot settle
	$0 stream $mode > $S/$tag.stream 2>&1
	tail -n0 -F $D/ftrace-dev.log > $S/$tag.ftrace 2>/dev/null & t1=$!
	tail -n0 -F $D/netcon-dev.log > $S/$tag.netcon 2>/dev/null & t2=$!
	sleep 1
	P "setsid nohup sh -c '
		m() { echo \"\$1\" > /dev/kmsg; echo \"\$1\" > /sys/kernel/tracing/trace_marker; }
		$PRE
		m \"freqff-START $tag\"
		python3 /var/tmp/freqff/ff.py $secs $* > /var/tmp/freqff/$tag.out 2>&1
		m \"freqff-END $tag\"
		$POST
		$RESTORE' >/dev/null 2>&1 &" || { kill $t1 $t2; echo "start failed"; exit 1; }
	# counters die with the reset: sample them here every 3 s
	timeout $((secs + 20)) ssh -o ConnectTimeout=8 -o BatchMode=yes a52w 'cd /sys/devices/system/cpu/cpufreq; while :; do
		echo "$(cut -d" " -f1 /proc/uptime) $(cat policy0/stats/total_trans policy6/stats/total_trans policy0/scaling_cur_freq policy6/scaling_cur_freq | tr "\n" " ") $(cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null | sort -n | tail -1) $(cat /sys/class/thermal/cooling_device*/cur_state | tr -d "\n")"
		sleep 3; done' > $E/$tag.samp 2>/dev/null & t3=$!
	t0=$(date +%s) fail=0 r=OK
	while [ $(( $(date +%s) - t0 )) -lt $((secs + 6)) ]; do
		sleep 10
		if T=9 P true; then fail=0; else fail=$((fail + 1)); fi
		[ $fail -ge 3 ] && { r=HANG; break; }	# ssh unreachable for 30 s
	done
	kill $t3 2>/dev/null
	# uptime first..last sample, policy0/6 transitions and rates in between, hottest zone seen
	# the sampler brackets the stress on an OK trial (rate = delta / SECS); on a HANG the rate is over the sampled span
	stats=$(awk -v r=$r -v secs=$secs 'NF >= 6 { if (!n++) { u0 = $1; a0 = $2; b0 = $3 } u = $1; a = $2; b = $3; if ($6 > mt) mt = $6 }
		END { d = r == "OK" ? secs : u - u0; if (d <= 0) d = 1; printf "samples=%d span=%.0fs p6trans=%d (%.0f/s) p0trans=%d (%.0f/s) maxT=%.1fC", n, u - u0, b - b0, (b - b0) / d, a - a0, (a - a0) / d, mt / 1000 }' $E/$tag.samp)
	if [ $r = HANG ]; then
		waitup || { kill $t1 $t2; echo "$(date '+%m-%d %T') NO-RECOVERY $tag (needs human)" | tee -a $log; exit 2; }
		sleep 2; kill $t1 $t2
		$0 slice $tag > $E/$tag.txt 2>&1
		extra="$(grep -m1 '^HB-DEAD' $E/$tag.txt) | back after $(( $(date +%s) - t0 ))s"
	else
		sleep 2; kill $t1 $t2
		extra=$(P "cat /var/tmp/freqff/$tag.out" | tr '\n' ' ')
		rm -f $S/$tag.ftrace $S/$tag.netcon
	fi
	echo "$(date '+%m-%d %T') $r $tag secs=$secs stream=$mode args=[$*] pre=[$PRE] $stats | $extra" | tee -a $log
	[ $r = OK ] ;;
slice)
	tag=$2
	echo "## $tag"
	nice awk -v tag="$tag" '
	{ if (!match($0, /\[ *[0-9]+\.[0-9]+\]/)) next
	  t = substr($0, RSTART + 1, RLENGTH - 2) + 0
	  if (index($0, "freqff-START " tag)) { on = 1; mx = t; t0 = t; print "netconsole start marker at " t; next }
	  if (!on) next
	  if (t < mx - 5) exit
	  if (t > mx) mx = t
	  if (match($0, /cpuhb[0-7]/)) hb[substr($0, RSTART + 5, 1)] = t; else other[++n] = $0 }
	END { for (c = 0; c < 8; c++) printf "cpuhb%d %s  ", c, hb[c]; print ""
	      d = 0; for (c = 1; c < 8; c++) if (hb[c] < hb[d]) d = c
	      printf "HB-DEAD cpu%d last heartbeat at %.2f = +%.0fs after start, %.0fs before the last netconsole line\n", d, hb[d], hb[d] - t0, mx - hb[d]
	      print "last netconsole line at " mx "; non-heartbeat lines after the marker: " n + 0
	      for (i = (n > 20 ? n - 19 : 1); i <= n; i++) print "  " substr(other[i], 1, 220) }' $S/$tag.netcon
	# lean stream: per CPU the last event, and the last 20 events executed on cpu6 / cpu7
	nice awk -v tag="$tag" '
	{ if (!match($0, /\[00[0-7]\] +[^ ]+ +[0-9]+\.[0-9]+: /)) next
	  s = substr($0, RSTART, RLENGTH); c = substr(s, 4, 1) + 0; sub(/^.*\] +[^ ]+ +/, "", s); t = s + 0
	  if (index($0, "freqff-START " tag)) { on = 1; t0 = t; mx = t }
	  if (!on) next
	  if (t < mx - 5) exit
	  if (t > mx) mx = t
	  last[c] = t; n[c]++; L[c, n[c] % 20] = $0 }
	END { printf "# ftrace: start marker %.6f, last line of this boot %.6f (+%.1fs)\n", t0, mx, mx - t0
	  for (c = 0; c < 8; c++) if (c in last) printf "cpu%d last event %.6f (%.3fs before the end) events %d\n", c, last[c], mx - last[c], n[c]
	  for (c = 6; c < 8; c++) { print "# cpu" c " last 20 events:"; for (i = n[c] - 19; i <= n[c]; i++) if (i > 0) print "  " L[c, i % 20] } }' $S/$tag.ftrace
	echo "# raw stream, last 60 lines of the boot that froze:"
	nice awk -v tag="$tag" '
	{ if (index($0, "freqff-START " tag)) on = 1
	  if (!on) next
	  if (match($0, /\] +[^ ]+ +[0-9]+\.[0-9]+: /)) { s = substr($0, RSTART, RLENGTH); sub(/^\] +[^ ]+ +/, "", s); t = s + 0; if (t < mx - 5) exit; if (t > mx) mx = t }
	  B[++n % 60] = $0 }
	END { for (i = n - 59; i <= n; i++) if (i > 0) print B[i % 60] }' $S/$tag.ftrace ;;
esac
