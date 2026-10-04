# a52q modem DOG stall - root-cause pass 2 (2026-10-02, read-only, logs only)

## Verdict
Most likely cause (confirmed correlation in logs, mechanism read in 7.3-rc5 source, errno NOT yet observed):
the in-kernel QRTR nameserver aborts `announce_servers()` when the modem's HELLO arrives, so the modem is never
told about the AP-side services (rmtfs svc 14, tqftpserv 4096, pd-mapper 64/66, ...). Modem init waits for them -> DOG ~40 s.

Evidence unique to the stalled boot (absent in clean boot, grep both files):
  boot-stall.txt:1450  [13.729047] kernel: failed to announce new service
  boot-stall.txt:1451  [13.730180] kernel: failed while handling packet from 0:-2     (node 0 = MPSS, port -2 = QRTR_PORT_CTRL)
  boot-stall.txt:1452  [13.730493] ipa: received modem running event     <- 1.4 ms later
Code (tree ~/src/linux-a52q-mainline, 7.3-rc5):
  net/qrtr/ns.c:216-238 announce_servers(): loop over local servers, `service_announce_new(sq, srv)`; on ret<0 and
    ret != -ENODEV -> pr_err("failed to announce new service") and `return ret` => REMAINING servers are skipped.
  net/qrtr/ns.c:330 ctrl_cmd_hello() = announce_servers(); ns.c:693 prints "failed while handling packet from %d:%d".
  net/qrtr/af_qrtr.c:353-357 qrtr_node_enqueue(): returns -EAGAIN for any non-HELLO packet while node->hello_sent==false
    (set true only after OUR hello xmit succeeded, af_qrtr.c:391; hello is sent from delayed work qrtr_hello_work,
    af_qrtr.c:594, which itself retries every 100 ms if ns port not bound / alloc fail). Other non-ENODEV errors possible
    via qrtr_tx_wait() (flow control). The exact errno is unknown: the pr_err does not print it.
  => Race: modem HELLO is handled by ns worker before our HELLO to node 0 completed (or tx-flow error) -> first
    NEW_SERVER send fails -> loop aborted -> nothing announced. Intermittent because it is a ~ms race at modem boot.
Why the modem stalls: in the stall boot tqftpserv gets NO request until after recovery (ota_firewall probes at 54.68 s),
  clean boot gets them at 14.61 s (0.22 s after modem up). rmtfs/tqftpserv were registered long before (rmtfs.c:
  rmtfs_mem_open -> storage_init -> qrtr_publish -> only THEN rproc_start; so rmtfs ordering is correct by construction).
  The modem therefore never saw the services even though they existed locally. After recovery the modem re-HELLOs, the
  race is not hit again, announce succeeds -> tqftpserv traffic and ath10k QMI (56.3 s) resume.
Caveat: the lookup-notify path (ns.c:497+) is also skipped in the NEW_SERVER variant of the same error, so either
  message shape could cause it. Only 1 stall boot in evidence, so n=1 correlation.

## Timeline diff (kernel+userspace, 11-20 s). T = stall / clean
- qrtr-ns.service Started 12.977 / 13.627; userspace qrtr-ns "nameserver already running, going dormant" 13.008 / 13.663 (harmless, kernel ns used)
- rmtfs.service Started 12.986 / 13.633 (no log output from rmtfs at all - not verbose)
- tqftpserv Started 13.009 / 13.652
- "powering up modem" 13.023 / 13.649  (= rmtfs `-s` writing "start" to remoteproc state; +37 ms / +16 ms after rmtfs Started)
- Booting modem.mbn 13.348 / 14.000; ipa "modem starting" 13.349 / 14.002
- STALL ONLY: 13.729 "failed to announce new service", 13.730 "failed while handling packet from 0:-2"
- ipa "modem running" 13.730 / 14.385; "modem is now up" 13.732 / 14.388 (boot time to up: 0.71 s / 0.74 s, identical)
- CLEAN: tqftpserv ota_firewall/ruleset x2 at 14.612 (T+0.22 s); ath10k qmi chip_id at 15.955 (T+1.57 s); qcom-modem-setup "Using qrtr://0" 16.165
- STALL: none of those; ModemManager dbus activation timeout 41.2; DOG 53.754; recovery up 54.261; tqftpserv probes 54.678; ath10k qmi 56.327; modem-setup waited 43 s.
- No pd-mapper/servreg/sysmon/rmtfs_mem/uio kernel log lines in either boot (drivers silent), so those cannot be diffed.
- ModemManager/qcom-modem-setup (modem-setup starts 12.97/13.62 but only polls qrtr; first QMI use 16.2 clean) do not touch the modem before it is up -> not a cause.
- a52q-efs-wifi-mac mounts sda6 ro for ~30 ms at 12.95 (stall); unrelated device from rmtfs partitions (modemst1/2,fsg,fsc).

## Ranked causes
1. QRTR ns HELLO/announce race (above). Strong.
2. rmtfs now read-write (drop-in 10-rw-efs.conf: `rmtfs -P -s`, no -r). Weak: boot times identical until the ns error; rmtfs has not
   yet been asked anything. But keep in mind for post-recovery behaviour; stall rate pre-dated? unknown. Not proven irrelevant.
3. pd-mapper module timing: already =y; residual 1/6 not explained by it. Not excluded as a partial cause earlier.
4. CPU/IRQ starvation, udev, ModemManager: no evidence (modem boot durations equal; MM starts after).

## Fix to try
A. Diagnose first (1 line): in net/qrtr/ns.c print ret: `pr_err("failed to announce new service: %d\n", ret);` (both sites).
B. Fix (kernel, net/qrtr/ns.c announce_servers): do not abort on transient errors:
     if (ret == -ENODEV) continue;
     if (ret == -EAGAIN) { msleep(20) retry same srv up to ~50x (worker context may sleep); }
     else log and `continue` (never `return` mid-list).
   Equivalent alternative: in ctrl_cmd_hello, if announce fails with -EAGAIN, requeue the hello via queue_work after 100 ms.
   Alternative in af_qrtr.c: let qrtr_node_enqueue queue/delay instead of -EAGAIN for ns replies.
C. Userspace belt-and-braces (no kernel): after modem up, re-publish is NOT possible without restarting rmtfs (stops modem via -s);
   do not use. (tqftpserv restart re-publishes svc 4096 only.)

## Verify (<=10 reboots)
Build with A+B. Each boot: `journalctl -k | grep -E 'failed to announce|failed while handling|DOG|crash detected'` must be empty AND
`journalctl -u tqftpserv` shows ota_firewall within 1 s of "modem is now up". Baseline 1/6: 10 clean = ~84% confidence; if build A-only
shows a stall, errno in the log confirms/denies -EAGAIN. Also test by log: if 'failed to announce' appears but boot is clean with B,
B is working (retry succeeded).
Also check upstream: no lore search succeeded (403); unverified whether a fix exists in linux-next net/qrtr (check `git log net/qrtr` after 7.3-rc5).
