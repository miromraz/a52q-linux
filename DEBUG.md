# A52q U-Boot chainload debug

## Symptom
Samsung ABL shows "CURRENT BINARY: Custom", passes the logo, then bootloop or Download Mode.
No U-Boot output on screen, no USB (fastboot never enumerates).

## Timeline of flashes (2026-09-24)
| build | dtbo | result |
|-|-|-|
| U-Boot, text_offset 0xffffffff80000000, normal env | valid hdr, 0 entries | Download Mode ~11 s after reboot (ABL fail) |
| same | zeroed (invalid magic) | "crashes right after Samsung screen", Download Mode ~39 s after reboot |
| probe: preboot empty, bootcmd=fastboot | zeroed | constant bootloop |
| text_offset 0x80000 (Pixel-fork fix) | zeroed | Download Mode (user entered it; ~46 s) |
| + WATCHDOG_AUTOSTART | zeroed | bootloop (user report) |

Note: some "Download Mode" returns were the user's manual key combo, not a fallback — timing-based
conclusions (watchdog ~30 s) are NOT reliable.

## Evidence
- ABL (A525FXXSCFYF1) strings: exact appended-DTB match skips DTBO ("Exact DTB match found. DTBO search
  is not required"); valid-but-empty DTBO -> "Board Dtbo blob not found" path; unlocked -> AVB failure is
  non-fatal ("State: Unlocked, AvbSlotVerify returned %a, continue boot").
- Known-good reference: velvet-os boot-a52.img-6.0.0 (ref/boot-a52.img): header v0, NO os_version/patch level,
  cmdline set, real ramdisk, kernel = gzip(Image) + appended DTB, arm64 text_offset = 0x0,
  DTB msm-id <0x1bb 0>, board-id <0x22 6>, no root pmic-id. Same IDs/layout as ours.
- Flashing: Odin works on a directly connected phone (no hub). Heimdall only works on the first session after
  a fresh Download Mode entry. `fastboot devices` polling while Download Mode is open breaks the session.

## Open hypotheses
1. U-Boot starts but crashes/hangs very early (before video/USB) — needs an observation channel.
2. text_offset: known-good uses 0x0, we tried 0xffffffff80000000 and 0x80000.
3. os_version/patch-level fields in the header (ours 13.0.0 / 2025-06, known-good has none).

## Research result (22:55)
- Root cause of "bootloop with nothing on screen": we built plain `qcom_defconfig` WITHOUT the official
  phone fragment `board/qualcomm/qcom-phone.config` (docs.u-boot.org board/qualcomm/board.rst:
  `make qcom_defconfig qcom-phone.config`). Without it CONFIG_PANIC_HANG is off -> any U-Boot panic resets
  instantly (= bootloop, message never visible). The fragment also gives CONSOLE_RECORD + `fastboot oem console`,
  the phone env (volume-key bootmenu with UMS/fastboot entries) and key remap. Pixel 4a build uses exactly this.
- sm7125-mainline/u-boot fork only ships Xiaomi curtana/joyeuse images; nobody has published an a52q U-Boot.
- Samsung ABL fastboot is gutted (per the a52q DT series cover letter) - flashing is Odin only.
- Next build: qcom_a52q_defconfig + qcom-phone.config (+ watchdog autostart, text_offset 0x80000, as Pixel),
  header v0 without os_version/patch level (like velvet known-good).
- If it still shows nothing: flash ref/AP-velvet.tar (known-good Linux, console=tty1) to test whether this
  BIT-C bootloader still hands off to any payload.

## RESOLVED 23:00 — U-Boot runs on a52q
Build = qcom_a52q_defconfig + qcom-phone.config (repack.sh), header v0 no os_version, zeroed DTBO, flashed
with odin4 (AP tar with boot.img). Screen shows U-Boot 2026.10-rc5, "Model: Samsung Galaxy A52", UFS scan of
all 6 LUNs OK (LUN0 118.5 GB). Non-fatal UFS warnings: "error finding src node", "cannot get reset GPIO",
"invalid ref_clk setting = 0". The missing qcom-phone.config (PANIC_HANG etc.) was the difference.

## Flashing reliability (2026-09-25 evening)
- Software-triggered Download Mode (`reboot bootloader` from Linux, `adb reboot download` from Android):
  odin4 worked first try every time (01:32, 01:58).
- Key-combo Download Mode after the LineageOS sideload: 3 fresh entries, odin4 triggers a USB reset storm
  on open ("No such file or directory" on a stale /dev/bus/usb path), heimdall fails "Failed to send file
  part size packet" — even as the first tool on a fresh session with adb/fastboot not running.
- Lineage Recovery "Reboot to bootloader" = Samsung ABL FastBoot Mode (18d1:d00d), not Download Mode;
  `fastboot getvar` answers, `fastboot flash` hangs (gutted) — don't use.
- U-Boot PMIC reason: pm8998 shift is 1 → recovery = 0x02 (0x04 = bootloader → ABL FastBoot Mode).
- U-Boot needs CONFIG_BLKMAP + CMD_BLKMAP for the nested-GPT `linux` partition (was missing → only
  scsi 0-5 boot options). Also: after writing the nested image via UMS, U-Boot must be reset to rescan.

## Hardware-support gap analysis (2026-09-26, offline — phone shell access not yet granted)
Kernel: github.com/miromraz/linux obs/sm7125 (be514f237), running 6.14.7-sm7125. sm7125-samsung-common.dtsi
already describes: s6e3fc3 panel (DSI0/MDSS), stmfts touch (fts5cu56a), sm5714 charger+FG, tas2562 amps +
wcd9380 codec (sm8250-sndcard, rx/tx/va macro, SoundWire), WCN3988 BT, ath10k WiFi, GPU+zap, IPA, ADSP/CDSP/MPSS,
venus, UFS, SD, USB, keys, vibrator.
Not in DT at all: cameras (CAMSS + sensors), NFC, SSC sensors (accel/gyro/prox/light via ADSP sensor PD),
fingerprint (under-display, no mainline path).
Needs on-device verification (dmesg/probe status) before any of the above can be called "working".
- NFC (offline, untested): downstream atoll-sec-a52q-nfc_r00.dtsi = Samsung S3NRN82 "sec-nfc" @ i2c SE0 0x27,
  ven=tlmm12 (0=on, same as mainline s3fwrn5 en), firm=tlmm36, irq=tlmm37, pvdd=tlmm68. Node added as
  samsung,s3fwrn5-i2c -> patches/0001-arm64-dts-a52q-add-S3NRN82-NFC.patch (dtbs_check clean; driver already =m).
  RISK before boot-testing: s3fwrn5 requests sec_s3fwrn5_firmware.bin and flashes it if newer; S3NRN82 fw
  format/signing unverified -> do NOT ship any firmware file until version-check path is confirmed on device.
- Hall sensor: already in common.dtsi (pm6150 gpio10, SW_LID).
- Cameras (offline): downstream slots = rear IMX682 64MP (CCI0), UW S5K3L6/HI1336 12MP (CCI1), bokeh GC5035 5MP,
  front IMX616 32MP; all rails from an S2MPB03 camera PMIC. Mainline 6.14 tree: CAMSS has sc7180, but NO drivers for
  IMX682, IMX616, S5K3L6, GC5035, or S2MPB03 -> cameras = 5 new drivers, register tables must be RE'd from
  Samsung's vendor camera blobs on the phone. Largest remaining item.

## On-device bring-up (2026-09-26, BengalOS 0.26.0925.2, kernel 6.14.7-sm7125)
Access: A52 USB NIC isolated in netns `a52` (Pixel 4a also answers 172.16.42.1) via ~/.local/bin/a52-netns
ProxyCommand; `ssh a52r` = root (debug image trusts laptop key). /usr is verity: live tests go to /etc.
- WORKS as shipped: display/DSI panel, GPU (zap loads on later retry; early initramfs error is cosmetic),
  touch (stmfts), keys, vibrator (gpio57 toggles), hall, ADSP/CDSP/modem remoteprocs, Wi-Fi scan, BT scan.
- FIXED (profile/kernel, pending image rebuild):
  - BT/Wi-Fi MAC: factory addrs in EFS (efs/bluetooth/bt_addr, efs/wifi/.mac.info). a52q-efs-addr.service;
    mgmt set_public_address is only accepted while the controller is powered off. bootmac disabled.
  - sm5714-fg: read VBAT not OCV, vendor fixed-point formulas (verified vs raw i2c: 0x4830 -> 4395 mV).
  - Speakers: sm8250.c had no QUINARY_MI2S_RX case -> no bit clock -> DSP never consumes -> EIO after 550 ms.
  - Mics: TX path works on MultiMedia3 with miatoll routing (SMIC MUX0 ADC0). AMIC1->ADC1 bottom,
    AMIC4->ADC3 INP4 top, AMIC2->ADC2 headset. UCM Samsung/a52q written.
  - Sensors (SSC): vendor configs from super/vendor + persist registry, patched hexagonrpcd (sunfish fork),
    socinfo IDP/443, writable registry, ssc-accel udev tag -> accel, light, compass work via iio-sensor-proxy.
    No proximity sensor on a52q.
  - RTC: pm8xxx read-only (RTC_SET_TIME fails); offset kept in /var (a52q-rtc-offset.service). The only
    SDAM (b600) is the QG scratch area - not used for the offset on purpose.
- Kernel test boots: EFI var writes are read-only under U-Boot -> no bootctl oneshot; use boot counting
  (UKI name +1). CONFIG_EFI_ZBOOT=y -> boot vmlinuz.efi, not Image. A GCC 16.1 build hangs before
  ramoops; rebuilding with Debian GCC 14.2.0-19 (= OBS toolchain) in docker `kbuild-trixie`.
- OPEN: suspend (s2idle) never resumes (USB gone; needs forced restart). Modem: both SIM slots "absent".
  NFC untested. Cameras need 5 new drivers. Fingerprint (under-display) no driver.
- Cameras identified on-device (cam-probe, 2026-09-26): main S5KGW1P id 0xF971 @cci0.0 0x2D (downstream DT's
  0x1A is the IMX682 variant), UW S5K3L6 0x30C6 @cci0.1 0x2D, front IMX616 0x0616 @cci1.0 0x1A,
  depth GC5035 0x5035 @cci1.0 0x37, macro GC5035 @cci1.0 0x3F. All rails via S2MPB03 (i2c-gpio 25/26 @0x56)
  + GPIO LDOs 63/64/65/74. Register tables: vendor /lib/camera/com.samsung.sensormodule.*.bin (CAMX).
- Suspend: FIXED. qcom-wdt left the bootloader-armed WDT running in s2idle (reset); ADSP SEE crashed on
  suspend without the sleepstate SMP2P entry+driver (ported smp2p_sleepstate); hexagonrpcd must be stopped
  across sleep (a52q-sensors-sleep.service). Verified: RTC-woken 60/120 s suspends, audio/WiFi/BT/sensors OK.

## UW S5K3L6 (a52q ultra-wide) — parked 2026-09-26

CSIPHY3 is proven good (macro GC5035 captures through it). UW sensor probes
(id 0x30C6, rev 0xB0) and configures over I2C, but does not stream. A/B test
(build C: UW->CSIPHY3->csid2->vfe_lite, gpio66 LOW, MCLK 19.2MHz, vddd=L1):

- A = original Purism flow (init+setstream+frame_2104x1560, 25MHz-tuned PLL):
  frame_count 0x0005 ADVANCES (0x12->0x18->0x1e), i.e. the sensor produces
  frames. But CSIPHY3 SoT dIRQ=0 -> MIPI link off-ratio (25MHz tables at
  19.2MHz), PHY never locks.
- B = decoded vendor flow (22-reg init + 53-reg 4000x3000 mode, 19.2MHz PLL):
  frame_count STUCK at 0x00 -> sensor never starts readout. mode_select
  0x0100=1, 0x3c1e=0, 0x0136=0x1333(19.2MHz), 0x0112=0x0a(RAW10), 0x0114=0x03(4-lane).

Diff (regs A sets, B does not): 0x0300 (vt_pix_clk_div), 0x0387/0x0901 (binning,
mode-specific). Adding 0x0300=0x0006 to the vendor mode did NOT start frame_count,
so B is missing more than one base register (the CamX sensor .so applies a base
register set absent from com.samsung.sensormodule.2_0_lsi_s5k3l6.bin).

Conclusion: sensor-init gap. Two ways forward:
1. Extract the base register set from com.samsung.sensor.s5k3l6.so and prepend to
   the vendor mode (then the 19.2MHz PLL is correct and CSIPHY3 should lock).
2. Or keep the Purism flow (which produces frames) and retune its PLL dividers
   (0x0136/0x0300/0x0304/0x0306/0x030c/0x030e) for 19.2MHz to a CSIPHY-lockable
   rate. frame_count 0x0005 (via /sys/kernel/debug/s5k3l6/{address,read}) and
   CSIPHY3 /proc/interrupts are the pass/fail probes.

Depth + macro (both GC5035) capture RAW via vfe_lite; committed DTS links those.

### UW round 2 (retuned Purism flow @19.2MHz) — 2026-09-26

Retuned the Purism flow for the real 19.2MHz MCLK: set 0x0136=0x1333, and set
link_freq to the actual OP rate MIPI_CLOCK(19.2M,4,108,1)=259.2MHz (0x0136 is
informational, doesn't change the HW PLL). Result: frame_count 0x0005 ADVANCES
(0x1b->0x23->0x2a, ~5fps) so the sensor produces frames. BUT CSIPHY3 SoT still 0
with the matched link_freq, at 4 lanes AND at 2 lanes (0x0114=1), and at BOTH
gpio66 polarities (driver-driven low, and manual 0/1). gpio66 verified toggling
("out low"/"out high" in /sys/kernel/debug/gpio).

So sensor-init is SOLVED (frames produced). The remaining UW blocker is board-
level MIPI routing: the gpio66 switch does not deliver UW's MIPI to CSIPHY3,
while macro (2-lane) reaches the same CSIPHY3 via the same switch at gpio66 high.
Next: scope the gpio66 MIPI switch net in the schematic - confirm UW's D-PHY
(clock + data lanes) is actually wired through it to CSIPHY3, and the true
select logic. Sensor + init + link_freq are no longer the issue.

### UW round 3 (MIPI-switch supply hypothesis) — 2026-09-26
Tested whether the gpio66 switch IC is powered by vreg_cam3_vana (gpio64) and/or
S2MPB03 L4 (only on when depth/macro run). Added both as optional supplies the
s5k3l6xx driver enables during UW power-on. Result: with UW streaming (frame_count
advancing), gpio64=out high (vreg_cam3_vana ON), L4 ON, gpio66=out low -> CSIPHY3
SoT STILL 0. Hypothesis disproven; reverted the test supplies. UW remains blocked
at the physical gpio66->CSIPHY3 MIPI path (board-level).

## IMX616 (front) + S5KGW1P (main) V4L2 drivers (2026-09-26)

New mainline sensor drivers written from the vendor CamX register tables
(decoded by tools/camx-sensormodule.py; C tables emitted by
tools/gen-sensor-regs.py). Kernel diff: patches/0003-a52q-imx616-s5kgw1p-wip.patch.

- drivers/media/i2c/imx616.c  (+ imx616_modes.h): Sony IMX616, cci1_i2c0 @0x1a,
  CSIPHY2, MCLK4 24 MHz, 4-lane RAW10, mode 3264x2448@30 (vendor mode[2]).
- drivers/media/i2c/s5kgw1p.c (+ s5kgw1p_modes.h): Samsung S5KGW1P, cci0_i2c0
  @0x2d, CSIPHY0, MCLK0 19.2 MHz, 3-lane RAW10, mode 4624x3468@30 (vendor mode[1]).
- DT: replaced the two a52q,cam-probe nodes with real sensor nodes; added camss
  port@0 (csiphy0) and port@2 (csiphy2).

Both probe (dmesg chip IDs: imx616 0x0616, s5kgw1p 0xf971) and appear in
/dev/media0.

IMX616: WORKS end to end. frame_count (0x0005) advances 0x71->0x8f->0xae (~31fps)
while streaming; 5 RAW frames captured via csiphy2->csid2->vfe_lite:
  /var/tmp/cam-front.raw 9987840 B (3264x2448 pgAA/RAW10), mean 21.2 std 42.9.

S5KGW1P: BLOCKED at sensor readout. init(3491)+mode(563)+streamon all apply with
no i2c errors; verified by register readback while streaming (debugfs dbg_reg):
0x0000=0xf971 (i2c OK), 0x0100=0x0100 (streaming latched), 0x0136=0x1300 (extclk
19MHz, matches MCLK), 0x0306=0x012c (PLL mult), 0x0114=0x0201 (lanes), 0x0340/0x0342
FLL/LLP correct. Yet frame_count (0x0005) stays 0xFF (SMIA "no frame produced") and
CSIPHY0 SoT stays 0 -> the sensor never starts MIPI readout. Unlike the S5K3L6 case
this is NOT a missing vt_pix_clk_div: the whole PLL/VT tree (0x0300/0x0302/0x0304/
0x0306/0x0308/0x030A/0x030C/0x030E/0x0310) is present in the vendor tables. The
remaining blocker is a readout-enable write that CamX's .so injects at runtime and
is absent from the static bin (needs a datasheet or a sibling open S5KGW/S5K2L
driver to identify). A dbg_addr/dbg_reg debugfs pair was left in s5kgw1p.c for this.

## S5KGW1P (main) CSIPHY0 no-capture — investigation (2026-09-26, cont.)

After the 16-bit-decode fix the sensor NOW produces frames: frame_count (0x0005)
advances ~30fps while streaming mode[1] 4624x3468. But CAMSS still captures 0
frames; csiphy0 (0xac65000) status regs 0x8b0.. stay dark on the data lanes.

Systematically eliminated every software lever (all verified on-device):
- Lane count: DTB had a stale 4-lane diagnostic (csiphy0_ep=<0 1 2 3>, CTRL5=0xD5).
  FIXED to <0 1 2> (CTRL5 now 0x95, verified via devmem). No change: still dark.
- Lane mapping: vendor laneAssign_raw=0x210 = straight D0->0,D1->1,D2->2, so <0 1 2>
  is correct; permutations would be wrong. Also, when 4 lanes were enabled (0xD5)
  NO physical data lane 0-3 showed SoT either -> data isn't reaching any of them.
- Settle: csiphy0 settle=0x14, identical to the WORKING front (csiphy2) at higher
  rate (2.05 Gbps). cam_cc_csiphy0_clk + cam_cc_csi0phytimer_clk (300MHz) both en=1.
- Receiver reg table (lane_regs_sc7180): proven by front locking at 2.05 Gbps > our
  2.0 Gbps; data-rate table is CPHY-only (DPHY here), so irrelevant.
- Sensor programming complete: decoded vendor bin (camx-sensormodule.py) — stream-on
  group is only 0x0100=0x0100, exactly what the driver writes; nothing missing there.
- Auto D-PHY timing: the working Samsung UW (S5K3L6) sets 0x0900=0 + 0x0820=link_rate;
  GW1P sets 0x0900=0x0212 and leaves 0x0820=0. Tested LIVE via i2ctransfer on
  /dev/i2c-20 (stop, set 0x0820=0x07d0 (2000Mbps) + 0x0900=0, restart): confirmed
  written, sensor restarted (fc reset), but csiphy0 data lanes STILL dark. Not the fix.

Conclusion: the sensor's internal readout runs (frame_count advances) and the clock
lane shows partial activity (st2=0x80), but NO HS data is detected on any csiphy0
data lane under any lane-enable mask. Since the main camera works under stock
Android, the physical MIPI path exists -> the missing element is a proprietary
MIPI data-lane / TX enable that Samsung's CamX .so writes at stream time and that is
NOT in the static parameter bin (same class as the DEBUG hypothesis above; the S5K3L6
comparison did not reveal it). Next step: disassemble the OEM s5kgw1p sensor .so for
extra stream-on register writes (esp. Samsung 0x3xxx / 0x0Bxx), or get the S5KGW1P
datasheet; alternatively scope the sensor MIPI data lanes to confirm HS output.

Kernel change this session: DTS csiphy0_ep data-lanes <0 1 2 3> -> <0 1 2> (the
only justified fix; driver unchanged since the live pokes disproved the reg theory).
Phone left on DTB 0.26.0925.33 (<0 1 2>); front (22-001a) + UW (21-002d) still
capture 5 frames each. Patch: patches/0003-a52q-imx616-s5kgw1p-wip.patch.

## ROOT CAUSE for the Samsung sensors (2026-09-26 evening)
tools/camx-sensormodule.py guessed register data width from the VALUE (<=0xff -> 1 byte). The CamX
registerData leaf is (regAddrType, regDataType, ...) with 1=byte 2=word, and Samsung S5K tables are
all word writes. A 1-byte write of e.g. 0x0003 to 0x0304 lands in the HIGH byte (divider 768) and the
0x6F12 firmware-patch stream went half corrupt. Decoder now uses the blob's own widths.
- UW S5K3L6: vendor tables with correct widths -> WORKS. 5 frames 4000x3000 via csiphy3 (gpio66 LOW)
  -> csid2 -> vfe_lite, mean 25.7 std 40.1. UW is now the default CSIPHY3 link (macro is the swap).
  (The earlier "board-level routing" conclusion was wrong; it rested on masked CSIPHY IRQ counts.)
- Main S5KGW1P: with correct widths the sensor PRODUCES frames (frame_count advances ~30 fps) but no
  data lanes are seen on CSIPHY0 in D-PHY mode (only the clock-lane position shows activity).
  Suspect C-PHY (3 "lanes" = 3 trios; GW1 supports C-PHY; vendor mode never writes 0x0111).
  Next: port "media: camss: Add support for C-PHY configuration" (David Heidelberg, v8/v9, lore
  20260610-qcom-cphy-v8-0-cd4387785179@ixit.cz), set bus-type C-PHY on the csiphy0 endpoint.
- NOTE: camss masks CSIPHY interrupts, so /proc/interrupts csiphy counts are always 0. Use the
  common status regs (base+0x8b0..0x8dc) instead.
- Torch: sm5714-charger now registers white:torch (8 steps, FLEDCNTL2 6:4) and a usb-otg-vbus
  regulator; one op-mode resolver (CNTL2 3:0: 5 chg-on-vbus, 7 otg, 8 flash-boost) shared by both.
  Verified: rear depth camera mean 14.7 -> 32.5 with torch on. OTG boost untested (needs cable) and
  Type-C role detection (SM5714 CC block @0x33 on i2c11, IRQ gpio104) is not written yet.

## Main camera S5KGW1P over MIPI C-PHY - WORKS (2026-09-26)
- Ported C-PHY RX into camss (David Heidelberg v8, hand-adapted to this older 6.14 camss)
  for sc7180/sm7125 and switched the S5KGW1P main cam to C-PHY. IT STREAMS:
  cam-main.raw 4624x3468 pgAA, 5 frames, mean 30.5 std 56.0 (real image variance; under
  D-PHY it saw no data lanes). C-PHY CONFIRMED empirically.
- What was needed (patches 0003 sensor/DT, 0004 camss):
  - CSID: set CSI2_RX_CFG0 PHY_TYPE_SEL (bit 24) via new csid_phy_config.phy_sel, derived
    from endpoint bus-type at csid_link_setup.
  - CSIPHY 3ph: new lane_regs_sc7180_cphy[3][38] C-PHY init table, taken verbatim from the
    Samsung atoll downstream csiphy_3ph_v1_2_reg (CSIPHY v1.2; downstream D-PHY table offsets
    confirmed 1:1 with mainline lane_regs_sc7180, so C-PHY offsets map directly). 3 trios,
    stride 0x200, each ends 0x800=0x0E (3-phase select). gen2_config_lanes loops 3 lanes for
    C-PHY (vs 5 for D-PHY).
  - Lane mask: C-PHY uses odd bits BIT(pos*2+1), no clock-lane enable (get_lane_mask, also
    de-duped from the inline copy in csiphy_lanes_enable which had the pos*2 form).
  - Common CTRL7 (0x81C) = 0x52 for C-PHY (0x02 for D-PHY), per downstream 3PH common regs.
  - Endpoint bus-type parsing in camss.c (V4L2_MBUS_CSI2_CPHY), stored in
    csiphy_lanes_cfg.phy_cfg; C-PHY has no clock lane so clk pos/pol skipped.
  - camss_get_link_freq gains a cphy arg (C-PHY divisor 7 vs D-PHY 16); behaviourally neutral
    here since s5kgw1p exposes a LINK_FREQ control (1 GHz used directly).
  - Sensor: s5kgw1p.c endpoint now requires bus-type C-PHY. No sensor signalling-mode write:
    Samsung ISOCELL uses its own reg map (not the Sony 0x0111), vendor never writes it, so we
    rely on the sensor's C-PHY default. DT: bus-type = <MEDIA_BUS_TYPE_CSI2_CPHY> on both
    cam_s5kgw1p_ep and csiphy0_ep, data-lanes <0 1 2> (3 trios), link-freq 1 GHz unchanged.
- D-PHY regression clean (all csid2->vfe_lite): front imx616 25.6/60.5, UW s5k3l6 25.8/39.3,
  depth gc5035 28.2/52.8. Phone left booted on test UKI 0.26.0925.35 (C-PHY DTB).
- Tuning knobs if image quality/robustness needs work: settle_cnt still uses the D-PHY formula
  (csiphy_settle_cnt_calc untouched); the downstream C-PHY data_rate_delta_table (per-bandwidth
  bias trims) was NOT ported (base table only); DT link-freq 1 GHz is a guess for the C-PHY
  symbol rate. First knobs to try if frames are noisy at higher rates.
- Auto-rotate: accel ACCEL_MOUNT_MATRIX "-1,0,0;0,-1,0;0,0,1" (90-a52q-ssc-sensors.rules) confirmed by the user on-device (2026-09-26).
- Power-off right after login (user report, 2026-09-26 23:07; also 20:51, 20:55): NOT a crash. Journal:
  session opened for miro -> 0.5 s later "systemd-logind: Power key pressed short. Powering off...".
  Greeter (phrog) exits, ~5 s blank handover, user presses power to wake the screen, nobody holds the
  power-key inhibitor yet -> logind default HandlePowerKey=poweroff. Fix: device-a52q
  usr/lib/systemd/logind.conf.d/50-power-key.conf HandlePowerKey=ignore (+LongPress) - Phosh handles the
  button. Applied live (/etc copy); logind reports HandlePowerKey "ignore". sunfish has the same gap.

## Camera audit (2026-09-27)
Earlier "WORKS" verdicts used frame mean/std only. Those numbers were the same for garbage and for
black frames. New pass/fail check: the sensor's colour-bar test pattern (V4L2_CID_TEST_PATTERN on the
subdev), captured RAW through camss with libcamera `cam -s role=raw`. Rows must repeat (bars) and all
rows must be filled.
- libcamera (0.7.2, simple pipeline + soft ISP) lists 4 cameras (UW, front, depth, main) and streams all 4.
  Macro has no camss link (UW/macro share CSIPHY3 via the gpio66 switch).
- Test pattern: UW s5k3l6, main s5kgw1p (C-PHY), depth gc5035 = clean. Front imx616 = BROKEN
  since the first capture: only ~1478/2448 rows are written, and bars are scrambled row to row.
- Root cause (front): the vendor OP PLL drives the link at 2056 Mbps/lane (link-freq 1028 MHz). Halving it
  live (0x030E/0x030F 0x0101 -> 0x0081, 1032 Mbps/lane) gives a clean full frame. 30 fps still fits.
  Fix: imx616_modes.h OPPLL_MPY 0x0081, LINK_FREQ 516 MHz (driver + DT).
- imx616 PIXEL_RATE was 822.4 MHz (derived from the link). The real VT rate is 24/4*237/5*2 = 568.8 MHz
  (7536*2514/568.8M = 30.0 fps, as measured). A wrong value gives wrong libcamera exposure times.
- No camera had DT orientation/rotation -> libcamera "Failed to retrieve the camera location".
  Downstream (atoll-sec-a52q overlay r06) roll: rear 90, front 270. Set orientation (0 front, 1 back)
  and rotation 270 for all (sunfish convention: stock roll 90 -> rotation 270). Front rotation NOT yet
  checked by eye.
- Rear frames are pure black level (16/255) because the phone lies face-up. Real-scene AE/exposure is
  NOT verified yet.
- The test UKI is removed after 10 min by dev-rescue.service unless /run/dev-alive exists.
- Result (test kernel 0.26.0927.2 + sysext modules): libcamera lists 5 cameras with front/back
  location. Test pattern clean on all 5, incl. macro through the video-mux and UW again after macro
  (lanes 2 -> 4 restored). gpio66 = high for macro, low for UW.
- Macro: gpio-mux (tlmm 66) + video-mux in DT; camss follows the enabled link through the mux, stops its
  s_stream walk at the first non-camss subdev, and takes the lane count from the active sensor's endpoint.
- Suspend: rtcwake 20 s OK after the smp2p_sleepstate bit change (bit now from DT, 12) and the qcom-wdt
  inline. ADSP/CDSP/modem running, accel/light OK after resume.
- OPEN (power): camss powers a pipeline while its video node is OPEN (v4l2_pipeline_pm_get in
  video_open). The greeter's WirePlumber (libcamera monitor) keeps /dev/video0 open, so after the first
  capture CSIPHY/CSID/IFE clocks + TITAN_TOP GDSC stay on until reboot. Moving pm_get/put to
  start/stop_streaming fixed that, but then CCI runtime suspend logged "cam_cc_camnoc_axi_clk status
  stuck at 'on'" and a later depth (vfe_lite) capture came back partial/zero. Reverted. Needs a proper
  camss power-down (VFE/bus halt before clocks off) before it can be done.

## Camera image-quality pass (2026-09-27, stock CamX decode)
Per-camera reports: cameras/{main,uw,front,depth,macro}/REPORT.md; integration: cameras/INTEGRATION-*.md.
Stock Samsung A525FXXUAFXL2 camera blobs (vendor/lib/camera: tuned.*.bin Chromatix, sensormodule, sensor .so) decoded.
- Root causes of bad images: front imx616 reported GRBG but is RGGB (colour cast); gc5035 digital gain stuck at ~16x
  (noise/banding) + broken gain codes + wrong binned line length; s5kgw1p gain range/default wrong, stream-on
  cleared flip reg; no per-sensor tuning (all on uncalibrated.yaml); no LSC in soft ISP (UW corners need 5.66x).
- camss: sensor rmmod/insmod re-registered media dev + duplicated links -> libcamera saw no cameras. Fixed
  (skip register when registered, skip existing links).
- Kernel (test UKI 0.26.0927.3): all driver fixes, new modes (main 2000x1128 <=120fps, UW 2000x1500, front
  1632x1224), s5kgw1p get_selection, AK7374 VCM on i2c9 + lens-focus (range 301 inf..759 macro from EEPROM),
  front EEPROM at24 @9-0051, macro DT label -> "gc5035_macro" own tuning, front rotation 90 (not eye-checked).
- libcamera 0.7.2-1+a52q1 (patches cameras/libcamera/patches 0001-0013: sensor helpers, GPU soft-ISP LSC, AGC
  frame-length-first, AWB persist, softisp AF from sunfish, 5 tuning yamls with LSC). Installed via sysext
  (/var/lib/extensions/a52qdev); all 5 cameras load their own yaml and stream.
- NOT verified: any real-scene image (phone faced desk/dark the whole session); AF sharpness sweep; CCM on colour target.
- FIXED (libcamera +a52q2, patches 0014-0016): mode choice by aspect ratio, centred GPU crop, output height rounded to 4 (1000x750 hang). Known issues:
  OIS (STM32G @i2c10 0x62) not driven; full-res 64/32 MP needs proprietary remosaic.
- Phone crashed once (RCU stall CPU7) ~10 s after reading /sys/kernel/debug/gpio - avoid that file.

## OIS kernel driver written, NOT yet hardware-tested (2026-09-27, phone unreachable this session)
Phone was disconnected the whole session (only the two sunfish usbnet gadgets were on the bus) -
no live testing was possible or attempted. Did offline prep only, all build-verified but zero
on-device verification.
- `drivers/media/i2c/a52q-ois-mcu.c` (in ~/src/linux-sm7125, obs/sm7125 branch, uncommitted like the
  other WIP camera changes there): real i2c_driver for the STM32G OIS MCU, ported register-for-register
  from cam_ois_init()/cam_ois_set_ois_mode() in the downstream cam_ois_mcu_stm32g.c (CONFIG_SEC_A52Q_PROJECT
  branches specifically - gyro orientation {0,1,0}, tele pole {0,0}, angle comp 0x06815 53F, gyro scale
  factor 114 - all cross-checked against the C source, not just against oisproto.py). Same register set
  oisproto.py's WRITABLE allowlist uses.
  Builds clean (`make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- M=drivers/media/i2c W=1 modules`,
  zero warnings, modpost resolves all symbols, vermagic matches the running 6.14.7-sm7125+). Config:
  CONFIG_VIDEO_A52Q_OIS_MCU=m added to a52q_defconfig + Kconfig + Makefile.
- Driver binds via i2c_device_id "a52q-ois-mcu" - matches cameras/ois/test/ois-harness.c's
  I2C_BOARD_INFO name exactly, so the existing harness (no DT change needed) should be able to load
  this real driver in place of manual oisproto.py pokes. NOT tried - needs the phone.
- Added `cam_main_eeprom` (`eeprom@50` on i2c9) to the a52q DTS - the main module OTP was documented in
  a comment but never actually instantiated (only the front one, @51, existed). Driver reads XGG/YGG
  wide-cal data through this via nvmem cells "cal-mark"/"xygg", but those cells don't exist in the DTS
  yet (only the parent eeprom node does) - devm_nvmem_cell_get() fails gracefully to NULL until they're
  added, so first test runs will skip wide-cal (safe, just suboptimal, matches oisproto.py's own EEPROM
  fallback path).
- KNOWN GAP, not a blocker: gyro offset (XGZERO/YGZERO) is hardcoded to 0 - the real value comes from
  EFS FactoryApp/camera_ois_gyro_cal on the stock phone, never extracted. Servo will run without gyro
  bias compensation until that's pulled (see oisproto.py gyro_offset() for the exact conversion once
  the real EFS string is in hand).
