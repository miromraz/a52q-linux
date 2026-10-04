# a52q modem "DOG detects stalled initialization" (2026-10-01)

## Most likely cause (strong evidence, not yet reproduced on device)
pd-mapper is not registered when MPSS boots. In a52q_defconfig (a52q/integ):
QCOM_PD_MAPPER=m, QCOM_RPROC_COMMON=m, QCOM_Q6V5_PAS=m (lines ~6925-7000). In 7.3 the pd-mapper
is an auxiliary device created by qcom_common.c pdm_notify_prepare() (rproc prepare), and the
qcom_pd_mapper module (auxiliary driver) is only loaded by udev/modalias AFTER that device exists.
So modem start (~13.6 s) races udev loading qcom_pd_mapper; if it loses, the modem asks for
servreg/PD mapper, gets nothing, init stalls ~40 s, DOG fires. Matches "40 s after power-up".
Upstream confirmation of the exact signature + mechanism:
- [PATCH] remoteproc: qcom_common: load pd_mapper before booting the DSP
  https://ratatoskr.run/linux-arm-msm/2026/09/17492534 (also mail-archive linux-kernel msg2653217)
  Log: "qcom_q6v5_pas ...remoteproc: fatal error received: dog_hal_common.c:173:DOG detects stalled
  initialization", ~40 s after power-up, Agatti/Arduino UNO Q; fix = MODULE_SOFTDEP("pre: qcom_pd_mapper")
  in qcom_common. Not in our tree (grep MODULE_SOFTDEP in qcom_common.c: none).
Intermittent 2/6 = udev ordering race, consistent across two kernel builds.

## rmtfs/tqftpserv: secondary
rmtfs/tqftpserv start at ~13.6 s too; modem EFS requests before rmtfs is up normally just retry (QRTR
lookup), they do not trip the init DOG. rmtfs_mem DT is sane (client-id 1, vmid MSS_MSA, a52q reg override
0xf4f00000/0x202000). No evidence found that size/vmid matter. The tqftpserv mcfg/ota_firewall rejections
occur on good boots (per user) so are not the cause. Not verified against logs (phone not touched).

## WLAN PD not returning after recovery (inference only, nothing found upstream)
On SSR pdm_notify_unprepare/prepare delete and re-add the aux device, so pd-mapper is re-registered while
the module is already loaded; WLAN PD then depends on the modem fully re-initialising. Plausible reasons it
sometimes fails: modem crashes again / recovery races pd-mapper re-probe; ath10k_snoc=m QMI client re-arm.
Fixing the first crash removes the scenario. If wld0 still fails after a crash, capture
`qrtr-lookup` (svc 64/66 servreg, 69 WLFW) and dmesg 'ath10k' after recovery.
Related only: ath10k_snoc devcoredump alignment fault can break SSR (memcpy_fromio fix, ratatoskr linux-wireless 2026/07).

## Fix to try first (kernel, one-line, no DT change)
Option A (preferred, matches upstream): add `MODULE_SOFTDEP("pre: qcom_pd_mapper");` to
drivers/remoteproc/qcom_common.c.
Option B (config only): QCOM_PD_MAPPER=y (QRTR=y already; deps NET && QRTR OK) so the driver is bound
the instant the aux device is added. Also acceptable: userspace /etc/modules-load.d/ or initramfs include
qcom_pd_mapper (weaker; ordering vs udev still racy unless in initrd).
Verify: 8-10 reboots; dmesg must show no "fatal error received"; `journalctl -k | grep -E 'DOG|crash detected'`
empty; qrtr-lookup shows svc 64/66 and 69 within ~20 s; wld0 present. Baseline failure rate 2/6, so
0/10 gives reasonable (not conclusive) confidence. Also check `lsmod` order / dmesg timestamp of
qcom_pd_mapper load < "modem is now up".
