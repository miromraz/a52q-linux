#!/bin/bash
# Per-trial evidence summary for camff.sh trials, from /tmp/camff/TAG.{ftrace,netcon}.
# Prints: per-CPU last seen (ftrace + cpuhb heartbeat), first silent CPU and its last 15 events,
# last capture-thread event, SCM calls / RPMh requests without completion, big-core PSCI idle
# state, last cpu_frequency, VPH_PWR minimum. Usage: camff-slice.sh TAG [> logs-1003/camfreeze-1011/TAG.txt]
# ponytail: one awk pass over the slice held in memory; fine for the <50 MB slices of one trial.
tag=$1 S=/tmp/camff
echo "## $tag"
echo "# netconsole heartbeats: last cpuhbN before the reboot (kernel time)"
nice awk -v tag="$tag" '
	{ if (!match($0, /\[ *[0-9]+\.[0-9]+\]/)) next
	  t = substr($0, RSTART + 1, RLENGTH - 2) + 0
	  if (index($0, "=== TRIAL " tag " ===")) { on = 1; print "marker at " t; next }
	  if (!on) next
	  if (t < mx - 5) exit			# clock restarted = next boot
	  if (t > mx) mx = t
	  if (index($0, "=== END " tag)) print "end marker at " t
	  if (match($0, /cpuhb[0-7]/)) hb[substr($0, RSTART + 5, 1)] = t
	  else if ($0 !~ /=== (TRIAL|END)/) other[++n] = $0 }
	END { for (c = 0; c < 8; c++) printf "cpuhb%d %s  ", c, hb[c]; print ""
	      print "last netconsole line at " mx "; non-heartbeat kernel lines after the marker: " n + 0
	      for (i = (n > 6 ? n - 5 : 1); i <= n; i++) print "  " substr(other[i], 1, 160) }' $S/$tag.netcon
nice awk -v tag="$tag" '
	function ts(   s) { s = substr($0, RSTART, RLENGTH); sub(/^.*\] +[^ ]+ +/, "", s); return s + 0 }
	{ if (!match($0, /\[00[0-7]\] +[^ ]+ +[0-9]+\.[0-9]+: /)) next
	  t = ts(); c = substr($0, RSTART + 3, 1) + 0
	  if (index($0, "TRIAL " tag)) { on = 1; t0 = t }
	  if (!on) next
	  if (t < mx - 5) exit			# clock restarted = next boot
	  if (t > mx) mx = t
	  if (index($0, "END " tag)) tend = t
	  n++; L[n] = $0; C[n] = c; T[n] = t; if (t > last[c]) last[c] = t; cnt[c]++
	  if ($0 ~ /^ *(CameraManager|SWIspWorker|cam)-[0-9]+ /) lastcam = $0
	  if ($0 ~ / cam_cc_| titan|acb3000|ac4[ab]000/) lastcamev = $0
	  if ($0 ~ /5000000\.gpu|506a000\.gmu|gpu_cc_/) lastgpu = $0
	  if (match($0, /scm_smc_request: smc_id:0x[0-9a-f]+/)) { split($0, a, "["); scm[a[1] substr($0, RSTART + 24, RLENGTH - 24)] = $0 }
	  else if (match($0, /scm_smc_done: smc_id:0x[0-9a-f]+/)) { split($0, a, "["); delete scm[a[1] substr($0, RSTART + 21, RLENGTH - 21)] }
	  else if ($0 ~ /rpmh_send_msg: .*\[active\] cmd\(n\): 0 /) { match($0, /tcs\(m\): [0-9]+/); rp[substr($0, RSTART + 8, RLENGTH - 8) + 0] = $0; rpt[substr($0, RSTART + 8, RLENGTH - 8) + 0] = t; nsend++ }
	  else if (match($0, /rpmh_tx_done: .*tcs-m: [0-9]+/)) { m = $0; sub(/^.*tcs-m: /, "", m); delete rp[m + 0]; ndone++ }
	  else if (match($0, /psci_domain_idle_(enter|exit): cpu_id=[67]/)) { k = substr($0, RSTART + RLENGTH - 1, 1); psci[k] = ($0 ~ /idle_enter/ ? "ENTERED, no exit: " : "exited: ") $0; npsci[k]++ }
	  else if (match($0, /cpu_frequency: state=[0-9]+ cpu_id=[67]/)) freq[substr($0, RSTART + RLENGTH - 1, 1)] = $0
	  else if (match($0, /vph uV min=[0-9]+/)) { nv++; VT[nv] = t; VV[nv] = substr($0, RSTART + 11, RLENGTH - 11) + 0 }
	  else if ($0 ~ /: fg uV=/) fg = $0 }
	END {
	  print "# ftrace: trial marker at " t0 ", END marker at " (tend ? tend : "(none)") ", last event at " mx ", " n " events"
	  d = 0; for (c = 0; c < 8; c++) { printf "cpu%d last %.3f (%d ev)  ", c, last[c], cnt[c]; if (last[c] < last[d]) d = c }
	  print ""; D = last[d]
	  if (tend) { print "all CPUs alive at END (control); reference time T = END marker"; D = tend; d = -1 }
	  else print "FIRST SILENT: cpu" d " at T=" D " (" mx - D " s before the last event of any CPU)"
	  if (d >= 0) { print "# last 15 events of cpu" d
	    k = 0; for (i = n; i > 0 && k < 15; i--) if (C[i] == d) O[++k] = L[i]
	    for (; k > 0; k--) print "  " substr(O[k], 1, 210) }
	  print "# last capture-thread event:\n  " substr(lastcam, 1, 210)
	  print "# last camera clk/pd/device event:\n  " substr(lastcamev, 1, 210)
	  print "# last GPU/GMU event:\n  " substr(lastgpu, 1, 210)
	  print "# scm_smc_request without scm_smc_done (whole trial):"; k = 0
	  for (i in scm) { print "  " substr(scm[i], 1, 210); k++ }; if (!k) print "  none"
	  print "# rpmh [active] requests without rpmh_tx_done at end (sent " nsend ", done " ndone "):"; k = 0
	  for (i in rp) { print "  " (rpt[i] <= D ? "(before T) " : "(after T) ") substr(rp[i], 1, 210); k++ }; if (!k) print "  none"
	  print "# PSCI domain idle, last per big core:"; for (c = 6; c < 8; c++) print "  cpu" c " (" npsci[c] + 0 " ev) " substr(psci[c], 1, 150)
	  print "# last cpu_frequency:"; for (c = 6; c < 8; c++) print "  " substr(freq[c], 1, 150)
	  lo = 1e9; lo2 = 1e9; for (i = 1; i <= nv; i++) { if (VV[i] < lo) { lo = VV[i]; lot = VT[i] } if (VT[i] <= D && VT[i] >= D - 2 && VV[i] < lo2) lo2 = VV[i] }
	  print "# VPH_PWR: min in [T-2s, T] = " lo2 " uV; min over the whole trial = " lo " uV at " lot " (" nv " windows)"
	  print "  " substr(fg, 1, 170) }' $S/$tag.ftrace