- Found and fixed 96 root-owned build artifacts (.o/.ko/.cmd files, chown'd back) blocking the M=
  module build in drivers/media/i2c/ - leftover from an earlier sudo build. Unrelated to this driver,
  needed clearing to link-test it.
- NEXT (needs phone): load a52q-ois-mcu.ko against the test harness (rmmod any stale harness state
  first per the harness's own comment), confirm probe succeeds, then oisproto.py-style verification:
  read back registers after android_init()+set_mode(1), confirm hall position moves (0x0082/0x0094..9c),
  confirm servo off (0x0000=0x00) actually stops movement. Do NOT skip the harness step and wire the
  real DT node first - no live confirmation the register sequence produces a moving lens yet.
- Also fixed a much bigger tree-wide instance of the same root-ownership problem: 12023 files under
  ~/src/linux-sm7125 were root-owned (an earlier sudo build, scope unknown), blocking `make dtbs` too.
  `sudo chown -R` the whole tree. If a future `sudo make`/OBS-style build happens again, expect this
  to recur - chown after, don't dig into why each time.

## CORRECTION: Type-C CC role detection was already finished, DEBUG.md was just stale (2026-09-27)
The 2026-09-26 note above ("Type-C role detection... is not written yet") was wrong by the time this
session started - drivers/usb/typec/sm5714-cc.c (commit da4859d32) and the DT wiring in
sm7125-samsung-common.dtsi (&i2c11/typec@33, interrupts-extended tlmm 104, vbus-supply
vreg_usb_otg_vbus, usb-role-switch -> &usb_1_dwc3, usb_1_dwc3 has role-switch-default-mode =
"peripheral") are BOTH already committed and complete. Verified by rebuilding the full DTB clean
(no dtc warnings, all phandles resolve) - not just reading the source. Not tested on-device (no
cable, no phone this session) but there is no remaining code/DT gap; whatever needs doing next here
is live verification (plug an OTG cable, confirm host-mode switch), not more driver work. Don't
redo this from scratch in a future session - check git log for drivers/usb/typec/sm5714-cc.c first.

## Error sweep (2026-09-28, test UKI 0.26.0927.10)
- FIXED (profile): qcom-modem-setup exit 4 = no SIM (both slots no-atr). device-a52q drop-in
  qcom-modem-setup.service.d/10-no-sim.conf SuccessExitStatus=4 (+ live copy in /etc). System "running".
- FIXED (module, not yet on-device verified): i2c-qcom-cci system sleep -> pm_runtime_force_suspend/resume.
  Old cci_resume enabled camnoc_axi with TITAN_TOP GDSC off -> "stuck at off" -16 WARN on every resume.
  Separate pre-existing bug: cci_probe enables clocks before pm_runtime_enable -> insmod fails when GDSC off.
- FIXED (module, not verified): q6asm drops successful basic-rsp acks for WRITE_V2/READ_V2/EOS (0x10dac spam);
  wcd938x-sdw of_property_present for qcom,tx-port-mapping (boot OF warning).
- OPEN: after an s2idle resume ALL RX playback (speaker QUIN_MI2S + headphone SWR) wedges at hw_ptr=1024,
  capture fine -> DSP-side q6asm/AFE RX problem, not tas2562. Memory_map_regions -22 / CLOSE 10bcd timeout
  are its cascade. Needs fresh boot + 1 rtcwake to bisect.
- Benign: dsi_err status=5 (TIMEOUT|FIFO latched at resume, no underflow), dwc3 "HS-PHY not in L2" (gadget
  connected), aux_bridge -ENODEV (no DP on a52q), zap load fail in initrd (GPU inits later), initrd udev
  .ko misses, OSK start race (works), podman/PAM/portal noise.
- Shared-recipe defect (not edited): cmdline gets empty usrhash= + two image_policy= (image-immutable +
  device-qcom) -> /usr dissected "unprotected", veritysetup-generator error.
- CORRECTION: the ~70 min "USB gone" outage was NOT a hang - the phone was locked and idle-suspended (s2idle
  drops the USB gadget; power button brings it back; long-standing). Live rmmod/insmod of i2c_qcom_cci did leave
  both CCIs failing probe -16 (probe enables clocks before pm_runtime_enable) -> cameras dead until reboot.
  Don't hot-reload CCI; test via reboot. And 172.16.42.1 outside netns a52 is the PIXEL 4a — only `ssh a52r`.

## Consolidated test kernel (2026-09-28 evening): UKI a52qtest_0.26.0928.1 = 6.14.7-sm7125 #10
- ROOT CAUSE of "speakers EIO" and "cameras dead": the dev sysext held a stale/partial module set. The #8
  snd-soc-sm8250.ko predated ba923ef48 (no QUINARY_MI2S_RX sysclk -> no BCLK -> no WRITE_DONE -> EIO / stuck hw_ptr),
  and the 2026-09-27 17:55 sysext rebuild dropped s2mpb03-regulator, at24, video-mux, sm5714-cc and the patched
  libcamera (sensors deferred on the S2MPB03 LDOs). Fix: full `modules_install` of one build (784 modules, .ko.zst,
  same names as base) as /var/lib/extensions/a52qdev/usr/lib/modules/6.14.7-sm7125 (no updates/ any more; backup of
  the old dir in /var/lib/a52qdev-modules-backup), libcamera 0.7.2-1+a52q2 debs in cameras/libcamera/debs/ and
  unpacked into the sysext. Recipe: sysext-dev-README.md. RULE: kernel image and modules must come from ONE build.
- Kernel #10 also carries: i2c-qcom-cci force_suspend/resume, q6asm ack handling, wcd938x-sdw of_property_present,
  ath10k chan-info freq-0 warn -> dbg (CONFIG_ATH10K=y, needed the image).
- Verified on #10: boot 0 WARNING/traces, devices_deferred empty, all sensors/ak7375/at24/sm5714-cc bound, speaker
  plays; earlier on #8+fresh modules: speaker/headphone OK incl. stream open across rtcwake.
- USB net: a52q-usbnet-inhibit.service (sleep/idle inhibitor while UDC configured) + pinned gadget host MAC
  02:a5:2c:00:00:01; laptop ~/.local/bin/a52-netns finds the A52 by that MAC. Phone idle-suspend was the cause of
  the long-standing "phone vanished from USB" (gsd-power 900 s, SSH isn't activity).
- Wi-Fi at greeter "disconnected" is expected: connection <home-ssid> has permissions=user:mito.
- Suspend-safe testing: never hold an ssh across rtcwake (it hangs forever); run rtcwake via systemd-run and poll.

## State at end of 2026-09-28/29 sweep (phone unplugged, offline from here)
- Phone last seen: test UKI a52qtest_0.26.0929.2 (CCI CAMNOC icc vote build) booted; its 7-round stress loop
  results were LOST (phone unplugged mid-run) -> the icc-vote fix is NOT verified. Fallback-good kernel:
  0.26.0928.2 (#10) is gone from the ESP (uki-test keeps one test UKI); stock UKI is the fallback.
- Fixed + verified on device: modem-setup no-SIM; USB net always reachable (inhibitor + pinned MAC + MAC-matching
  a52-netns); speaker/headphone/mic (stale snd-soc-sm8250 module); cameras (missing modules + libcamera
  +a52q3 with patch 0017 = video node open only while acquired -> camss suspended when idle; 5/5 on all 5 cams
  after 8 s2idle cycles); q6asm ENOTREADY/ack spam; wcd938x tx-port-mapping warning; ath10k chan-info spam;
  sm5714-cc resume IRQ storm (1988x "SE resources -13"; disable_irq across sleep).
- Unverified: CCI CAMNOC interconnect vote (i2c-qcom-cci.c + &cci0/&cci1 interconnects + binding) for the
  order-dependent post-resume "camnoc_axi stuck at on" WARN + 0-frame captures (resume->cam1->cam3).
  ath10k freq-0-only demotion refined offline (warns again for nonzero bad freqs) — not yet on device.
- Current tree built 2026-09-29 10:48 (vmlinuz.efi + modules + dtbs, make rc 0). Next with phone: modules_install
  -> replace sysext modules dir, uki-test.sh 0.26.0929.3, reboot, run the stress loop in scratchpad stress.sh
  (count frames with grep -c "seq:").
- Open, needs owner: /home full (mito.home 48.4G LUKS homed image fills the 50G partition, rebalance off) ->
  podman system units fail -> system "degraded". Shared recipes: empty usrhash= + duplicate image_policy= ->
  /usr dissected unprotected. Kernel fixes live only in test UKIs + sysext; permanent = commit + OBS build.
- Session patches: patches/2026-09-28-error-sweep/.

## VERIFIED 2026-09-29: test UKI a52qtest_0.26.0929.3 = 6.14.7-sm7125 #11 (blessed)
- Image + DTB + 784 modules from one build (modules_install in sysext; backup of previous in /var/lib/a52qdev-modules-backup3).
- CCI CAMNOC icc vote fix VERIFIED: 6-round on-phone stress (/var/tmp/stress.sh via systemd-run: rtcwake 15 s, captures
  in orders incl. cam1->cam3 and cam1 alone, all 5 cams) -> every capture 5/5, stuck-at=0, WARNING=0, SMMU faults=0,
  "SE resources"=0.
- Also OK: speaker/mic, BT powered, usbnet inhibitor held, camss suspended when idle (no /dev/video holder),
  no ath10k chan-info lines, devices_deferred empty.
- Remaining dmesg err lines, all known: dwc3 "HS-PHY not in L2" (gadget connected during suspend), zap/gpu init in
  initrd (GPU inits later), WirePlumber MM1 probe (Memory_map_regions / no backend DAIs, once at boot), aux_bridge
  -ENODEV (no DP), veritysetup-generator (shared-recipe cmdline bug), bpf-restrict-fs.
- System "degraded" only because of podman units: /home full (owner decision on shrinking mito.home).

## 2026-09-29 afternoon: login bug, factory reset, restore
- Login "bounces back": /home 100% full (LUKS homed image mito.home fills the partition + podman graphroot on /home)
  -> homed "Not enough disk space for home mito". Also the clock was 1970: a52q-rtc-offset.service was never
  enabled (profile preset not applied to units that arrive via sysext) and rtc-offset.sh `restore` exited 1
  (`[ ] && date` as last command) -> fixed with if/fi in the profile.
- Owner asked for a clean state; build host (192.168.100.104 / <build-host>) down, so instead: via U-Boot UMS,
  removed the test UKI, wipefs + deleted inner-GPT root (p8) + home (p9) -> first boot re-created them
  (repart). Nested GPT backup: backup-pre-reflash-20260929/nested-gpt.bin. UMS exits via `eject /dev/sda`.
- After reset no user existed -> phrog login "error please try again" (greetd: no session under configuration).
  Created user **miro** (PIN 1234, --storage=directory, uid 60466; "mito" was an old typo, deleted).
- Stock kernel froze once while opening GNOME Settings (no pstore). Restored dev stack from
  backup-pre-reflash-20260929/phone-state.tar (sysext: 784 #11 modules + libcamera +a52q3) + current profile
  /usr, `systemctl preset` of the device preset, UKI a52qtest_0.26.0929.4 (#11). Host key re-pinned.
- s5kgw1p probe once failed at boot: CCI "master 0 queue 0 timeout", chip id read -110 -> no /dev/media (camss
  waits for all sensors). Next boot OK. Intermittent; candidate fix = retry the chip-id read in probe.
- State: running, cameras 5/5, owner confirmed camera works.
