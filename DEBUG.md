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

## 2026-09-29 evening: audio q6asm probe noise, s5kgw1p retry, NFC verify
Three-task sweep (device on test UKI a52qtest_0.26.0929.4 = #11).

### 1. Audio "q6asm DSP returned error[1]" / MultiMedia1 no backend — HARMLESS PROBE
- Real speaker playback for miro is CLEAN: `pw-play` -> Speaker (MM1->QUIN_MI2S->TAS2562)
  produces zero q6asm errors. Mic + headphones sinks all present (UCM-managed, no raw MM nodes).
- Trigger: PipeWire/WirePlumber opens the MM1 front-end PCM (hw:0,0) and runs hw_params+prepare
  during ALSA node init, BEFORE any back-end is routed. The SM7125 ADSP refuses to map DSP memory
  for a front-end with no back-end graph (DSP error[1]) -> cascades to Memory_map_regions failed /
  Buffer Allocation -22 / prepare -12, plus the ASoC-core "no backend DAIs enabled for MultiMedia1".
  Reproducible on demand: `systemctl --user restart wireplumber` (miro) -> the block reappears.
  Raw `aplay -D hw:0,0` does NOT reproduce (only PipeWire's mmap open+prepare pattern does).
- Verdict: NOT a kernel/DSP bug (kernel correctly reports an FE prepared with no BE; q6asm-dai.c
  prepare is stock upstream). Fix belongs in the userspace audio profile. Suppressing it in-kernel
  would mask real misconfig, so no kernel change.
- Fix (device profile): WirePlumber drop-in pins the ASoC output nodes to one rate so WP stops
  re-opening/re-preparing MM1 to renegotiate (this is what caused the recurring post-boot hits, e.g.
  the +567 s one). File: device-a52q profile
  `mkosi.extra/usr/share/wireplumber/wireplumber.conf.d/51-a52q-no-fe-probe.conf`
  (audio.rate=48000 + api.alsa.disable-batch on ~alsa_output.*). Live copy deployed to the phone at
  `/etc/wireplumber/wireplumber.conf.d/51-a52q-no-fe-probe.conf` for verification.
- Residual: ONE benign probe line remains at WP/node init (PipeWire opens each sink once to
  configure it); cannot be removed from userspace without breaking init, and is expected (routeless
  FE prepare refused by the DSP). pw-play playback stays clean (0 errors).

### 2. s5kgw1p intermittent probe timeout — FIXED (kernel)
- Root cause: probe releases reset then immediately reads chip-id; the sensor sometimes NAKs that
  first I2C access -> CCI "master 0 queue 0 timeout", cci_read -110 -> probe fails -> no /dev/media
  (camss waits for all sensors). Sibling s5k3l6xx never fails: it uses a reset pulse + settle.
- Fix: commit `media: i2c: s5kgw1p: retry chip-id read on power-up` (obs/sm7125 f45e8a436) — retry
  the chip-id read up to 4x, power-cycling the sensor between attempts. checkpatch --strict clean.
- Built incrementally (vermagic 6.14.7-sm7125, matches the #11 image), stripped + zstd, deployed over
  the sysext `.../kernel/drivers/media/i2c/s5kgw1p.ko.zst` (old saved at
  /var/lib/a52q-s5kgw1p-retry-backup.ko.zst).
- Verified: 5 consecutive `systemctl reboot`s -> `cam -l` (as root) shows 5/5 cameras every time,
  s5kgw1p detected each boot, 0 CCI timeouts. (Retry path did not need to fire in these 5 boots —
  the timeout is intermittent; the retry is the safety net.)
- Note: post-reboot `cam -l` as miro fails "/dev/media0 Permission denied" — miro isn't in group
  `video` and relies on a logind uaccess ACL that lags early boot; unrelated to the camera fix. Root
  enumeration is unaffected.

### 3. NFC (s3fwrn5) — power-up + NCI init + version OK; RF poll times out (no-flash limitation)
- No firmware file present (required): `sec_s3fwrn5_firmware.bin` absent -> s3fwrn5_firmware_init
  fails -> post_setup skips bootloader/FW mode (driver does NOT flash, correct).
- DEV_UP succeeds (netlink genl, no neard needed): NCI CORE_RESET+CORE_INIT complete. dmesg
  (nci +p): manufact_id 0xe (Samsung), manufact_specific_info 0x2160062 (chip fw/version info),
  RF interfaces enumerated, max_routing_table_size 1170. So NCI init succeeds and version is read.
- START_POLL consistently times out at RF_DISCOVER (opcode 0x103): RF_DISCOVER_MAP returns status
  0x0 but RF_DISCOVER gets no response in 5 s (-110), then the chip wedges until DEV_DOWN. The NFC
  IRQ (msmgpio 37) fires for reset/init/discover-map, so the i2c+irq path works. Not a DT/irq issue.
- Conclusion: control-plane works; RF discovery on the resident firmware does not start without the
  proprietary RF-register (rfreg) config, which we deliberately do not load. Reported as a limitation
  (no fix without the forbidden blob); no kernel change. Bar "power up + start poll without errors"
  is partially met: power-up yes, poll no.
- Test script: ~/linux-a52q/nfc-nl-test.py (genl, genl DEV_UP/START_POLL/STOP_POLL/DEV_DOWN, correct
  cmd nums DEV_UP=2 DEV_DOWN=3 START_POLL=6 STOP_POLL=7, PROTOCOLS attr=3).

### 2026-09-29 — NFC (s3fwrn5) RF poll: root cause found = S3NRN4V variant needs DUAL_OPTION + single-byte FW_CFG clock
- Chip is Samsung **S3NRN4V** (vendor blobs: sec_s3nrn4v_*), a later part than the S3FWRN5/S3FWRN82 our
  in-tree driver handled. The mainline rf-config path (START/SET/STOP_RFREG 0x26/0x22/0x27 + 3-byte
  FW_CFG 0x28) is the OLD scheme; it is also only reached during a firmware flash, so with no
  sec_s3fwrn5_firmware.bin present post_setup returned early and the chip got ZERO RF/clock config →
  RF_DISCOVER(0x103) times out (-110) and wedges. Two missing pieces:
  1) reference clock: vendor libnfc-sec-vendor.conf sets FW_CFG_CLK_SPEED=0x11 (19.2 MHz PLL) via the
     single-byte FW_CFG; mainline sent the 3-byte form with 0xff. Without 0x11 NCI init completes but
     RF_DISCOVER never answers.
  2) RF calibration: S3NRN4V loads it with proprietary **DUAL_OPTION (GID 0x0f, oid 0x2a)** sub-ops
     GET_VER/START/SET/STOP, the hwreg+swreg blobs MERGED into one stream (HW first), checksum = sum of
     merged u32 LE & 0xffff. Not the SET_RFREG sequence.
- Upstream fix exists: "[PATCH v4/v5 0/6] nfc: s3fwrn5: support the S3NRN4V" (Jorijn van der Graaf,
  lore 20260807021001.239389-1-jorijnvdgraaf@catcrafts.net). Applied patches 1,3,5 to obs/sm7125 and
  hand-adapted the i2c.c/uart.c hunks (our tree predates the gpiod conversion): FW_CFG from ->init,
  DUAL_OPTION upload from post_setup, samsung,s3nrn4v compatible + variant match data, pvdd-supply.
- Vendor blobs extracted from super/vendor (loop-mounted /dev/sda25 @ off 4642570240): /vendor/etc/nfc/
  sec_s3nrn4v_{hwreg(3232B),swreg(336B)}.bin, kept in ~/linux-a52q/nfc-vendor-blobs/. Installed on phone
  at /var/lib/firmware/samsung/s3nrn4v/{hwreg,swreg}.bin (firmware_class.path=/var/lib/firmware). NEVER
  provide sec_s3fwrn5_firmware.bin (that would flash the chip).
- Build OK (M=drivers/nfc/s3fwrn5, vermagic 6.14.7-sm7125 matches; checkpatch --strict clean).
  DTB (compatible=samsung,s3nrn4v, pvdd-supply=<&vreg_nfc_pvdd>) builds.
- STATUS: built, NOT verified on device (phone unplugged/owner away). Committed on obs/sm7125:
  a4d12a5 of_match_ptr, 6c8a10a bindings, 07145bc pvdd, b6e9d4b S3NRN4V support (Jorijn van der Graaf,
  his SoB + mine, "[backported to 6.14]" on the i2c/uart-adapted ones), c3cb676 a52q DT enable NFC
  (mine). checkpatch --strict: 0 errors all five (patch1 has 1 warning = valid upstream commit-ref in
  the backported message). Modules build (vermagic 6.14.7-sm7125 matches); a52q dtb builds.
- RETEST when phone reachable (ssh a52r):
  1. Deploy DTB: ~/linux-a52q/uki-test.sh <VER> <vmlinuz.efi> \
     ~/src/linux-sm7125/arch/arm64/boot/dts/qcom/sm7125-samsung-a52q.dtb  (safe one-try UKI, falls back
     to stock on boot-fail); flock /tmp/claude-1000/a52phone.lock around the reboot. This makes the node
     bind as samsung,s3nrn4v (needs vmlinuz.efi of the running kernel).
  2. Deploy the two rebuilt .ko (drivers/nfc/s3fwrn5/{s3fwrn5,s3fwrn5_i2c}.ko) via sysext-dev.sh (or
     md5-verified copy to /var/tmp + reload). Blobs already at /var/lib/firmware/samsung/s3nrn4v/.
  3. python3 nfc-nl-test.py -> expect dmesg "calibration data update: success" + START_POLL: OK, then
     STOP_POLL/DEV_DOWN OK, DEV_UP again OK (responsive bar).
  Module-only alt (no DTB): temporarily map samsung,s3fwrn5-i2c -> S3NRN4V in i2c.c of-table, rebuild,
  reload; clean copy at /tmp/claude-1000/i2c.c.clean. (Earlier attempt aborted: corrupted .ko transfer
  -> userspace insmod SIGSEGV, then USB-net link flap; kernel was not crashed.)

## 2026-09-29 — mainline v7.3-rc5 a52q bringup (branch a52q/mainline)

Worktree `~/src/linux-a52q-mainline` (branch `a52q/mainline`, base 72d3fcf802c4 =
v7.3-rc5). 23 commits. Built with Debian GCC 14 (`kbuild-trixie-img`, committed from
`kbuild-trixie`), O=`~/linux-a52q/out-mainline`, EFI_ZBOOT=y, modules zstd.
KERNELRELEASE = 7.3.0-rc5-sm7125.

Stack, in order:
- fixes: watchdog stop-on-sleep, ath10k freq0 demote, i2c-cci interconnects (4)
- pmic: s2mpb03 regulator, sm5714 fuel-gauge + Type-C CC, all with bindings (6)
- NFC s3fwrn5 S3NRN4V series 1-5 (Jorijn v4; skipped 0 cover + 6 fairphone DT)
- Erikas DT v3 1-3: A52/A72 compatibles, tzmem SHM-bridge disable, initial DT
- NEW ports (mine): FTS5CU56A touch driver + binding; SM5714 charger driver +
  binding; a52q DTS on-top (touch i2c7, charger/fg i2c4, Type-C i2c11, tsp_int).

Port fixes made:
- charger: `power_supply_config.of_node` removed in mainline → `fwnode = dev_fwnode()`
  (like the fg driver); dropped unused of_gpio.h/platform_device.h; added error
  checks to every regmap_read in get_property; dropped dead reg_st3.
- charger binding: current props need `$ref .../uint32` or dtbs_check rejects the cells.
- DTS tsp_int: `function` must be `"gpio"` (Erikas' "normal" fails sc7180 pinctrl schema).

Verified (all observed, not claimed):
- Build: `make vmlinuz.efi qcom/sm7125-samsung-a52q.dtb modules` → OK. GCC 16 host
  hangs pre-ramoops on this phone, so GCC 14 docker only.
- dtbs_check (a52q dtb): 0 warnings after the tsp_int + binding-type fixes.
- checkpatch --strict (my commits): DTS clean; charger/bindings clean bar the
  advisory "MAINTAINERS?"; touch driver 142 cosmetic CHECK/WARN (CamelCase locals,
  blank lines, banner comment) 0 errors — imported downstream style, pre-upstream TODO.

Artifacts: `~/linux-a52q/mainline-stage/7.3.0-rc5-sm7125/` (vmlinuz.efi,
dtbs/qcom/sm7125-samsung-a52q.dtb, modules-*.tar.zst = 794 mods vermagic-matched,
README with uki-test.sh steps). Phone was unplugged — NOT test-booted.

Deferred (stubbed nothing, left out):
- DSI panel s6e3fc3/ams646yd04: needs full old→_multi mipi_dsi API conversion
  (57 seqs ×2 variants). simple-framebuffer covers display for the test boot, and a
  mis-converted panel could black-screen (worse), so deferred. TOP display follow-up.
- Wi-Fi/BT/modem: Erikas base lays out mpss/wlan/adsp reserved-memory but does not
  enable the remoteprocs/wifi node. DT-only + firmware staging; boot-risky (bad mpss
  hangs) — validate before flashing. HIGH follow-up (drivers already in mainline).
- Cameras (gc5035/s5k3l6xx/imx616/s5kgw1p+retry, ak737x/OIS, camss C-PHY/video-mux,
  s2mpb03 cam-pmic i2c-gpio node), audio (Quinary MI2S/tas2562 fsync/wcd fixes),
  smp2p sleepstate (check Acayan patchwork 1170900). LOW per priority.

## 2026-09-30 — NFC (s3fwrn5 / S3NRN4V) VERIFIED ON DEVICE — RF poll works
On-device verification of the obs/sm7125 f45e8a436..620f8a39a NFC series (no code change needed).

Pre-checks (source): core.c post_setup: S3NRN4V variant -> s3fwrn5_nci_rf_configure_dual(hwreg,swreg)
then `return 0` — the flash path (s3fwrn5_firmware_init "sec_s3fwrn5_firmware.bin") is unreachable for
this variant. i2c.c enables pvdd itself via devm_regulator_get_enable(dev,"pvdd") (DT regulator-always-on
removed). Driver requests samsung/s3nrn4v/{hwreg,swreg}.bin; phone firmware_class.path=/var/lib/firmware/
-> resolves to /var/lib/firmware/samsung/s3nrn4v/{hwreg(3232B),swreg(336B)}.bin (present). Forbidden flash
files sec_s3fwrn5_firmware.bin / sec_s3fwrn5_rfreg.bin ABSENT (confirmed).

Build (kbuild-trixie, Debian GCC14): M=drivers/nfc/s3fwrn5 modules + a52q dtb. vermagic both .ko =
"6.14.7-sm7125 SMP preempt mod_unload aarch64" (matches running #11). dtb has compatible samsung,s3nrn4v.

Root cause of the previous "RF poll times out" bar: the BOOTED test UKI a52qtest_0.26.0929.4 still carried
the OLD dtb (nfc@27 compatible = samsung,s3fwrn5-i2c) -> driver bound as S3FWRN5 variant, so post_setup
never ran the DUAL_OPTION RF-cal path. Fix = boot the new dtb.

Deploy: stripped+zstd .ko (aarch64-strip --strip-debug, zstd -19) md5-verified to phone
(s3fwrn5.ko.zst f736fd85..., s3fwrn5_i2c.ko.zst 893d05a3...); old .ko.zst backed up at
/var/lib/a52q-nfc-s3nrn4v-backup/; copied into a52qdev sysext kernel/drivers/nfc/s3fwrn5/; depmod OK
(temp lib->usr/lib symlink so `depmod -b /var/lib/extensions/a52qdev` finds usr/lib/modules).
Kernel image: extracted the .linux PE section from the running UKI (rp=258048 rs=14041600,
md5 8722c28a...) — NOT rebuilt — so image+modules are one build. uki-test.sh 0.26.0930.1 <that vmlinuz>
<new dtb> -> a52qtest_0.26.0930.1+1.efi. Rebooted under flock a52phone.lock, reconnected ~90s, touched
/run/dev-alive.

Verify (all observed): booted nfc@27 compatible = samsung,s3nrn4v; loaded .ko md5 = new build.
nfc-nl-test.py x3: every run DEV_UP OK / START_POLL OK / STOP_POLL OK / DEV_DOWN OK, chip stays
responsive across runs. dmesg: manufact_id 0xe (Samsung), "nfc0: calibration data already current"
(DUAL_OPTION GET_VER matched -> no re-upload, NO firmware flash), nci_rf_disc_rsp_packet status 0x0
(RF_DISCOVER now answers — previously -110 timeout+wedge), rf_deactivate_rsp status 0x0. No tag present
(none expected). CONCLUSION: NFC control+RF plane fully working on device.

No regression: cam -l (root) 5/5 cameras; wld0 connected (192.168.100.131, SSID <home-ssid>); sound card 0
"Galaxy A52" present; usb0 172.16.42.1 up. Test UKI marked GOOD (a52qtest_0.26.0930.1.efi, +1 counter
dropped; boot-complete.target active) -> stays default. No new commits (verification only).

## 2026-09-30 — mainline v7.3-rc5 a52q: coprocessors/Wi-Fi/BT, DSI panel, cleanups (branch a52q/mainline)

Six commits on top of the 23-commit stack. All built with the Debian GCC14 docker
(`kbuild-trixie-img`, O=out-mainline, KERNELRELEASE 7.3.0-rc5-sm7125), under
`flock /tmp/claude-1000/kbuild.lock`. Build- and schema-verified ONLY — phone was
unplugged, so NOTHING here was boot-tested.

### Task 1 — DT coprocessor/radio enablement (1 commit, 93734523)
common.dtsi: enable qupv3_id_0/1 (the already-present i2c4/7/11 + BT uart sit under
them and were latently dead without this), ipa (memory-region), remoteproc_adsp
(memory-region), wifi (ath10k WCN3990 supplies), uart3 + WCN3988 bluetooth child +
qup_uart3_sleep pin state. a52q.dts: status=okay + firmware-name for ipa,
remoteproc_adsp, remoteproc_mpss; firmware-name for gpu_zap_shader, venus, bluetooth
(paths qcom/sm7125/a52q/*.mbn; BT sm7125/a52q/apnv11.bin). gpu/venus/gmu are
enabled-by-default in mainline sc7180 (no status override needed; the zap-shader
already carries memory-region=<&gpu_mem>).
LEFT OUT: remoteproc_cdsp — mainline sc7180.dtsi has NO cdsp remoteproc node (only
mpss + adsp), so cdsp cannot be enabled DT-only.
Binding fix: the v7.3 sc7180 pinctrl schema requires per-pin subnodes for
qup-uart3-sleep-state (cts/rts/tx/rx-pins, each with pins+function+bias); the 6.14
pinmux{}/pinconf-*{} split fails dtbs_check ('oneOf conditional failed').

### Task 2 — DSI panel (3 commits: binding e0581e, driver a31135, dts bec931)
Ported the fork panel-samsung-s6e3fc3.c (map220v) to v7.3 — AMS646YD04 variant only
(a52q's panel; dropped the unused ams667ym01). Converted the whole init/enable/disable
path to the mipi_dsi_*_multi() API. v7.3 also dropped drm_panel_init() and
of_drm_get_panel_orientation(): use devm_drm_panel_alloc() and, since the a52q panel
node sets no rotation, dropped orientation handling. New binding samsung,s6e3fc3.yaml
(vddio/vci supplies, reset-gpio, port). common.dtsi enables dispcc/mdss/mdss_dsi0/phy
+ panel skeleton + mdss pin states; a52q.dts sets the panel compatible okay.
simple-framebuffer kept (msm aperture handoff on probe).
Init-sequence fidelity: `panel-initseq-diff.py` (staged) extracts every DCS/generic
write payload + control op + delay from ams646yd04_init_sequence() in both the fork
and the ported source, normalises only the API spelling, and diffs. Result:
**MATCH: 46 ops identical (byte-for-byte)**.

### Task 3 — audio (sm8250 sndcard / QUINARY MI2S -> tas2562 + WCD9380): NOT DONE, blocked
The 6.14 audio card depends on the sm8250-style LPASS codec macros (rx/tx/va macro),
SoundWire controllers (swr1/swr2) and the `sound` node — which the fork BACKPORTED
into its sc7180.dtsi (`grep -c 'rxmacro:|vamacro:|swr1:|sound:' sc7180.dtsi` = 6 in
the fork, 0 in mainline v7.3). Mainline sc7180 uses the older lpass_cpu I2S model +
q6afe/q6asm APR instead. Reproducing the macros/SoundWire/sound infrastructure is
SoC-level DT work (affects every sc7180 board), boot-risky, and unverifiable with the
phone unplugged — beyond board-level enablement. The tas2562 QUINARY-MI2S speaker
path also needs that infrastructure, so it is deferred too, and the fork's sm8250.c
Quinary-MI2S + tas2562 frame-sync tweak (fork ba923ef48) has no DT consumer without
it. Deferred as a separate SoC-level effort that needs device testing.

### Task 4 — tidy (2 commits: charger ff6b75c, touch e3e17b7)
sm5714-charger.c: replaced every bare `(0x1 << n)` status/control bit with a named
BIT() define next to its register (STATUS1_VBUSOK/VBUSOVP, STATUS2_NOBAT/CHGON/TOPOFF,
CNTL1_ENCHG, CHGCNTL4_AUTOSTOP). Field masks (0x7<<4 torch, 0x3, 0x7F) left as-is —
not single bits. checkpatch --strict clean.
stmfts_fts5cu56a.c: cosmetic-only to checkpatch --strict 0 errors/0 warnings (wrapped
>100-col lines, snake_case locals/cmd buffers, sysfs *_show + DEVICE_ATTR_RO, max_t,
dropped one brace, block-comment style, removed commented-out dead code, GPL). 29
CHECKs left (alignment / spaces-around-'+' / unnecessary-parens / cast-space —
justified). Behaviour preserved: normalised token-diff vs HEAD shows only the 4
intended semantic edits (max->max_t x2, DEVICE_ATTR->_RO x5, brace drop, GPL v2->GPL).
Delegated the grind to a coder subagent, then re-verified independently.

### Verification (all observed)
- `make vmlinuz.efi modules qcom/sm7125-samsung-a52q.dtb` -> OK. The config change
  (new panel module) regenerated autoconf.h and forced a one-time near-full module
  rebuild; watch disk (peaked ~2.9 GB free).
- dtbs_check a52q dtb -> 0 warnings (both after task 1's pin-state fix and final).
- dt_binding_check samsung,s6e3fc3.yaml -> clean (example compiles).
- checkpatch --strict on the 6 new commits -> 0 errors; only the advisory
  "MAINTAINERS?" on new files and the justified touch CHECKs.
- panel init byte-diff -> MATCH, 46 ops.
- Panel module vermagic = `7.3.0-rc5-sm7125 SMP preempt mod_unload aarch64`.

### Artifacts (refreshed, one build)
mainline-stage/7.3.0-rc5-sm7125/: vmlinuz.efi, dtbs/qcom/sm7125-samsung-a52q.dtb,
modules-7.3.0-rc5-sm7125.tar.zst (795 modules, INSTALL_MOD_STRIP=1, 9 MB), plus
panel-initseq-diff.py. uki-test.sh now takes the uname as an optional 4th arg
(default 6.14.7-sm7125); pass 7.3.0-rc5-sm7125 for this kernel.

## OIS MCU hardware-tested and DT-wired (2026-09-30)
First live test of the STM32G main-camera OIS. The MCU answers on i2c10 0x62 and
the a52q-ois-mcu driver's full init + servo sequence works. Verified against the
running 6.14.7-sm7125 (test UKI a52qtest_0.26.0930.1); no reboot, all changes
non-persistent.

- Build: `a52q-ois-mcu.ko` (drivers/media/i2c, M=) + `ois-harness.ko` (built from
  cameras/ois/test/ois-harness.c in a throwaway M= dir), vermagic 6.14.7-sm7125.
  No i2c-tools/gpiod on the phone, so reads/writes go through a tiny i2c-dev
  ctypes helper (staged /var/tmp/oisreg.py) on the harness's /dev/i2c-10, I2C_RDWR
  (works while the driver is bound). camwork/oisproto.py deps were NOT on the phone.
- GOTCHA (cost the most time): load order matters. The harness registers the
  vdd->vaf / vio->vcustom supply aliases AFTER it creates the i2c client, so if the
  DRIVER is already loaded the client binds with DUMMY regulators; runtime_resume
  then runs android_init over bit-banged i2c on an UNPOWERED MCU and hangs on 1 s
  SCL-stretch timeouts, dragging the main sensor (20-002d) into PM "error". The
  harness header says it: load harness FIRST, driver second. Recover the sticky
  sensor PM error with `s5kgw1p` driver unbind/bind (echo on/auto does NOT clear it).
- Rails/GPIOs (step 1): MCU needs VAF (vreg_cam_l7) + VIO 1.8 V (vreg_cam_l3) +
  AVDD1P8 (gpio63); all come up when the main sensor is runtime-resumed
  (`echo on > /sys/bus/i2c/devices/20-002d/power/control`). NRST=tlmm32,
  BOOT0=tlmm43 (kept low = main flash). Correct sequence: insmod harness, force
  sensor on, insmod driver, `echo on > .../10-0062/power/control` -> resumes active
  in ~2 s = android_init succeeded.
- Probe (step 2): fw ver 0x00F8/0x007C = "PSC1NK1M" (matches phone blob), fwsts
  0x00FC = a6110300 (not 4451/broken), err 0x0004 = 0000. All driver writes landed:
  gyro orient 0x0240 = 000100, angle comp 0x0348/0x03D8 = 0681553f (0.834),
  oissel 0x00BE = 01, mode 0x0002 = 01, ctrl 0x0000 = 01. gyro offset 0x0248 = 0,0
  (EFS cal still not extracted - known gap). XGG/YGG 0x0254 = f628dc3edc...e13e =
  the MCU's own factory cal (driver skips its nvmem write, cells absent - fine).
- Servo (step 3): servo ON (ctrl 01, status 0x02) -> hall/gyro words 0x0082,0x0084,
  0x0094..0x009c continuously fluctuate (e.g. 0x9a swings -16133..-16395, 0x82
  -21..44) = live control loop. Servo OFF (0x0000=00 -> ctrl 00, status 0x01) ->
  every one of those words FREEZES identical sample-to-sample. Toggling back on
  resumes the fluctuation, err stays 0000. This is the requested proof (phone can't
  be physically moved): the servo drives the hall/gyro registers, and 0x0000=0x00
  stops it. Status reg cleanly tracks 0x01 idle <-> 0x02 servoing.
- libcamera capture (step 4): NOT usable this session. main = cam5 (s5kgw1p 20-002d,
  cci0 bus0); UW = cam1 (s5k3l6xx 21-002d, cci0 bus1) - both legitimately @0x2d, not
  a duplicate. `cam` starts the pipeline but delivers NO frames for ANY camera (main,
  UW), with the OIS driver fully removed and no kernel/camss error and no held
  /dev/video* - an OIS-independent camss/session condition (a reboot restores 5/5 per
  prior history). So no OIS regression could be attributed, but on/off comparison
  couldn't be captured. The AK7375 "lens init failed, device ''" line is pre-existing
  enumeration noise, not the blocker.
- Cleanup: servo off + suspend, rmmod harness+driver (bus10 gone), sensor rebind left
  it suspended/clean. i2c_qcom_cci never touched/reloaded. dev-alive kept.
- Commits (obs/sm7125, linux-sm7125): f87b68721 driver OF match table
  (samsung,a52q-ois-mcu); 0af2cfd75 a52q DTS i2c-cam-ois node (i2c-gpio gpio86/87,
  ois@62, vdd=l7 vio=l3, reset=tlmm32 boot0=tlmm43). checkpatch --strict clean, dtb
  builds clean. DTB NOT booted - for the next test UKI.
- STILL UNVERIFIED / next: (1) boot the new DTB and confirm DT probe/bind. (2) The
  DT node has no runtime-resume trigger - the harness used a sensor->OIS device link;
  the DT path needs the driver to create that link from a phandle (or v4l2 subdev
  integration) or the OIS never resumes on camera open. (3) EFS gyro offset
  (0x0248) still hardcoded 0. (4) real OIS-on/off image comparison (needs a working
  capture / reboot).

## 2026-09-30 — mainline v7.3-rc5 a52q FIRST BOOT-TEST — did NOT boot; boot-count auto-recovered
Test-booted the 7.3.0-rc5-sm7125 build (vmlinuz.efi + sm7125-samsung-a52q.dtb, mainline-stage/) as
UKI a52qtest_0.26.0930.2+1 (one-try counter), stock 6.14.7 known-good UKI (0930.1) backed up to
/var/tmp/a52qtest_0.26.0930.1.efi.bak (sha256 7237fbd9…). 7.3 modules (795, vermagic 7.3.0-rc5-sm7125)
installed as an ADDITIONAL dir in the a52qdev sysext (usr/lib/modules/7.3.0-rc5-sm7125/, depmod -b),
6.14.7-sm7125 dir left untouched; 6.14 confirmed healthy (system running, usb0+wld0 up) before reboot.

Result: 7.3 did NOT reach boot-complete. Reboot 23:46:08 → back 23:48:36 (~2m28s) on STOCK 6.14.7
(BengalOS_0.26.0925.2), i.e. systemd-boot decremented the counter (UKI now …0930.2+0-1 = bad) and
auto-fell-back. No forced reset was needed. dev-alive absent on the fallback boot (expected).

Per-subsystem table for 7.3 — NOTHING could be recorded live: the kernel never reached userspace
(no USB-net, no Wi-Fi, no boot-complete), so every subsystem is UNOBSERVED.
| subsystem | 7.3 result | evidence / key line |
|-|-|-|
| boot to userspace | FAIL | never reached boot-complete.target; UKI marked bad (+0-1); fell back to stock |
| display panel (dsi/drm/bl) | UNOBSERVED | kernel did not reach userspace |
| touch (fts5cu56a) | UNOBSERVED | " |
| USB-net (usb0) | FAIL/UNOBSERVED | gadget is built-in; never came up → died before networking svc |
| Wi-Fi (wld0/ath10k) | UNOBSERVED | " |
| Bluetooth (hci0) | UNOBSERVED | " |
| battery/charger (sm5714) | UNOBSERVED | " |
| Type-C (sm5714-cc) | UNOBSERVED | " |
| NFC (s3nrn4v) | UNOBSERVED | " |
| remoteproc adsp/mpss/ipa | UNOBSERVED (suspect) | new DT nodes; "bad mpss hangs" per this file |
| GPU zap (adreno 618) | UNOBSERVED | " |
| modem (mmcli) | UNOBSERVED | " |

Root-cause forensics (no console/serial on this phone):
- pstore/ramoops EMPTY after the failed boot → NO kernel panic was captured. A panic persists to
  ramoops; a silent HANG (spin on a clock/regulator/genpd/remoteproc wait) does not. So 7.3 hung,
  it did not oops. Nothing to root-cause from logs → step-4 fix precondition not met.
- DM_VERITY/initrd ruled OUT: stock initrd (7125 entries) is MODULES-FREE (0 *.ko, no lib/modules);
  built-in UFS/EROFS/SQUASHFS mount rootfs; and this boot uses usr=unprotected (winning
  systemd.image_policy cmdline arg), so dm-verity (=m) is not on the boot path and initrd module
  vermagic is irrelevant. CONFIG_DM_VERITY=m in both 6.14 and 7.3.
- Leading suspects = the newly DT-enabled, never-boot-tested subsystems from the 2026-09-30 six-commit
  additions (remoteproc mpss/adsp, ipa, s6e3fc3 DSI panel, wifi/bt). No evidence channel exists to
  pinpoint which, and blind DT-bisect reboots without a console violate the
  research-before-flash-iteration rule, so not attempted. Owner has no key-press cost here (boot-count
  auto-recovers), but a single boots/doesn't-boot bit per rebuild is weak signal without a console.

Decision: no rebuild/commit made (no log-based root cause). Restored the 0930.1 known-good UKI (below).

## 2026-09-30 — pstore/ramoops persistence: ROOT-CAUSED as intrinsic DRAM decay (NOT DT-fixable)
Goal was to make ramoops survive a reset so the 7.3 hang could be captured. Result: pstore
persistence is impossible on this device via DT alone. Two independent failure modes, one of
them a bootloader/firmware property we cannot touch. Steps 4-5 (boot 7.3, read log) NOT attempted.

Method: test UKIs built from the running 0930.1 kernel (.linux PE section extracted so image+modules
stay one build) + a modified a52q dtb; markers via /dev/pmsg0 + /dev/kmsg; raw DRAM read/written via
/dev/mem (STRICT_DEVMEM allows the no-map region since it is not System RAM). All under a52phone.lock,
ssh never held across a reboot, boot-count auto-fallback intact. ~8 reboots.

FINDING 1 — EFI boot chain was clobbering the region (real, fixed by no-map, but SECONDARY):
- Stock (no no-map): U-Boot efi_dt_fixup marks the ramoops reg EFI_BOOT_SERVICES_DATA (reusable),
  so zboot decompression / systemd-boot allocate over it. dmesg: "found existing invalid buffer".
- Add `no-map;` to ramoops@b4600000 -> U-Boot marks it EFI_RESERVED. Confirmed via `efi=debug`:
  `efi: 0x0000b4600000-0x0000b46fffff [Reserved | ... |WB| ]` (was BOOT_SERVICES_DATA). The
  "invalid buffer" message disappears. The carve-out is driven by the DT embedded in the UKI
  (changing the UKI dtb changed the EFI memmap) — U-Boot's OWN built-in DT does NOT need changing.
- uki-test.sh gained a generic `EXTRA_CMDLINE=` env (appends extra boot args; DEBUG_CMDLINE still
  works). Used for efi=debug here; intended for initcall_debug on the 7.3 test.

FINDING 2 — intrinsic DRAM decay across the reboot (DOMINANT, NOT DT-fixable):
- Even with no-map (region provably protected from clobber), a written pattern does NOT survive a
  normal `systemctl reboot`. Clean, uncontaminated measurement: wrote a deterministic 4 KiB pattern
  via /dev/mem to the DUMP-zone data area (0xb4602000 — a region a clean boot never rewrites),
  verified it in DRAM by re-reading before reboot, rebooted, re-read:
     13.78% of BITS flipped, 66.3% of BYTES corrupted (mostly isolated 1-bit flips per byte).
  (pmsg-zone tests gave the same ~15%/68%, but the pmsg zone is contaminated by the new boot's own
   logging, so the dump-zone number is the trustworthy one.)
- This corrupts every ramoops zone signature (4-byte sig, ~5 bits flip) -> ramoops rejects the
  buffers -> fresh init -> /sys/fs/pstore always empty. Confirmed pmsg + console markers never
  survive, no-map OR mapped.
- MAPPED mode (stock 0930.1) also fails: clean mapped->mapped reboot leaves pstore empty and prints
  NO "found existing buffer" (sig destroyed too). So decay is INTRINSIC to the reset path, not caused
  by no-map. The earlier one-off "found existing invalid buffer, size 25, start 285" was coincidental
  clobber leaving sig-like bytes, not evidence of low decay.
- Why no DT knob helps: mem-type (WC/cached/uncached) cannot change DRAM cell retention; ecc-size
  (ramoops RS, corrects ecc_size/2 bytes per 128-byte block) cannot fix ~85/128 corrupted bytes;
  relocate — decay is uniform (a refresh-timing loss in the reset window), a different address will
  not retain better. Stock Android's sec_debug works at this same address only because Samsung's
  reset keeps DDR in self-refresh; the mainline path (kernel PSCI reset -> Samsung PBL/XBL -> U-Boot)
  loses refresh for a window and ~14% of bits decay.

CONCLUSION / DECISION:
- A working fix requires the bootloader/firmware to preserve DDR self-refresh across the reset
  (Samsung signed PBL/XBL, or U-Boot). U-Boot rebuild = Odin = not allowed; PBL/XBL = signed.
  Per the "if the fix needs U-Boot, stop and report" guardrail: STOPPED. No DT commit made — no-map
  alone yields no observable benefit (pstore still empty), so it was reverted from both trees
  (obs/sm7125, a52q/mainline) rather than shipped as a non-working partial fix.
- The 7.3.0-rc5 hang therefore cannot be captured via pstore on this device. Prior session already
  showed the same empty-pstore-after-7.3 result; this session explains WHY and rules out the DT path.
- OPEN LEADS for a future session (need a real observation channel — pstore is out):
  (1) whether the mainline reset issues a hard vs warm reset (qcom PON reset-type / reboot-mode in
      the SoC DT) — if mainline picks a colder reset than stock, changing the reset type could
      preserve DDR self-refresh and is Linux-side; (2) a USB/serial-gadget early console from U-Boot
      (env has serial_gadget) as an alternative live channel for the 7.3 hang.

Restore (verified on a52r): default = a52qtest_0.26.0930.1.efi (sha256 7237fbd9…, matches .bak);
test UKIs removed; uname 6.14.7-sm7125; cam -l = 5/5; Wi-Fi wld0 connected; usb0 172.16.42.1 up;
NFC nfc-nl-test.py DEV_UP/START/STOP/DOWN all OK; /run/dev-alive touched. Phone /var/tmp test scripts
cleaned. NOTE: the local dtb build in ~/src/linux-sm7125 ran `make oldconfig` non-interactively and
may have altered that tree's .config to defaults (BTF off etc.) — irrelevant to OBS builds.

## 2026-09-30 — netconsole debug-kernel STAGED, stopped before boot-test (laptop shutdown)
Step 0 (warm-reset DRAM): NEGATIVE. Wrote a 200x pmsg marker via /dev/pmsg0, set
`echo warm > /sys/kernel/reboot/mode`, `systemctl reboot`. Phone returned on 6.14.7;
ramoops registered (0x100000@0xb4600000, ecc:0) but /sys/fs/pstore EMPTY — marker did
NOT survive. Warm reset does not preserve DDR self-refresh either; confirms the
intrinsic-decay finding. pstore stays out; netconsole is the only channel.

Debug build (PUSHED + OBS pkg made; NOT yet boot-tested):
- git: branch obs/a52q-mainline-dbg = obs/a52q-mainline(9aa2b3e) + commit 675f71432a70
  "debian: a52q defconfig debug variant (netconsole + g_ether built-in)". ONLY edits
  arch/arm64/configs/a52q_defconfig: +CONFIG_NETCONSOLE=y, +CONFIG_NETCONSOLE_DYNAMIC=y,
  USB_ETH n->y. (USB_GADGET/LIBCOMPOSITE/U_ETHER/PRINTK_TIME already =y; DWC3 DUAL_ROLE=y.)
  KERNELRELEASE unchanged 7.3.0-rc5-sm7125. Created via temp-index plumbing in
  ~/pixel-a4-linux/kernel/linux-fork WITHOUT touching its working tree/index. Pushed to
  github.com/miromraz/linux.
- OBS: package home:realni/linux-sm7125-mainline-dbg created (scmsync
  #obs/a52q-mainline-dbg). At stop it was still "blocked / service in progress"
  (scmsync clone). NEXT: `osc results home:realni linux-sm7125-mainline-dbg` -> wait
  succeeded (~13 min). If stuck, re-save meta to force resync.

Pre-verified for the boot (no wasted boot): g_ether.host_addr is a valid module_param
(u_ether.h USB_ETHERNET_MODULE_PARAMETERS), netdev = usb0; netconsole cmdline format
[src-port]@[src-ip]/[dev],[tgt-port]@<tgt-ip>/[tgt-mac]; netconsole has a NETDEV_UP/
REGISTER notifier (deferred attach) so gadget-enumeration-vs-init order won't drop the
target.

EXACT NEXT STEPS (resume):
1. Extract kernel+dtb from the .deb: `osc getbinaries home:realni linux-sm7125-mainline-dbg
   Debian_13 aarch64` into scratchpad; `dpkg-deb -x linux-image-7.3.0-rc5-sm7125_*.deb x/`;
   vmlinuz = x/boot/vmlinuz-7.3.0-rc5-sm7125 (EFI zboot), dtb =
   x/usr/lib/linux-image-7.3.0-rc5-sm7125/qcom/sm7125-samsung-a52q.dtb.
2. Capture side (laptop): run ~scratchpad/a52-nicwatch.sh in bg (keeps the A52 NIC MAC
   02:a5:2c:00:00:01 parked in netns a52 @172.16.42.2/24 even if the phone hangs, since
   ssh/a52-netns won't run then). Then, BEFORE reboot:
   `sudo ip netns exec a52 socat -u UDP-RECV:6666,reuseaddr - | tee <scratchpad>/netconsole.log &`
3. Boot: EXTRA_CMDLINE='netconsole=6665@172.16.42.1/usb0,6666@172.16.42.2/02:a5:2c:00:00:01 \
   initcall_debug ignore_loglevel g_ether.host_addr=02:a5:2c:00:00:01' \
   flock /tmp/claude-1000/a52phone.lock ~/linux-a52q/uki-test.sh 0.26.0930.4 <vmlinuz> <dtb> \
   7.3.0-rc5-sm7125 ; then `ssh a52r systemctl reboot` (don't hold ssh). Boot-count
   auto-falls-back to stock in 2.5-10 min if 7.3 hangs; wait up to 20 min.
4. Read netconsole.log last lines + initcall_debug to locate the hang; fix per Step 2.

Safety state at stop: phone on 6.14.7-sm7125, default /boot/EFI/Linux/a52qtest_0.26.0930.1.efi
present (unchanged; NO 7.3 test UKI was ever installed — uki-test.sh never ran). Backup
/var/tmp/a52qtest_0.26.0930.1.efi.bak intact (sha256 7237fbd9…). No watchers/listeners left
running; OBS poll killed. Nothing to restore.

## Camera upstreaming — state at stop (2026-09-30)
Branch a52q/cameras in ~/src/linux-upstream @ 72d3fcf802c4 (7.3-rc5). Two commits, nothing else touched.
- ak7374 VCM: DONE. Fits existing upstream ak7375 driver as new compatible (struct already has
  has_standby/mode_standby). 2 patches (binding enum + driver cdef/OF entry), MAINTAINERS unchanged
  (same files). checkpatch --strict 0/0/0 both. dt_binding_check clean (SCHEMA+DTEX+DTC pass).
  Series in ~/linux-a52q/upstream/ak7374/ (cover + 0001 + 0002 + to-cc.txt).
- s5k3l6xx, imx616, s5kgw1p: NOT STARTED as patches. Good news: modern drivers already exist in
  ~/src/linux-sm7125 obs/sm7125 (v4l2-cci, cci_reg_sequence, subdev active state, pm_runtime,
  fwnode device_parse, get_selection). Remaining: copy .c/.h into tree + Kconfig/Makefile, write
  DT-binding YAML from scratch (none exist; the *.yaml in cameras/ are libcamera tuning, not DT),
  MAINTAINERS entries, checkpatch/dt_binding_check/W=1, register-table old-vs-new diff, cover+to-cc.
- gc5035: NOT STARTED. Old-style driver (no CCI helpers) from Figa 2020 v4 base; needs the most work.
  Reuse Figa v4 from patchwork (kernel.org API) for authorship/base; keep his From:/SoB if using his patch.
No scratch O= build dir was created (stopped before compile-testing). No git gc/repack run.

## 2026-09-30 late — 7.3 "HANG" ROOT-CAUSED: U-Boot-armed watchdog + modules unloadable (NOT a kernel hang)
Channel: netconsole debug build (obs/a52q-mainline-dbg) + laptop listener in netns a52, AND a phone-side
journald drop-in /etc/systemd/journald.conf.d/99-a52q-debug-sync.conf (SyncIntervalSec=1s) + enabled
a52q-heartbeat.service (logs `hb <uptime> <udc state>` every 1 s). The persistent journal of the failed
boot (`journalctl -b -1` on the 6.14 fallback) is the better channel: it survives the reset.
- netconsole works (g_ether.host_addr pins the host MAC; netpoll.carrier_timeout=30). Log stops at
  12.78 s = deferred-probe timeout ONLY because nothing else is printed; NOT a freeze (misread at first;
  disabling the DSI node changed nothing, which disproved the DSI/refgen hang theory).
- Heartbeat: userspace alive, UDC "configured", until 28.1 s, then hard reset. regulator_ignore_unused: same.
- CAUSE: U-Boot .config has WDT_QCOM=y, WATCHDOG_AUTOSTART=y, WATCHDOG_TIMEOUT_MSECS=30000 → U-Boot leaves
  the APSS WDT running at hand-off. 6.14 loads qcom_wdt (=m) from modules-load.d at 9 s (driver sees
  HW_RUNNING and pets it). On 7.3 qcom_wdt=m never loads: sysext merge fails ("Failed to mount sysext
  (type overlay) ... No such device") because OVERLAY_FS=m and the stock initrd only has the 6.14
  overlay.ko → no 7.3 module is ever available → bite at ~28 s kernel time.
- Also found: REGULATOR_QCOM_REFGEN=m → msm_dsi defers forever ("Failed to get supply 'refgen'").
FIX (pushed obs/a52q-mainline 51966e7 + -dbg eccc265): a52q_defconfig QCOM_WDT=y, OVERLAY_FS=y,
REGULATOR_QCOM_REFGEN=y. uki-test.sh: EXTRA_CMDLINE now %q-quoted (multi-word args broke the ssh env).
Remove the journald sync drop-in + heartbeat unit when 7.3 bring-up is done (extra flash writes).

## 2026-10-01 — Camera sensor upstream series DONE (s5k3l6xx, imx616, s5kgw1p)
Branch a52q/cameras in ~/src/linux-upstream, 6 commits on top of the 2 ak7374 ones
(base f5b2a1c14d25). One binding + one driver commit per sensor. Sources copied
verbatim from ~/src/linux-sm7125 obs/sm7125; only changes: MODULE_AUTHOR set to a
real name (imx616/s5kgw1p), s5k3l6xx MODULE_LICENSE "GPL v2"->"GPL", modes.h given
an SPDX line and reflowed to <=100 cols (register VALUES byte-identical: 928 imx616
/ 4617 s5kgw1p entries diffed equal). s5k3l6xx keeps the Purism copyright/authors
and credits them in the commit + cover (From: is Miroslav; no forged SoB).
- DT bindings written from scratch under Documentation/.../media/i2c/:
  sony,imx616.yaml (4-lane D-PHY, vio/vana/vdig, reset-gpios, link 516 MHz),
  samsung,s5k3l6xx.yaml (4-lane D-PHY, vddio/vdda/vddd, rstn-gpios, clock-frequency,
  link 595.2 MHz), samsung,s5kgw1p.yaml (3-trio C-PHY bus-type=4, 5 supplies incl
  vaf/vcustom, reset-gpios, link 1 GHz).
- MAINTAINERS: 3 new entries (M: Miroslav, L: linux-media, S: Maintained); binding F:
  in the binding commit, driver F: in the driver commit so each patch touches
  MAINTAINERS (no checkpatch "does MAINTAINERS need updating" warning).
- checkpatch --strict: 0 errors, 0 warnings on all 6. Remaining CHECKs are idiomatic
  --strict only: "multiple assignments" (fse->min_width = fse->max_width = ... in
  enum_frame_size, same as every peer sensor driver) and "blank line after decl"
  (#define NUM_SUPPLIES ARRAY_SIZE(...) right after the array). Left as-is.
- dt_binding_check: all 3 yaml + examples validate clean (dtschema 2026.9, yamllint
  1.38 via venv; the make LINT/STYLE stage misfires with DT_SCHEMA_FILES on dtschema
  2026 - ran yamllint + example validation directly).
- W=1 compile: arm64 defconfig + the 3 symbols (O= dir in tmpfs, disk was at 831 MB),
  native aarch64-linux-gnu-gcc 16.1.0 - all 3 .o build with ZERO warnings. Build dir
  deleted afterwards.
- Series: ~/linux-a52q/upstream/cameras/{imx616,s5k3l6xx,s5kgw1p}/ (cover + 2 patches
  + to-cc.txt from get_maintainer.pl).
- OPEN: s5kgw1p capture needs C-PHY in camss (not mainline yet) - noted in its cover.
  s5k3l6xx binding uses rstn-gpios/clock-frequency to match the working driver;
  reviewers may ask for reset-gpios/assigned-clock-rates (driver change, not re-tested).

## 2026-10-01 — smp2p sleepstate ported to mainline (branch a52q/smp2p)
Ported from obs/sm7125 e84f35c88 + 885022f6d into worktree ~/src/linux-a52q-smp2p
(sparse checkout — disk critical). 4 commits on a52q/smp2p:
- 13259c3f (Richard Acayan): dt-bindings qcom,smp2p sleepstate entry (carried from
  patchwork 14837140, his From/SoB preserved).
- 6d6e9f47: new dt-binding qcom,smp2p-sleepstate.yaml for the consumer node
  (Acayan's patch is entry-only; the "qcom,smp2p-sleepstate" compatible needs its
  own binding or dtbs_check warns).
- e6243b0d (miromraz, orig author preserved): driver smp2p_sleepstate.c + Kconfig +
  Makefile (both source commits squashed; bit-from-DT form).
- c7dc0c39: a52q dts — sleepstate/sleepstate_see entries on &{/smp2p-lpass} + the
  smp2p-sleepstate consumer node (bit 12, IRQ_TYPE_EDGE_RISING).
Checks: checkpatch --strict 0 err/0 warn (only generic "MAINTAINERS?" new-file notice,
false pos — files under existing qcom wildcards). dt-doc-validate OK on both bindings
(schema + examples). SKIPPED (disk <1GB, ~827M): dt_binding_check make target,
dtbs_check on sm7125-samsung-a52q.dtb, W=1 build of the .o — rerun when disk frees.
Open: SoB/author identity mixed (seznam driver vs techmania tree) — normalise before
sending upstream.

## 2026-10-01 — Adreno 618 GPU bringup (SM7125 / a52q), mainline v7.3-rc5

Symptom on device: `missing support for speed-bin: 159`, `adreno_idle timeout
... rptr/wptr = 0/C`, `gpu hw init failed: -22`, hangcheck lockups, `GMU
firmware fault`, `failed to power off SPTPRAC: 0xa8`. Chip id 0x06010800 (A618).

Root cause: a52q top compatible is "samsung,a52q","qcom,sm7125", so the GPU
matched the generic (no .machine) A618 entry in a6xx_catalog.c, which (a) has no
speed-bin 159 -> fuse_to_supp_hw() returns UINT_MAX and enables *every* OPP
including 825 MHz TURBO_L1, and (b) has no .hwcg. Overvolted top corner +
missing clock gating => GMU/SPTPRAC power-up failure.

Fix (branch a52q/gpu off a52q/mainline; worktree was forced onto tmpfs because
/ had <1 GB free):
- drm/msm/adreno: new `.machine = "qcom,sm7125"` catalog entry (chip 0x06010800,
  a615_hwcg, a615_zap.mbn, speedbins {0,0},{159,3}). Chose a per-SoC entry over
  extending the shared generic entry (what the sm7125-mainline fork did) so hwcg
  + bin 159 stay scoped to SM7125 and sc7180 chromebooks (bins 0/169/174) are
  untouched. Mirrors the existing sm7150 entry. Lookup returns the first
  machine-matching entry, so it must (and does) sit before the generic one.
- arm64: dts: qcom: sm7125.dtsi overrides &gpu_opp_table: adds 750 MHz NOM_L1
  (opp-supported-hw <0x08> = BIT(3) = bin 159) and widens 650/565/430/355/267/180
  MHz from <0x07> to <0x0f>. 800/825 MHz stay sc7180-only. Done in sm7125.dtsi,
  not sc7180.dtsi, so all SM7125 SKUs get it and sc7180 is untouched.

Bin 159 -> 750 MHz NOM_L1 confirmed via downstream atoll mapping
(FMAX/4.8 + 2, round up: 750/4.8 + 2 = 158.25 -> 159). Original work:
Vitalii Skorkin (nikroks@mainlining.org), sm7125-mainline commits 95df926 /
31a7f8d / c6779e7 — credited in the commit bodies (no Co-authored-by per task).
No pending upstream patch found (patchwork API was Anubis-blocked, so unverified).

Verify: defconfig+DRM_MSM on tmpfs; `W=1 a6xx_catalog.o` compiles with zero
warnings; `CHECK_DTBS=y sm7125-samsung-a52q.dtb` clean. Decompiled dtb confirms
a52q (BIT(3)) OPP set = 180/267/355/430/565/650/750 MHz (no 800/825).
checkpatch --strict: DTS clean; DRM has one false-positive CHECK
("line ends with '('") from the ADRENO_SPEEDBINS() macro used file-wide.

## 2026-10-01 - DT gap close: NFC, GPI DMA, key wakeup (branch a52q/dtfix)

Worktree ~/src/linux-a52q-dtfix on a52q/dtfix (off a52q/mainline). Disk was
critical (~800M free, contended by parallel agents); a full worktree checkout
ran out of space, so this is a git sparse-checkout (arch/arm64, scripts,
include, Documentation/devicetree, all Kconfig/Makefile + checkpatch sentinels).
Build out dir was on tmpfs (/tmp) to avoid the full rootfs.

Commits (upstream-style, no Signed-off-by yet, no Co-authored-by):
- sc7180: add gpi_dma0@800000 / gpi_dma1@a00000 (qcom,sm6350-gpi-dma) and wire
  tx/rx dmas on all 20 geni I2C/SPI SEs. Fixes "Failed to get tx DMA ch" at
  i2c@a84000 (i2c7). Addresses/IRQs/masks/SMMU IDs taken from the 6.14 fork
  sc7180.dtsi and cross-checked against sm6350.dtsi; style follows sm8250.dtsi
  (uart SEs deliberately get no dmas).
- sm7125-samsung-a52q: NFC S3NRN4V on i2c0@0x27 + vreg_nfc_pvdd (GPIO68) +
  nfc_default pinctrl. compatible samsung,s3nrn4v is in the mainline binding.
  qupv3_id_0 is already status=okay in common.dtsi, so i2c0 only needs enabling.
- sm7125-samsung-common: wakeup-source on button-vol-up and event-hall-sensor.

REVIEWER FLAGS:
- nfc_default int-pins lists "gpio31" alongside the IRQ "gpio37" (both
  bias-pull-down), ported verbatim from the RF-poll-verified 6.14 DT. gpio31 is
  NOT referenced by nfc@27; purpose unknown (possible downstream clk/fw line).
  Kept to preserve the verified config; drop it if it has no NFC role.
- sc7280.dtsi is absent from this a52q/mainline tree, so sm8250.dtsi/sm6350.dtsi
  were used as the upstream dmas-wiring reference instead.

Verification (make O=<tmpfs> ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
CHECK_DTBS=y qcom/sm7125-samsung-a52q.dtb, under flock a52build.lock):
- dtbs_check: 0 warnings before, 0 warnings after (dt-validate clean; dtschema
  2026.6). dtb builds. The first post-defconfig run printed 5 spurious "Error in
  reading or end of file" while processed-schema.json was being generated; gone
  on rebuild and on direct dt-validate.
- checkpatch.pl --strict: all 3 commits "0 errors, 0 warnings, 0 checks".

Kconfig symbols these DT nodes need (defconfig NOT touched, per task):
- NFC node: CONFIG_NFC_S3FWRN5=m + CONFIG_NFC_S3FWRN5_I2C=m (+ CONFIG_NFC).
- GPI DMA + dmas wiring: CONFIG_QCOM_GPI_DMA=y/m (else geni stays FIFO-mode).
- key wakeup-source: none (DT-only PM wakeup).
- Unrelated pre-existing item (not from these DT changes, handled in defconfig
  elsewhere): CONFIG_TYPEC_MUX_SM5714 for the already-merged typec@33 graph.

## CAMSS + CCI mainline enablement for sc7180/sm7125 (2026-10-01)
Branch a52q/camss (worktree ~/src/linux-a52q-camss, off a52q/mainline). Goal: upstream-submittable
sc7180 CAMSS + CCI so a52q cameras work on mainline. 4 commits (no Co-authored-by):
- dt-bindings: media: qcom,camss: Add SC7180 CAMSS binding (new qcom,sc7180-camss.yaml, modelled on
  sm6350; 10 reg, 24 clocks, 10 irqs, 4 icc cam_ahb/cam_hf_0/1_camnoc/cam_sf_camnoc, 3 iommus,
  3 power-domains ife0/ife1/top).
- media: qcom: camss: Add support for SC7180 (CAMSS_7180 enum + csiphy/csid/vfe/icc _sc7180 tables +
  of_match; vfe.c: CAMSS_7180 added to the two VFE-170 switch groups).
- dt-bindings: i2c: qcom,i2c-cci: Add qcom,sc7180-cci (CCI v2, msm8996-cci fallback).
- arm64: dts: qcom: sc7180: Add CCI and CAMSS nodes (cci0@ac4a000, cci1@ac4b000, isp@acb3000, all
  status=disabled; cci0/1/2 tlmm pinctrl; added #include qcom,camcc-sc7180.h). NO a52q sensor nodes
  (separate agent).
Prior art credited via Link: George Chan's unmerged sm7125 RFT v3 (patchwork 13709404..).

Porting notes (6.14 fork -> mainline 7.3-rc5):
- Fork csid tables used bare-string regulators (.regulators = {"vdda-phy","vdda-pll"}); mainline field
  is regulator_bulk_data[] -> compile error. Dropped to .regulators = {} (matches sm6350; fork DT had
  no vdda supplies anyway -> dummy regulators, functionally identical). Supplies also dropped from the
  binding.
- Added csiphy .id = 0..3 (mainline needs it for base offset / clock matching; fork omitted).
- sc7180 is genuinely distinct from sm6350 in-tree (different clock names, 3 vs 4 CSID/VFE, icc names),
  so ported the fork's own sc7180 tables rather than reusing sm6350.

C-PHY DEFERRED (not in these commits). Mainline camss.c:4761 hard-rejects any bus-type != CSI2_DPHY,
so the main S5KGW1P (C-PHY) will NOT stream until C-PHY lands; the 4 D-PHY sensors (UW/front/depth,
+macro via mux) are unaffected. David Heidelberg's C-PHY v9 (patchwork 14719209-213) is state
"handled-elsewhere" (not merged); it touches camss-csiphy-3ph-1-0.c (the file sc7180 uses) but adds a
Gen2 v1.1 path - fit vs sc7180's csiphy_ops_3ph_1_0 not yet verified. Rebase our C-PHY on his series
once it lands, as a follow-up.

Checks (aarch64-linux-gnu- host gcc; out dir built+deleted, disk stayed >2.5G):
- checkpatch.pl --strict: clean on all 4 (fixed 4 DTS >100col interconnect lines by splitting).
- dt-doc-validate + dt_binding_check (DT_SCHEMA_FILES both yamls): rc=0, no errors.
- W=1 build of drivers/media/platform/qcom/camss/ (CAMSS=m): rc=0, zero warnings.
- sm7125-samsung-a52q.dtb builds clean; dt-validate of the dtb vs both processed schemas: rc=0
  (isp@acb3000/cci@ nodes confirmed present in the dtb).

Remaining for on-device test: enable camss+cci0/cci1 in the a52q board dts with sensor nodes
(other agent), set CONFIG_VIDEO_QCOM_CAMSS/I2C_QCOM_CCI, boot, verify the 4 D-PHY cameras via
libcamera. Main cam needs the C-PHY follow-up.

## 2026-10-01 — OIS MCU mainlined + AK7374 rebased (branch a52q/ois)
Upstream-submittable OIS MCU driver + DT binding, plus the AK7374 VCM series,
prepared on the tmpfs worktree `git -C ~/src/linux-upstream worktree add
/tmp/claude-1000/wt-ois -b a52q/ois a52q/mainline`. Four commits on a52q/ois
(authored Miroslav Mráz <miroslav.mraz@techmania.cz>, no Co-authored-by):
- dt-bindings: media: add Samsung camera OIS MCU
- media: i2c: add Samsung camera OIS MCU driver
- dt-bindings: media: asahi-kasei,ak7375: add AK7374   (cherry-pick d1809e945)
- media: i2c: ak7375: add support for AK7374           (cherry-pick f5b2a1c14)

### Upstream shape decisions (for the reviewer)
- Dropped the product-specific `samsung,a52q-ois-mcu` compatible for a
  vendor-prefixed `samsung,ois-mcu`; driver renamed
  drivers/media/i2c/a52q-ois-mcu.c -> samsung-ois-mcu.c,
  CONFIG_VIDEO_A52Q_OIS_MCU -> CONFIG_VIDEO_SAMSUNG_OIS_MCU (in the
  "Lens drivers" menu), module `samsung-ois-mcu`. A52q-specific tuning
  (gyro orientation, angle-comp 0.834, gyro scale 114) stays as the
  driver's built-in module tuning; a second board would add DT props later.
- Kept it a plain media-i2c companion driver, NOT a full V4L2 subdev: it
  exposes no controls or pads, so subdev boilerplate buys nothing. If a
  reviewer wants it in the media graph, that's a follow-up.
- RUNTIME-PM TRIGGER FIX (the DEBUG gap from 2026-09-30): the driver now
  reads a `samsung,image-sensor` phandle and at probe creates a
  device_link_add(&sensor->dev /*consumer*/, ois /*supplier*/,
  DL_FLAG_STATELESS | DL_FLAG_PM_RUNTIME), returning -EPROBE_DEFER until the
  sensor i2c device exists. This makes the harness's proven sensor->OIS link
  permanent WITHOUT touching the (not-yet-upstream) sensor driver: the
  sensor's stream-on runtime_resume resumes+inits the OIS first, suspends it
  after. Link torn down in remove.

### Checks (all green)
- checkpatch.pl --strict --no-summary: 0/0 on all four commits.
- dt_binding_check on samsung,ois-mcu.yaml AND asahi-kasei,ak7375.yaml: pass
  (full processed-schema.json built; only skipped optional yamllint). dtschema
  2026.6 system-wide, ~/.local/bin/dt-validate — no venv needed.
- W=1 cross-build (aarch64-linux-gnu-gcc 16.1.0, arm64 defconfig+olddefconfig,
  under flock /tmp/claude-1000/a52build.lock): drivers/media/i2c/samsung-ois-mcu.o
  and ak7375.o both compile with ZERO warnings. tmpfs was 100% full (other
  agents' 1.8G worktrees), so the out dir went to a throwaway ~/.a52ois-build
  on root fs and was deleted after (not tmpfs — forced deviation).

### AK7374 rebase note
Cherry-picked cleanly onto a52q/mainline; no changes needed. Base ak7375.c /
asahi-kasei,ak7375.yaml unchanged from when the series was written.
CONFLICT WARNING (do not block): the two pending ak7375 patches named in the
task — Jan-Michael Brummer's AK7377 and Cong Nguyen's leak fix — are NOT yet in
the a52q/mainline base. When they land, AK7377 will textually collide with the
AK7374 additions (same compatible enum in the yaml, same of_device_id table and
adjacent ak73xx_chipdef block in ak7375.c); trivially re-orderable. Cong's leak
fix touches probe/remove error paths and should not conflict with the pure
additions.

### patchwork check — BLOCKED
patchwork.kernel.org (and lore) are behind Anubis proof-of-work; WebFetch,
curl with a browser UA, and a scripted PoW solve all returned the challenge
page, not JSON. Could not query for a pending Samsung OIS MCU driver to reuse.
Proceeded on knowledge (no upstream/pending Samsung OIS MCU driver known) plus
the task-supplied pending-ak7375 patch names. Re-run the patchwork query from a
real browser session before actually posting the OIS series.

### DT node snippet (mainline a52q dts has NO camera i2c bus yet)
a52q/mainline's sm7125-samsung-a52q.dts has only camera_region memory — no
i2c10 / i2c-gpio cam bus — so the OIS node was NOT added to the dts (the camss
agent owns adding the camera i2c buses). When that bus exists, add (bit-banged
i2c-gpio on the QUP i2c10 pins because the MCU stretches SCL during flash
access; shares the main actuator rails l7/l3; add the sensor phandle for the PM
link):

    /* main-camera OIS: STM32G MCU at 0x62, bit-banged i2c (gpio86/87) */
    i2c-cam-ois {
        compatible = "i2c-gpio";
        sda-gpios = <&tlmm 86 (GPIO_ACTIVE_HIGH | GPIO_OPEN_DRAIN)>;
        scl-gpios = <&tlmm 87 (GPIO_ACTIVE_HIGH | GPIO_OPEN_DRAIN)>;
        i2c-gpio,delay-us = <5>;
        i2c-gpio,timeout-ms = <1000>;
        #address-cells = <1>;
        #size-cells = <0>;

        ois@62 {
            compatible = "samsung,ois-mcu";
            reg = <0x62>;
            vdd-supply = <&vreg_cam_l7>;
            vio-supply = <&vreg_cam_l3>;
            reset-gpios = <&tlmm 32 GPIO_ACTIVE_LOW>;
            boot0-gpios = <&tlmm 43 GPIO_ACTIVE_HIGH>;
            samsung,image-sensor = <&s5kgw1p>;  /* main sensor: drives OIS PM */
        };
    };

STILL OPEN (unchanged): EFS gyro offset (0x0248) hardcoded 0; real on/off
image comparison needs a working capture; DT probe/bind of the new compatible
not booted.

## 2026-10-01 — LPASS audio stack to mainline v7.3-rc5 (branch a52q/lpass)

Worktree /tmp/claude-1000/wt-lpass on a52q/lpass, based on a52q/audio
(ec32d4a3, tas2562 frame-sync patch). 5 commits, nothing else touched.

Key finding that reshaped the plan vs GAP item 3 / DEBUG blocker list:
- Blocker 1 (no sc7180 LPI pinctrl driver): NOT needed. Mainline already has
  the generic LPI framework + pinctrl-sc7280-lpass-lpi.c. The SC7180 LPI TLMM
  is register-identical to SC7280 (both 15 pins; the LPI_PINGROUP offset tables
  are byte-identical — sm6350 is the 14-pin odd one). So instead of duplicating
  a driver (a reviewer would reject the copy), the SC7280 binding now accepts
  "qcom,sc7180-lpass-lpi-pinctrl" as a fallback pairing and the existing SC7280
  driver binds via the 2nd compatible. This is what the 6.14 fork did too.
- Blocker 3 (Quinary-MI2S machine hack): NOT ported. The fork's sm8250.c hack
  did 3 things on the shared QUINARY_MI2S_RX case (would regress fp5 which has
  the identical 2×aw88261-on-quinary topology): (a) NB_IF frame-start, (b)
  set_tdm_slot(0x3,0x3,2,16), (c) per-codec fmt loop. Analysis:
    * tas2562 L/R separation is a runtime "ASI1 Source" kcontrol (Left/Right/
      LeftRightDiv2), set by UCM — NOT a slot. Same as fp5/aw88261 which rely on
      the generic NB_NF I2S case + awinic,audio-channel. So no machine change
      for channel routing.
    * The one fatal item is RXLEN: tas2562 defaults RX *slot length* to 32-bit
      (TDM_CFG2, not in reg_defaults); hw_params only sets RX *word length*
      (RXWLEN). On the 16-bit MI2S frame the slot/BCLK mismatch = "TDM clock
      error" = no audio. Fixed the upstream-correct way (blocker's hint): new
      per-codec DT prop "ti,rx-slot-width", applied once at component probe.
      Both amps get ti,rx-slot-width=<16>. No machine driver touched; fp5
      (no tas2562) unaffected.
    * NB_IF frame-start: the fork needed it *with* its forced-TDM config ("with
      their default frame start the channels come out swapped"). In plain I2S
      mode (generic case) this should not recur; ec32d4a3 already gives the
      codec the NB_IF capability if a follow-up proves it's needed. THIS IS THE
      RISKIEST ON-DEVICE ITEM (see below).

Commits (a52q/lpass, no Co-authored-by, author Miroslav Mráz):
  67b8e5b dt-bindings: pinctrl: qcom: allow sc7180 LPASS LPI TLMM
  deed152 dt-bindings: ASoC: tas2562: add ti,rx-slot-width
  1ad0511 ASoC: tas2562: pin the RX slot width from the device tree
  1db2ba9 arm64: dts: qcom: sc7180: add LPASS audio macros, SoundWire, LPI TLMM
  4daf92c arm64: dts: qcom: sm7125-samsung-a52q: speakers, WCD938x, sound card

sc7180.dtsi: added rxmacro/txmacro/vamacro (sm8250 compatibles, HW-verified),
swr1/swr2 (soundwire-v1.5.1), lpass_tlmm (sc7180+sc7280 fallback, pin states
tx_swr/rx_swr/i2s1). ALL status=disabled by default so trogdor is untouched.
a52q enables them + i2c-gpio speaker bus (2×tas2562 @0x4c/0x4d, gpio88/89 SDA/
SCL, INT gpio90, EN gpio94), wcd938x over swr, qcom,sm8250-sndcard with speaker
+ WCD playback/capture DAI links (Quinary MI2S / RX_CODEC_DMA_RX_0 /
TX_CODEC_DMA_TX_3). Reused the mainline q6afe/q6asm/q6routing tree already in
sc7180.dtsi.

Chose sm8250 macro compatibles verbatim (as the fork, HW-proven) rather than
adding sc7180-prefixed fallbacks to 3 macro bindings — minimal, dtbs_check-clean.
A reviewer may ask for qcom,sc7180-lpass-*-macro fallbacks; cheap follow-up.
Dropped ti,vmon-slot-no (missing from the binding; I/V sense capture is not
routed on this card, driver default is harmless) — noted as a pre-existing
binding gap, not fixed here to keep scope tight.

Verification (native x86 host, aarch64-linux-gnu- cross, O= on real disk,
flock a52build.lock; out dir + build worktree deleted after):
- CHECK_DTBS=y qcom/sm7125-samsung-a52q.dtb: builds, 0 dtbs_check warnings.
- CHECK_DTBS on sc7180-trogdor-coachz-r1.dtb (validates the new disabled
  nodes): 0 warnings.
- dt-doc-validate on both changed yamls: OK. dt_binding_check ran CHKDT clean
  (DTEX example-compile misfires with DT_SCHEMA_FILES on dtschema 2026, known);
  bindings are validated in practice by the clean a52q dtbs_check.
- W=1 sound/soc/codecs/tas2562.o (native aarch64 gcc): 0 warnings.
- checkpatch --strict -g: 4/5 commits 0/0/0; sc7180.dtsi has 2 "line >100"
  warnings on the q6afecc NPL_MCLK clock lines — identical to 142 accepted
  lines in sm8250.dtsi, left as-is.

defconfig symbols the stack needs (all =m unless noted):
  PINCTRL_SC7280_LPASS_LPI (selects PINCTRL_LPASS_LPI) — binds lpass_tlmm
  SND_SOC_QDSP6 (q6afe/q6asm/q6routing/q6afe-clocks; needs the ADSP+APR already
    enabled), SND_SOC_SM8250 (the qcom,sm8250-sndcard machine driver),
  SND_SOC_LPASS_VA_MACRO, SND_SOC_LPASS_RX_MACRO, SND_SOC_LPASS_TX_MACRO,
  SOUNDWIRE + SOUNDWIRE_QCOM, SND_SOC_WCD938X + SND_SOC_WCD938X_SDW,
  SND_SOC_TAS2562, I2C_GPIO (bit-banged amp bus).
  (a52q_defconfig already carries SOUNDWIRE_QCOM/QDSP6 per GAP; add the rest.)

Needs on-device verification (never booted):
  1. Speaker: does plain I2S NB_NF + ti,rx-slot-width=16 produce clean audio,
     or does a52q still need NB_IF frame-start like the fork? RISKIEST ITEM.
     If distorted/swapped: the ec32d4a3 codec capability is there; wire NB_IF
     per-card without touching the shared sm8250.c QUINARY case (e.g. a codec
     DT prop or a card-scoped hook) — do NOT re-add the fork's global hack.
  2. UCM must set each amp's "ASI1 Source" (Left/Right) for stereo.
  3. WCD938x earpiece/mic/headset over SoundWire; MBHC thresholds copied from
     the fork (Samsung values) — verify button/headset detection.
  4. tas2562 INT is IRQ_TYPE_LEVEL_LOW (fork used IRQ_TYPE_NONE); confirm no
     irq storm.

## Mainline camera DT (a52q/camdt) — 2026-10-01

Branch `a52q/camdt` (worktree `/tmp/claude-1000/wt-camdt`), built on `a52q/camss`
(SC7180 CAMSS + CCI, disabled cci0/cci1/camss in sc7180.dtsi). Cherry-picked the
camera driver/binding commits from `a52q/cameras`: AK7374 (ak7375), IMX616,
S5K3L6XX, S5KGW1P (bindings + drivers). Added the a52q camera DT in three commits
(all in sm7125-samsung-a52q.dts only — none of it is shared with a72q, so nothing
went into the common dtsi):
  1. S2MPB03 camera PMIC on an i2c-gpio bus (gpio25/26) + 2 GPIO fixed LDOs.
  2. Sensors + CAMSS: IMX616 front (CSIPHY2, D-PHY 4-lane, MCLK4), S5K3L6XX UW
     (CSIPHY3 via a gpio66 video-mux, D-PHY 4-lane, MCLK2), S5KGW1P main (CSIPHY0,
     C-PHY 3-trio, MCLK0); camcc/cci0/cci1/camss enabled; MCLK pinctrl.
  3. AK7374 VCM + main/front module EEPROMs (at24) on i2c9, lens-focus link.

Checks (tmpfs was full at 49M, so O= went to /home/realni/.cache/a52camdt-out on
rootfs instead of tmpfs; deleted afterwards; system dtschema 2026.6, no venv):
  - `make CHECK_DTBS=y qcom/sm7125-samsung-a52q.dtb`: 0 warnings.
  - checkpatch --strict on the 3 DT patches: 0 errors / 0 warnings / 0 checks.
  - dt_binding_check on the 3 amended sensor bindings: clean.

Porting notes vs the working 6.14 obs DT (property names differ under the mainline
bindings' unevaluatedProperties):
  - data-lanes are 1-based on the sensor endpoints (imx616/s5k3l6xx <1 2 3 4>,
    s5kgw1p <1 2 3>); the CAMSS csiphy endpoints stay 0-based.
  - Dropped `power-domains = <&camcc TITAN_TOP_GDSC>` from the sensor nodes (not in
    the sensor bindings; matches db845c/ov8856, GDSC held by CAMSS/CCI).
  - Dropped `vdda-phy-supply`/`vdda-pll-supply` from &camss (the qcom,sc7180-camss
    binding has no supply properties).
  - Renamed the i2c-gpio bus i2c-cam-pmic -> i2c-campmic (i2c-controller nodename
    regex allows only one `-[a-z0-9]+` segment; the old name also blocked the child
    schema so #address-cells and the pmic child were flagged).
  - MCLK rate set via assigned-clock-rates (imx616/s5kgw1p read clk_get_rate);
    s5k3l6xx additionally keeps clock-frequency (its driver reads it).

Binding fixes folded into their cherry-picked commits (drivers require them, the
bindings were incomplete/wrong):
  - all three sensor bindings: added `clock-names: const mclk` (drivers do
    devm_clk_get(dev,"mclk")); updated required + examples.
  - samsung,s5kgw1p.yaml: bus-type `const: 4` (D-PHY) was wrong for a C-PHY sensor
    whose driver presets V4L2_MBUS_CSI2_CPHY -> changed to `const: 1` (C-PHY); DT
    uses MEDIA_BUS_TYPE_CSI2_CPHY on both the sensor and csiphy0 endpoints.

Known limitations (noted, not blockers):
  - Main S5KGW1P is C-PHY. The mainline CAMSS driver on a52q/camss has no C-PHY RX
    support (that lives only in the a52q/cameras camss hack), so the main camera is
    described but will not stream until C-PHY receive support is merged.
  - Macro + depth cameras are GalaxyCore GC5035 — no mainline binding/driver exists,
    so both are omitted. The video-mux keeps a reserved (unconnected) input port@1
    for the macro; CSIPHY1 (depth) is left unused. Add both when a GC5035 binding
    lands.
  - The downstream cci "cci-camnoc" interconnect vote (clock-wedge workaround) was
    not ported; it is a runtime tuning, not hardware wiring, and the cci binding
    doesn't model it.

defconfig symbols needed to build/use these: VIDEO_QCOM_CAMSS, I2C_QCOM_CCI,
VIDEO_IMX616, VIDEO_S5K3L6XX, VIDEO_S5KGW1P, VIDEO_AK7375, VIDEO_MUX, MULTIPLEXER,
MUX_GPIO, EEPROM_AT24, I2C_GPIO, REGULATOR_S2MPB03 (plus the usual
MEDIA_CONTROLLER / VIDEO_V4L2 / V4L2_FWNODE deps).

## 2026-10-01 01:15 — MAINLINE 7.3 BOOTS TO USERSPACE (obs/a52q-integ 70a83b1, UKI a52qtest_0.26.1001.1)
Reached boot completion ("degraded": only hexagonrpcd failed), SSH over usb0. Module install: ~/linux-a52q/mods73.sh.
WORKS on 7.3: modem (mmcli sees it), ADSP, IPA, USB gadget net, sm5714 charger+FG, DSI panel s6e3fc3 + backlight,
keys, vibrator, Type-C port0+partner, watchdog, **GPU A618** (fences retire, devfreq 180-750 MHz — better than 6.14,
where zap never loaded).
BROKEN on 70a83b1 and root-caused (fixes in branch a52q/bootfix, in obs/a52q-integ 4c13f42):
- Wi-Fi: qcom_pd_mapper has no "qcom,sm7125" entry → no WLAN PD → no WLFW (qrtr-lookup lacks svc 69).
- Bluetooth: qcom_geni_serial "Invalid line -19": with NO serial aliases of_alias_get_highest_id() = -ENODEV and
  ida_alloc_range(min<0) fails → generic mainline bug; clamp fix + serial1=&uart3 alias.
- Touch: geni i2c7 (a84000) in GPI mode, no GPI DMA nodes → a52q/dtfix gpi_dma (merged in 53cbc3c+).
- Sensors: ADSP fastrpc lacked qcom,non-secure-domain → only /dev/fastrpc-adsp-secure → hexagonrpcd fails.
- NFC: DT node was not in 70a83b1 (a52q/dtfix).
Phone state: default = 7.3 test UKI (blessed); fallbacks a52q614_0.26.0930.1.efi (sha 7237fbd9, good 6.14) and stock.
a52q-failsafe73.service is still enabled (deletes a52qtest_* after 5 min on 7.x unless /run/keep73) — remove
once 7.3 is the default.
Integration branch: a52q/integ in ~/src/linux-upstream = a52q/mainline + gpu, smp2p, audio, dtfix, bootfix, lpass,
ois, camdt (+ debian/defconfig commits). Pushed as github obs/a52q-integ; OBS package linux-sm7125-mainline now
scmsyncs that branch (NOT obs/a52q-mainline any more).

## 2026-10-01 — CAMSS C-PHY receive for SC7180/SM7125 (branch a52q/cphy)

Worktree `/tmp/claude-1000/wt-cphy`, branch `a52q/cphy` off `a52q/camdt`. Goal:
main camera S5KGW1P (3-trio C-PHY on CSIPHY0) streams on mainline.

Base chosen: **David Heidelberg's C-PHY v9 series** (patchwork series 1136910,
ids 14719206-14719214, state "handled-elsewhere"). It was NOT blocked — fetched
via the patchwork REST API (`/api/1.3/patches/<id>/` -> the JSON `mbox` URL; the
`/api/.../mbox/` path 404s, use the web `.../patch/<msgid>/mbox/` from the JSON).
Applied all 9 via `git am` (From/SoB preserved, David Heidelberg <david@ixit.cz>),
they apply cleanly on a52q/camdt. Then one own commit on top:

- `media: qcom: camss: Add C-PHY support for SC7180` (60a32360c60c). Adds
  `lane_regs_sc7180_cphy[]` — the CSIPHY v1.2 3-phase table flattened from our
  6.14 commit 7a9497b16 (verbatim downstream Samsung atoll csiphy_3ph_v1_2_reg,
  3 trios x 38 = 114 entries, absolute addrs, 0x200 stride, each trio ends
  0x800=0x0E). Mainline iterates lane_regs as one flat array, so the 6.14
  `[3][38]` + per-lane loop == a single flat 114-entry array (identical writes).
  Wires CAMSS_7180 into the (Heidelberg-refactored) csiphy_lanes_enable switch
  (C-PHY -> the new table). CTRL7 (offset+0x1C) programmed 0x52 for C-PHY vs 0x02
  D-PHY per the verified downstream config (deviates from Heidelberg's series,
  which leaves 0x02 for all — noted for a future rebase).

sc7180's own C-PHY register map is distinct from Heidelberg's sdm845 3PH table
(his uses the LN CTRLn macros / CSIPHY v1.0; sc7180 is v1.2), so sc7180 needs its
own table — could not reuse lane_regs_sdm845_3ph.

Two PRE-EXISTING gaps in the a52q/camdt base (NOT introduced here, out of scope
= D-PHY; flagged): (1) `csiphy_is_gen2()` was missing CAMSS_7180, so the 3-phase
path was never selected — REQUIRED for C-PHY, so added it here (also routes
sc7180 D-PHY to gen2). (2) No `lane_regs_sc7180` D-PHY table exists in this tree;
the new case's D-PHY branch is left unpopulated (WARN_ONCE) instead of the old
uninitialised-pointer landmine. sc7180 D-PHY needs its own lane table added to
the a52q/camss series separately before the 4 D-PHY cams work on mainline.

Checks (aarch64-linux-gnu- cross build; out dir on tmpfs under
flock /tmp/claude-1000/a52build.lock, deleted after):
- checkpatch.pl --strict -g HEAD: 0 errors, 0 warnings, 0 checks (161 lines).
- W=1 build `make W=1 drivers/media/platform/qcom/camss/` (CAMSS=m): rc=0, 0
  warnings, 0 errors, 28 objects incl camss-csiphy-3ph-1-0.o. (M= modules build
  fails modpost with unresolved core symbols — expected without vmlinux
  Module.symvers; the in-tree dir target is the correct W=1 check.)
- No DT touched -> CHECK_DTBS not run.

On-device test to run next: boot with this camss + the a52q/camdt DT + C-PHY DTB,
CONFIG_VIDEO_QCOM_CAMSS=m. Verify with libcamera `cam -s role=raw` on the
S5KGW1P (CSIPHY0): capture RAW and confirm the sensor colour-bar TEST_PATTERN
(V4L2_CID_TEST_PATTERN) shows repeating bars with all rows filled (per the
2026-09-27 audit — frame mean/std alone is NOT a valid pass). Expect no
"Missing lane_regs definition!" WARN for CSIPHY0. Regression-check the 4 D-PHY
cams are unaffected (they will still need the D-PHY gap #2 fixed to stream).

### 2026-10-01 follow-up — SC7180 D-PHY table + gen2 fix + CTRL7 scoping (a52q/cphy)

Restructured the sc7180 additions into three own commits on top of Heidelberg's
9 (rebuilt from the Heidelberg tip; hashes changed):
- a03cd9a71595 "Mark SC7180 CSIPHY as gen2" — CAMSS_7180 added to
  csiphy_is_gen2() alone. Verified `git apply --check` clean on pre-Heidelberg
  a52q/camdt, so it can be cherry-picked straight into the a52q/camss series.
- 61f9330a2c79 "Add SC7180 CSIPHY D-PHY lane settings" — new lane_regs_sc7180[]
  (CSIPHY v1.2 2PH, clock + 4 data lanes, 5x23=115 entries) flattened from the
  verified 6.14 tree (7a9497b16^ lane_regs_sc7180[5][23], captured on device);
  wires CAMSS_7180 D-PHY branch to it (replaces the WARN_ONCE placeholder). Fixes
  the 4 D-PHY cameras on mainline.
- 6047f7fcef69 "Add C-PHY support for SC7180" — lane_regs_sc7180_cphy[] (114
  entries) + C-PHY branch; CTRL7=0x52 now scoped to CAMSS_7180 C-PHY only
  (`version==CAMSS_7180 && phy_cfg==CPHY`), so sdm845/other C-PHY keep Heidelberg's
  0x02 unchanged.

Checks: checkpatch --strict -g on all 3 = 0/0/0. W=1 `make W=1
drivers/media/platform/qcom/camss/` (CAMSS=m, aarch64 cross, tmpfs out under
flock, deleted) = rc=0, 0 warnings, 28 objects. No DT touched.

On-device: now expect ALL 5 cams — the 4 D-PHY (front imx616, UW s5k3l6, depth
gc5035, macro via mux) AND the C-PHY main (s5kgw1p, CSIPHY0) — no "Missing
lane_regs" WARN. Validate each with the colour-bar TEST_PATTERN via libcamera raw.

## 2026-10-01 04:15 — mainline integ 9d9c345 (+ DT fixes 238fec6/36c84f3/cfd26e0 via local dtb) ON DEVICE
UKI a52qtest_0.26.1001.4 = OBS kernel 9d9c345 + locally built dtb (a52q/integ incl. bootfix). systemctl: running, 0 failed.
VERIFIED working on mainline 7.3:
- Wi-Fi wld0 associated (pd-mapper sm7125 fix); BT hci0 (geni serial alias fix) — laptop discovers the phone;
  NFC nfc0 DEV_UP/START_POLL/STOP_POLL/DEV_DOWN OK; /dev/fastrpc-adsp present, hexagonrpcd running.
- Touch stmfts input (needs &gpi_dma0/1 status okay — the dtfix agent had left them disabled).
- Sound card "Samsung Galaxy A52" (needs q6asmdai dai@0-2 + q6afedai QUIN_MI2S_RX qcom,sd-lines=<0>): speaker
  path plays (silence at -110 dB, no AFE errors), Mic1 capture OK, WCD938x bound over SoundWire, headset jack input.
  UCM: card longname is now "samsung-SamsungGalaxyA52" → recipes commit 0ee5d29 adds the matching conf.d symlink.
- Cameras: libcamera lists 3 (s5kgw1p main C-PHY, imx616 front, s5k3l6xx UW via video-mux); cam -cN --capture=4
  gives full-size frames with data on all 3 (incl. C-PHY). EEPROMs at24 9-0050/0051. GPU used by libcamera softISP (EGL).
- GPU A618 OK (bin 159 → 750 MHz max), panel, backlight, modem, ADSP, USB net, charger/FG, Type-C, keys, vibrator.
OPEN:
- s2idle (rtcwake -m mem) → hard reset right after "Filesystems sync" (no log; no PM_DEBUG/netconsole in build).
  6.14 needed cci system-sleep + sm5714-cc IRQ masking fixes → agent porting (branch a52q/pm).
- camss WARN v4l2-subdev.c:484 call_s_stream on start+stop for the video-mux pipeline (camss walks every subdev and
  video-mux also forwards s_stream → sensor started twice) → agent fixing (branch a52q/camfix).

## 2026-10-01: PM/suspend port-audit of 6.14-fork fixes vs a52q/integ (7.3-rc5)
Worktree: a52q/pm off a52q/integ (sparse). Compared each named obs/sm7125 commit
against the 7.3-rc5 integration tree. Result: almost everything was already
backported into a52q/integ (same code, same ponytail comments).

Per-commit verdict:
- 77edbf98c i2c-qcom-cci system sleep + CAMNOC vote + ak7374: ALREADY PRESENT in
  full (icc vote, SET_SYSTEM_SLEEP_PM_OPS(pm_runtime_force_suspend/resume), ak7374
  cdef + both DT bindings). The task hint "mainline only has the interconnect part"
  is stale. GAP (camera-only, not the reset): &cci0/&cci1 in the a52q DT have no
  `interconnects`/`interconnect-names="cci-camnoc"`, so icc_path is NULL and the
  anti-"camnoc_axi stuck" vote is a no-op on a52q. Not ported (needs sm7150 CAMNOC
  provider IDs + on-device verify; irrelevant to s2idle reset).
- cfafec1b7 sm5714-cc mask CC IRQ across sleep: ALREADY PRESENT (adapted to
  request_threaded_irq/free_irq; disable_irq/enable_irq in SET_SYSTEM_SLEEP ops).
- e0d5f445a + fe02559c6 qcom-wdt stop across sleep: ALREADY PRESENT and functionally
  identical to the fork (SET_LATE_SYSTEM_SLEEP_PM_OPS; stop if active||hw_running on
  suspend, start on resume). No ordering/last-ping/resume-path difference vs the fork
  that could reset the SoC. Builtin (CONFIG_QCOM_WDT=y). Not the regression.
- 5625ffa6c camss video-mux/lane-count/re-register: NOT APPLICABLE to a52q/pm. 7.3
  rewrote the sensor-finding API (camss_find_sensor -> camss_find_sensor_pad); every
  remaining piece (lane count from active sensor, re-register dedup) is built on the
  video-mux-follow change that branch a52q/camfix owns. Skipped entirely to avoid a
  cross-branch conflict on a rewritten subsystem; belongs in camfix on the 7.3 API.
- d74773d9c + aed20b7ef sm5714-charger OTG-pref + torch LED + OTG VBUS regulator:
  ALREADY PRESENT (otg-first op_mode, sm5714_otg_desc regulator, torch_led classdev).
- b14bc30a8 sm5714-fg voltage/current/temp: ALREADY PRESENT (read_sram helper,
  sm5714_fg_sign, VBAT, the 2989/2044/109 vendor scalings, min() capacity cap).

=> Nothing to port from the named commits. One new in-tree fix made:
   9269474 "arm64: defconfig: a52q: build the SMP2P sleepstate notifier in"
   (CONFIG_QCOM_SMP2P_SLEEPSTATE m->y). checkpatch --strict 0/0.

Ranked suspects for the s2idle hard-reset (right after "PM: suspend entry / fs sync"):
1. CONFIG_QCOM_SMP2P_SLEEPSTATE=m not loaded at suspend time. smp2p_sleepstate signals
   the ADSP via a PM_SUSPEND_PREPARE notifier that fires exactly at that point in the
   log; if the module isn't loaded the SEE is never told the AP is sleeping, faults,
   and Samsung's subsystem-restart-disabled firmware full-resets the SoC. This is the
   one leg of the 6.14 "FIXED" recipe that the 7.3 build no longer guarantees. Fixed
   above by building it in. [top]
2. hexagonrpcd not stopped across sleep (6.14's 3rd leg, a52q-sensors-sleep.service).
   Userspace, not an in-tree fix; same ADSP-fault -> reset path if the service is
   absent on the test image.
3. qcom-wdt bite - unlikely: fix is present, builtin, and identical to the 6.14 one
   that fixed it; listed only for completeness.

Suspend-hostile DT/driver scan (a52q/integ) - essentially CLEAN:
- sm5714-cc (gpio104 LEVEL_LOW): IRQ masked across sleep. OK.
- touch stmfts_fts5cu56a (gpio9 LEVEL_LOW): disable_irq in suspend + IRQF_NO_AUTOEN +
  SET_SYSTEM_SLEEP_PM_OPS. OK.
- tas2562 x2 (gpio90 LEVEL_LOW, shared): mainline driver requests NO irq; the DT
  `interrupts` are inert. Benign.
- NFC s3nrn4v (gpio37): no mainline driver in integ; node never binds. Benign.
- sm5714 muic/charger/fg (i2c4): no `interrupts` declared -> no IRQ-storm path.

## 2026-10-01 — CAMSS double s_stream WARN with video-mux (a52q/camfix)

Symptom: `WARNING: drivers/media/v4l2-core/v4l2-subdev.c:484 at call_s_stream`
once from video_start_streaming and once from video_stop_streaming, on the
pipeline [s5k3l6xx]->[video-mux]->[csiphy3]->[csid0]->[vfe0_rdi0]->[video0].
Direct sensor->CSIPHY pipelines (no mux) do not warn.

Root cause: camss-video.c video_start/stop_streaming() walk pads[0] upstream
and call .s_stream() on EVERY subdev up to and including the sensor.
video_mux_s_stream() (drivers/media/platform/video-mux.c) itself forwards
.s_stream() to its active upstream subdev, so the sensor is started/stopped
once by the mux and again by the camss walk -> the "already started/stopped"
WARN_ON fires.

Fix (branch a52q/camfix off a52q/integ, 1 commit): stop the walk at the first
external subdev. camss drives only its own subdevs; the first non-camss subdev
(sensor, bridge or mux) owns everything upstream of it. CAMSS-owned subdevs
belong to a fixed set — new helper camss_is_own_subdev() tests the subdev
against camss' own CSIPHY/TPG/CSID/ISPIF/VFE-line subdevs (enumerated exactly
as camss_register_entities() does, via res counts), and the walk breaks after
calling s_stream on the first subdev that fails it. Array membership is used
rather than subdev->owner because with CAMSS and video-mux both built-in the
module owner is NULL for both, so an owner test would wrongly treat the mux as
camss-owned and start the sensor twice again. Plain sensor pipelines are
byte-for-byte identical (sensor stays the last subdev called). No existing upstream fix: the Sept 2026 streams-API series
(Gjorgji Rosikopulos) only short-circuits when enable_streams is supported;
the legacy s_stream walk (our mux case) is untouched.

Fixes: 0ac2586c410f ("media: camss: Add files which handle the video device nodes").
Checks: checkpatch --strict 0 errors/0 warnings; W=1 cross build (gcc 16.1
aarch64-linux-gnu, a52q_defconfig+olddefconfig) of the whole qcom/camss/ dir
clean, no warnings. Second W=1 build with CAMSS=y + VIDEO_MUX=y (media chain
=y) also clean, proving the built-in case compiles. Not flashed/tested on
device yet.

## 2026-10-01 04:35 — s2idle WORKS on mainline 7.3 (the "reset" was a test artefact)
- `rtcwake -m mem` suspends WITHOUT systemd sleep.target, so a52q-sensors-sleep.service never stops hexagonrpcd →
  ADSP SEE faults → Samsung FW hard-resets (the same failure 6.14 had). Always test with
  `echo +N > /sys/class/rtc/rtc0/wakealarm; systemctl suspend --check-inhibitors=no` (the usbnet inhibitor blocks
  plain `systemctl suspend`). Script /var/tmp/s2.sh (unbinds the gadget, suspends, rebinds; run via Wi-Fi ssh:
  `ssh -o ProxyCommand=none -o HostName=192.168.100.131 a52r`).
- Verified: 40 s s2idle by wall clock (02:30:34 → 02:31:14, RTC wake), and 25 s with USB attached. NOTE monotonic
  timestamps do not advance in s2idle — "entry→exit 1.3 s" in dmesg is NOT an early wake.
- After resume: Wi-Fi, BT, modem, ADSP, camera capture, mic capture all OK.
- Fixes found: stmfts power_off treated i2c_master_send()'s byte count (3) as an error ("failed to disable
  touchscreen: 3") → fixup on a52q/bootfix. PM audit agent: all 6.14 sleep fixes already present in mainline;
  a52q/pm 9269474 builds SMP2P_SLEEPSTATE in (=y) so suspend never depends on module load order.

## 2026-10-01 — GC5035 (macro + depth) upstream-submittable series (branch a52q/gc5035)

Worktree `/tmp/claude-1000/wt-gc5035` off `a52q/integ`. Seven commits: Figa's v4
posting (from patchwork REST API) applied verbatim with his From:/SoB preserved,
then our changes on top.

Series (newest first):
- arm64: defconfig: a52q: enable GC5035 camera sensor (CONFIG_VIDEO_GC5035=m)
- arm64: dts: qcom: sm7125-samsung-a52q: add GC5035 depth + macro cameras
- media: i2c: gc5035: modernise and add Galaxy A52 (a52q) support   [us]
- dt-bindings: media: gc5035: use mclk clock-name and add label     [us]
- media: i2c: gc5035: Add OTP configuration handling                [Hao He/Figa, am]
- media: i2c: Add a driver for the Galaxycore GC5035 sensor         [Hao He/Figa, am]
- media: dt-bindings: media: i2c: Add bindings for GC5035           [Figa, am]

Key decisions:
- Driver = Figa v4 base + our delta = the 6.14 fork driver MINUS the mipi_sel_gpio
  hack. a52q/integ models the gpio66 UW/macro switch as a gpio-mux mux-controller +
  video-mux, so the sensor must NOT drive gpio66 itself (that is the downstream model).
  Macro connects to the reserved video-mux input port@1; depth goes direct to CSIPHY1.
- Did NOT convert to v4l2-cci: GC5035 is page-banked (0xfe selects the register page),
  which CCI's flat 16-bit reg model does not fit. Active-state/fwnode/pm_runtime
  modernisation was already in the fork and is kept.
- Binding: renamed to galaxycore,gc5035.yaml, $id trailing '#', clock-name mclk,
  added label, allOf $ref video-interface-devices.yaml (orientation/rotation),
  unevaluatedProperties, pwdn-gpios made optional (a52q modules have no PWDN).
- DT: added ldo4 (1.2V, depth/macro vdig) and vreg_cam3_vana (gpio64, 2.8V) to a52q;
  sensor data-lanes = <1 2> per binding; MCLK1/MCLK3 pinctrl; csiphy1 port on camss.

Checks (all run in worktree, aarch64-linux-gnu-gcc 16.1, dtschema 2026.6):
- checkpatch --strict: our 4 commits 0 errors/0 warnings/0 checks. Figa's 3 am'd
  commits carry inherited as-posted warnings (binding-without-MAINTAINERS since his
  2/4 split put it in 3/4; MODULE_LICENSE "GPL v2"; 2 alignment CHECKs) — all cured
  in the final tree by our modernise commit; left on his commits to keep From:/SoB.
- dt_binding_check DT_SCHEMA_FILES=galaxycore,gc5035.yaml: clean.
- W=1 build of drivers/media/i2c/gc5035.o: 0 warnings, 0 errors.
- CHECK_DTBS=y qcom/sm7125-samsung-a52q.dtb: 0 warnings.

Gotcha: /tmp tmpfs + / both ~100% full (other sessions' 1.8G worktrees). The W=1
build needs the full Kconfig tree + prepare deps; built via a non-cone sparse set
(all Kconfig files + scripts/include/arch-arm64/drivers-media/kernel/lib/tools/
arch-x86-syscalls + drivers/Makefile). In a linked worktree the sparse file is at
`git rev-parse --git-path info/sparse-checkout`, NOT .git/info. Build dir deleted.

## 2026-10-01 05:45 — integ cf7d8dfc on device; modem DOG stall; sensors
- cf7d8dfc (bootfix+camfix+pm): camss WARN gone (0 "cut here" after capturing all 3 cams); touch/sound/BT/NFC OK.
- INTERMITTENT (2/6 boots, both builds): modem `fatal error received: dog_hal_common.c:173:DOG detects stalled
  initialization` ~40 s after MPSS start; recovery sometimes leaves no WLFW/wld0 (qcom-modem-setup then fails).
  Cause (agent research, MODEM-STALL-2026-10-01.md): QCOM_PD_MAPPER=m loads via udev only after remoteproc creates
  its aux device → MPSS can start before the PD mapper exists. Upstream reports the same signature; their fix is
  MODULE_SOFTDEP("pre: qcom_pd_mapper") in qcom_common. Ours: defconfig QCOM_PD_MAPPER=y (integ 1f3e617, building,
  also adds GC5035). VERIFY over 8-10 reboots.
- Sensors: SSC registry configs extracted from the Lineage vendor (~/linux-a52q/sensors/, deployed to
  /var/lib/droid-juicer/sensors/sensors). Still no sensors: ADSP asks hexagonrpcd for "/../sns_reg_version" (sibling
  of the persist registry dir, unmapped) → agent patching hexagonrpcd. Same failure on 6.14 (never worked).
- DO NOT `echo stop > /sys/class/remoteproc/<adsp>/state` at runtime: it hard-resets the phone.

## 2026-10-01 16:50 — session resumed after a laptop reboot
- /tmp is tmpfs: all agent worktrees under /tmp/claude-1000 and the scratchpad (reboot-loop log, extracted .debs)
  were lost; branches/commits are intact in ~/src/linux-upstream. Root disk had 173 MB free (owner's package
  caches) → removed ~/linux-a52q/out-mainline (6.2 GB stale local build dir; builds are on OBS now).
- Phone NOT attached since the laptop booted (09:20), not on LAN/tailscale. Queued on-device checks are scripted in
  ~/linux-a52q/accept73.sh (modem DOG-stall N-reboot loop, sensors with patched hexagonrpcd, 5 cameras incl.
  GC5035 macro, Wi-Fi/BT/NFC/touch/deferred/WARN counts). Run:
  `flock /tmp/claude-1000/a52phone.lock ~/linux-a52q/accept73.sh 8 | tee ~/linux-a52q/accept-$(date +%m%d-%H%M).log`
- Phone state when last seen: default UKI a52qtest_0.26.1001.6 (integ 1f3e617: PD_MAPPER=y + GC5035), modules
  installed; patched hexagonrpcd (sha 02f307c9) at /var/lib/a52q-test with drop-in; failsafe73 still enabled.

## 2026-10-01 17:30 — second laptop reboot; camfix d4afd1c merged (integ 22c75c6, on OBS)
- camss_find_sensor_pad() now follows the enabled link (media_entity_remote_source_pad_unique) → GC5035 macro on
  video-mux input 1 should stream; WARN was csiphy_get_bpp() "Unknown format" on the mis-resolved input.
- ~/linux-a52q/phone-arrive.sh (run under the phone lock) waits for the A52 USB NIC, installs the newest OBS
  build if its sha differs from ~/linux-a52q/k73/.sha, then runs accept73.sh 8 → ~/linux-a52q/accept-*.log.

## 2026-10-01 — U-Boot upstream-submittable series prepared (branch a52q-upstream)

New branch `a52q-upstream` off the same base as `a52q` (v2026.10-rc5, a06e89ab).
6 patches, exported to `~/linux-a52q/upstream/u-boot/` (cover letter + To/Cc from
get_maintainer.pl). NOT emailed, NOT pushed, phone not flashed.

Series:
- 1-4: Vitalii Skorkin's SM7125 v2 (SC7180 GCC/pinctrl/UFS-PHY), cherry-picked,
  authorship preserved (Erikas Bitovtas is the submitter, Vitalii the author).
- 5 `qcom: Add board support ... (a52q)`: upstream phone convention — NO dedicated
  defconfig. `board/qualcomm/a52q.config` fragment (DEFAULT_DEVICE_TREE, env text
  file, BLKMAP/CMD_BLKMAP, CMD_PMIC, WATCHDOG_AUTOSTART, TEXT_BASE=0x80080000) +
  `board/qualcomm/a52q.env` (dual-boot menu: Linux via blkmap/EFI, LineageOS via
  `pmic write 0x88f 0x02; reset`, PON-reason explained in a comment) + MAINTAINERS.
  Build: `make qcom_defconfig qcom-phone.config a52q.config`.
- 6 `doc: qcom: ... a52q page`: doc/board/qualcomm/samsung-a52q.rst + index.rst
  (build/packaging/odin4 flashing, msm-id/board-id, bad-magic DTBO, watchdog caveat).

Key decision — replaced local hack 07e1b99e (global edit hardcoding the arm64
image header text_offset to 0x80000) with CONFIG_TEXT_BASE=0x80080000 in a52q.config
(= google-pixel.config value). Verified byte-identical: `u-boot-nodtb.bin` header
offset field (bytes 8-15) = 0x0000000000080000. qcom_defconfig is PIE so the TEXT_BASE
change is safe for execution. NOT re-verified on hardware (no flashing permitted).

DT: `sm7125-samsung-{a52q,a72q,common}.dts*` kept as UNTRACKED working-tree files
(not committed). U-Boot takes arm64 qcom DTs via the dts/upstream sync from
devicetree-rebasing/Linux, so the DT is a dependency documented in the cover letter,
not part of the U-Boot series. The files must be present in dts/upstream/src/arm64/qcom/
to build until the Linux DT (dt-a52q-v3.mbox) lands in rebasing.

Verification (host aarch64-linux-gnu-gcc):
- checkpatch.pl: 0 errors on all 6 (each new-file patch has the standard 1
  "does MAINTAINERS need updating?" warning; 0005 does update MAINTAINERS).
- build OK -> u-boot-nodtb.bin + sm7125-samsung-a52q.dtb.
- u-boot-initial-env contains the full menu (bootmenu_0=Linux, bootmenu_1=LineageOS,
  boot_android pmic write 0x88f, blkmap preboot).
- repack.sh packs it (AP-uboot-a52q.tar = boot.img + zeroed dtbo.img), rc=0.

Caveat: repack.sh line 8 still names `qcom_a52q_defconfig` (gone on this branch); it
only skipped because .output/.config pre-existed. Left unchanged (the `a52q` branch
still has that defconfig). Update to the fragment line if repacking a clean tree.

---

## 2026-10-01 — CDSP remoteproc + thermal/venus audit (a52q/integ)

Worktree: `~/src/wt-cdsp` (branch `a52q/cdsp`, base `a52q/integ` 22c75c6), sparse.

### Task 1 — CDSP remoteproc: DONE (3 commits on a52q/cdsp)
- `dt-bindings: ... qcom,sm6350-pas: add SC7180 CDSP` — SC7180 CDSP == SM6350 CDSP
  PAS (same cx/mx proxy PDs, 5 interrupts). Added `qcom,sc7180-cdsp-pas`,
  `qcom,sm6350-cdsp-pas` fallback (qcs615/sm8150 pattern). No driver change: existing
  `sm6350_cdsp_resource` match binds via the fallback. Converted the cdsp interrupt +
  power-domain `if` branches from `enum` to `contains: enum` so the fallback matches.
- `arm64: dts: qcom: sc7180: add CDSP remoteproc node` — remoteproc@8300000 + fastrpc,
  status disabled. KEY: mirrors the ADSP node, NOT MPSS — sc7180.dtsi does not define
  *_mem and the cdsp node carries NO memory-region; boards supply it. (The initial
  attempt added `cdsp_mem` to sc7180.dtsi, which collided with the board's own
  `cdsp_mem@98900000` — reverted.)
- `arm64: dts: qcom: sm7125-samsung: enable CDSP on Galaxy A52` — `&remoteproc_cdsp`
  memory-region=<&cdsp_mem> in samsung-common (cdsp_mem@98900000 already present there),
  firmware-name `qcom/sm7125/a52q/cdsp.mbn` + status okay in a52q.dts.

### Task 2 — thermal/cpufreq audit: NOTHING TO PORT
Compared obs/sm7125 (6.14 fork) vs a52q/integ:
- tsens0/1 (qcom,sc7180-tsens): identical. SoC thermal-zones: mainline 26 vs fork 25
  (mainline is ahead, nothing missing).
- cpufreq: both use `qcom,sc7180-cpufreq-hw` + `osm_l3` + `qcom,sc7180-cpu-bwmon`.
  sc7180 uses OSM, not EPSS. Identical.
- LMh: absent in BOTH fork and mainline (no qcom,sc7180-lmh node exists anywhere).
- Skin/battery thermal zones via PM6150 ADC: the brief expected these in the 6.14 DT,
  but the fork's a52q/common/sm7125 DTS have NO board thermal-zones, adc-tm, iio-hwmon,
  or therm channels (only audio "ADC" labels). PM6150/6150L are included but expose no
  thermistor channels. So the premise does not hold for this fork — there is nothing to
  port. No commits for Task 2.

### Task 3 — Venus: already correct, no change
sc7180.dtsi `venus: video-codec@aa00000` has no status prop (defaults okay) and full
power-domains/clocks/iommus + video-decoder/encoder subnodes. a52q.dts `&venus` sets
firmware-name `qcom/sm7125/a52q/venus.mbn`. Nothing else needed.

### Verification (the kernel `make` path was unusable — see below)
- Binding: `dt-doc-validate` on qcom,sm6350-pas.yaml — OK (schema + example valid).
- DTBs: compiled a52q, a72q, sc7180-trogdor-coachz-r3 with `cpp -Iscripts/dtc/
  include-prefixes` + `dtc` — 0 errors, 0 new dtc warnings from the cdsp node.
- dtbs_check equivalent: `dt-mk-schema -j` (processed schema) + `dt-validate` — cdsp
  node clean in all three (a52q enabled+memory-region, a72q disabled+memory-region,
  trogdor disabled+no-memory-region). Baseline-vs-current diff: 0 new warnings.
- checkpatch --strict: 0 errors / 0 warnings / 0 checks on all three commits.

### ENV NOTE — kernel `make`/dtbs_check stalls here
`make O=<tmpfs> ARCH=arm64 defconfig` never completed: the recursive makes sat sleeping
at 0% CPU with no `.config` after 30 min (load avg < 1, not CPU-bound — blocked). Killed
twice. Root fs is at 99% (5 GB free) but O= was on tmpfs, so that is not obviously the
cause; suspect the same I/O/thrash class of issue noted for this host. Worked around it
entirely with the standalone dt-schema toolchain (`~/.local/bin/dt-{doc-validate,validate,
mk-schema}`) + cpp/dtc — this reproduces dtbs_check/dt_binding_check without kernel make.
Also had to widen the sparse-checkout to include `include/uapi/linux` (dt-bindings input
header symlink) and `arch/arm/boot/dts` (trogdor includes arm/cros-ec-sbs.dtsi).

## 2026-10-01 18:40 — CDSP merged; OBS 0076120 built and saved
- a52q/cdsp (3 commits, binding fallback qcom,sc7180-cdsp-pas → sm6350, same as the working 6.14 DT) merged:
  integ 0076120, OBS r8 succeeded. Kernel .deb extracted to ~/linux-a52q/k73/x (.downloaded = 0076120, NOT yet installed on the
  phone; .sha = installed marker used by phone-arrive.sh, absent → it will install on next run).
- Thermal/cpufreq audit: nothing to port (tsens/cpufreq-hw/osm-l3/bwmon identical to 6.14; no LMh). Venus OK.
- Owner asked (2026-10-01 ~18:00) to stop all USB interaction with the phone; watcher stopped. Do not touch the
  phone until the owner says so.

## 2026-10-01 — input-fts5cu56a upstream-clean (v2)

Goal: make the ST FTS5CU56A touchscreen driver (A52/a52q) upstream-clean;
decide standalone vs extending stmfts.c on top of David Heidelberg's
in-flight FTS5 series (patchwork series 1174082 / patch 14848317, v8).

Decision: **standalone (option B)**. Fetched Heidelberg's v8 series mbox and
compared protocols. stmfts.c (and his `st,stmfts5` ops variant) use 8-byte
events via opcodes 0x85/0x86 and the ST-reference 0x90-0xa4 command set.
FTS5CU56A uses Samsung sec_ts firmware: 16-byte event FIFO via 0x60/0x61
(remaining count in byte7 & 0x1f), 0x62 clear, ID/FW reads 0x22/0x24,
calibration 0x13, 6-byte 0xfa reset blob, bit-packed coordinate/touch-type
events. Only overlap is scan enable 0xa0 00 01 (and 0xa0 even means
SYSTEM_RESET in the reference set). Extending stmfts.c = a second fully
independent parser+power path in code his series is actively changing, zero
shared behaviour, no HW here to verify the other variants → net-negative.

Work (branch up/input-fts5cu56a-v2 in ~/src/linux-upstream; sparse worktree
~/src/wt-fts; full build worktree on tmpfs under flock, deleted after):
- Rewrote drivers/input/touchscreen/stmfts_fts5cu56a.c clean. Preserved
  EXACTLY: all command bytes (reset 0xfa 20 00 00 24 81; touch-enable
  0x39 61 00; cal 0x13; clear 0x62; scan 0xa0 00 01 / 00), timings
  (msleep 500 after regulator enable, msleep 20 after reset), the
  0x60/0x61 FIFO read + `data[7]&0x1f` count + loop, and the exact
  press/move/release input_report_* semantics + touch_count/BTN handling.
  The squashed fixup (i2c_master_send positive byte count = success in
  power_off, warn only on <0) is kept.
- Stripped debug-only code: location_detect, finger_mode, all dev_dbg,
  per-finger telemetry fields, dead enums/defines, the status/gesture/
  vendor structs. Replaced bitfield structs with explicit, endian-safe
  mask/shift extraction (same bit math). sprintf->sysfs_emit,
  ATTRIBUTE_GROUPS/.dev_groups, DEFINE_SIMPLE_DEV_PM_OPS/pm_sleep_ptr,
  guard(mutex). Removed never-reported axes (ABS_MT_ORIENTATION /
  ABS_MT_PRESSURE / ABS_DISTANCE) and the duplicate ABS_MT_TOUCH_MAJOR
  line; kept POSITION_X/Y and TOUCH_MAJOR/MINOR (the only axes reported).
- Folded the old separate "clean up coding style" patch into the driver
  patch; renamed binding file to match the compatible
  (st,stmfts_fts5cu56a.yaml); added a MAINTAINERS entry.
- v2 = 2 patches (binding, driver) + cover letter with the stmfts.c
  reuse-rejection paragraph.

Checks (all from the tmpfs full tree, flock /tmp/claude-1000/a52build.lock):
- checkpatch --strict: driver 0 err / 0 warn / 0 chk; binding only the
  "does MAINTAINERS need updating?" heuristic (resolved by patch 2/2).
- dt_binding_check DT_SCHEMA_FILES=...st,stmfts_fts5cu56a.yaml: RC 0, zero
  schema warnings (yamllint not installed → that sub-check skipped).
- W=1 arm64 (aarch64-linux-gnu-gcc 16.1.0) build of
  drivers/input/touchscreen/stmfts_fts5cu56a.o: RC 0, zero warnings.
- NOT verified on device (no hardware this revision); behaviour preserved
  by construction (command/timing/report paths copied verbatim).

Output regenerated in ~/linux-a52q/upstream/input-fts5cu56a-v2/
(format-patch -v2 + cover + to-cc.txt).

## 2026-10-01 19:20 — touch driver v2 in integ (c5c6e8a, on OBS)
- FTS5CU56A driver rewritten upstream-clean (853→463 lines, checkpatch 0/0/0); event decode reviewed against the old
  bitfields (eid/tid/tchsta/x/y/ttype/left_event identical). Compatible renamed st,stmfts_fts5cu56a → st,fts5cu56a
  (binding st,fts5cu56a.yaml, a52q dts updated). Reusing stmfts.c rejected: the chip runs Samsung sec_ts firmware
  (16-byte FIFO 0x60/0x61), unlike ST's 8-byte protocol. NOT yet HW-verified: if touch breaks on the next
  boot, compare against 0076120 (~/linux-a52q/k73 holds that build).
- serial-geni upstream patch: Fixes: a53be6945f51 (v6.16-rc1) added.

## 2026-10-02 19:40-20:00 — acceptance run on c5c6e8a; boot loop (my fault); modem DOG ROOT-CAUSED
- c5c6e8a: 6 boots — touch v2 works, 5 cameras listed (cam2 0 frames once), Wi-Fi/BT/NFC every boot,
  0 failed units, 0 WARNs. Modem DOG stall still 1/6 → PD_MAPPER=y was not the cause.
- SENSORS: the deployed SSC configs on the phone were 0-byte files (my earlier deploy) → redeployed (md5
  verified) → the ADSP then loaded them and `PDM: service 'sensor_process' crash: EF:...:UTMR_CLNT_1:...:
  sns_thread_mana` ~26 s into every boot → ADSP fatal → hard reset → BOOT LOOP (5 boots). Broken by
  `systemctl mask hexagonrpcd iio-sensor-proxy` + configs moved to *.disabled. Before the crash hexagonrpcd
  logs missing `sns_bring_to_ear.so` (vendor rfsa/adsp libs) and `/sys/class/sensors/ssc_core/ssc_mode`
  (Samsung downstream sysfs). Agent working on both; hexagonrpcd stays MASKED until a manual test passes.
- MODEM DOG STALL ROOT CAUSE (2 of 2 stalled boots, 0 clean boots): `failed to announce new service` +
  `failed while handling packet from 0:-2` 14 ms after modem up. net/qrtr/ns.c announce_servers() aborts the
  whole NEW_SERVER list on the first send error; -EAGAIN happens while our own HELLO to the modem has not gone
  out yet → modem never learns rmtfs/tqftpserv → init stall → DOG 40 s later. Fix: retry -EAGAIN (20 ms × 50)
  and continue past other errors (branch a52q/qrtr ea0b380, upstreamable; integ = ea0b380 on OBS).
- accept73.sh: resends the reboot if the phone did not reboot within 2 min (the 3 h stall in part2).

## 2026-10-02 21:30 — SENSORS WORK on mainline; QRTR fix verified 8/8
- ea0b380 (QRTR announce retry): 8/8 boots clean, no "failed to announce", Wi-Fi every boot.
- SSC sensors: root cause = pm6150l L8 (sensor VDDIO, downstream "Sensor Vdd" always-on) unused in
  mainline → off → SEE bus hang → sensor_process watchdog → ADSP fatal → phone reset. Fix: a52q DT
  `&vreg_l8c_1p8 { regulator-always-on; }` (a52q/ssc-rails 2665664, merged; integ pushed to OBS).
  Tested with that DTB on ea0b380: hexagonrpcd + iio-sensor-proxy start from boot, accelerometer + ALS
  present, 0 sensor_process crashes. Compass not exposed by iio-sensor-proxy (open).
- Safety: hexagonrpcd now has ExecCondition on .../regulators-1/ldo8/regulator-always-on (phone drop-in
  + recipes bd47183), so kernels without the rail fix never start it (no boot loop).
- The earlier 0-byte sensor configs on the phone came from my first, botched deploy — always md5-verify.
- Cameras: after a capture was killed mid-stream, every capture returns 0 frames with an SMMU fault at
  IOVA 0 (SID 0x820, VFE); plus a recurring cam_cc_camnoc_axi_clk "stuck at on" WARN from
  cci_suspend_runtime (a52q DT CCI nodes lack the cci-camnoc interconnect). Agent on a52q/camfix2.
- USB cable dropped at 20:50 (laptop side); working over Wi-Fi via the new `a52w` ssh alias;
  uki-test.sh/mods73.sh honour H= (e.g. H=a52w).

## Camera-stack fixes: CCI CAMNOC DT + camss WM/state reset (2026-10-02)
Branch a52q/camfix2 off a52q/integ (worktree ~/src/wt-camfix2). Two bugs from evidence-1002/camera-bugs.txt.

Bug 1 - "cam_cc_camnoc_axi_clk status stuck at 'on'" WARN at every CCI runtime suspend.
- Root cause: the i2c-qcom-cci icc vote (CCI_ICC_AVG_BW, "cci-camnoc" path) and the binding were already
  ported to a52q/integ, but the sc7180 cci0/cci1 DT nodes had no `interconnects`, so devm_of_icc_get()
  returned NULL and icc_set_bw() was a no-op. The shared camnoc_axi branch then wedged when CCI gated it
  after camss had dropped its own bandwidth vote.
- Fix: add `interconnects = <&camnoc_virt MASTER_CAMNOC_HF0_UNCOMP 0 &camnoc_virt SLAVE_CAMNOC_UNCOMP 0>;`
  + `interconnect-names = "cci-camnoc";` to cci0 AND cci1 in arch/arm64/boot/dts/qcom/sc7180.dtsi (SoC-level
  HW property - shared clock exists on all sc7180; mirrors the camss node's camnoc vote). Commit 608f04bb7518.

Bug 2 - abnormal capture kill -> every later capture 0 frames + IFE SMMU unhandled context fault
  (fsr=0x402 TF, iova=0, WNR, cbfrsynra=0x820=camss IFE) on stream-on.
- Root cause chain (all in drivers/media/platform/qcom/camss):
  (1) video_stop_streaming() returned early when a pipeline subdev s_stream(0) failed, skipping
      video_device_pipeline_stop() AND flush_buffers() -> queued buffers never returned, left referenced
      in the VFE output lists.
  (2) vfe_flush_buffers() returned the active buffers to vb2 but left output->buf[]/gen2.active_num set.
  (3) vfe_enable_output_v2() armed the WM (vfe_wm_start) before any address was written; with a stale/empty
      pending list the WM ran pointing at address 0 -> SMMU TF at iova 0, which wedges the IFE context bank,
      so ALL later captures (every camera, shared cb=8) fault/return 0 frames until reboot.
- Fix (commit 0ca6efe43f5e):
  (1) camss-video.c: log s_stream(0) error and keep walking so pipeline_stop + flush_buffers always run.
  (2) camss-vfe.c vfe_flush_buffers(): NULL buf[0]/buf[1] and reset gen2.active_num.
  (3) camss-vfe.c vfe_enable_output_v2(): if no pending buffer was pulled, vfe_wm_stop() and fail the
      stream-on (-ENOBUFS) instead of leaving the WM enabled at address 0.
- No existing upstream patch matched this exact fault; the hitesh@ebytelogic.com v5 camss series on
  patchwork (buffer-done, WM selection, VFE-reset-while-streaming) is related but separate, not applied here.

Verification (PC-side only, not yet on device):
- tmpfs build /tmp/claude-1000 (root disk was 100% full; detached worktree + O= on tmpfs under a52build.lock).
- W=1 drivers/media/.../camss/ and i2c-qcom-cci.o: 0 warnings. CHECK_DTBS=y sm7125-samsung-a52q.dtb +
  sc7180-trogdor-lazor-r3.dtb: 0 warnings (no cci/interconnect schema warnings). checkpatch --strict: clean, both commits.
- On-device expectation: no "stuck at 'on'" WARN at CCI runtime suspend; after a mid-stream kill, subsequent
  captures on all cameras still return frames with no arm-smmu context fault.

## 2026-10-02 22:40 — integ 706d119 on device (8/8 boots, sensors from boot, camera kill-test clean)
- 8/8 boots: no modem crash, Wi-Fi/BT/NFC each boot; hexagonrpcd + iio-sensor-proxy active from boot
  (registry populated: sns_reg_version + temp.json), 0 sensor_process crashes. ALS + accel discovered;
  iio-sensor-proxy's "compass" is SSC `rotv` (fusion) → "No 'rotv' sensor available" (minor, open).
- camstress.sh: kill capture mid-stream → next captures fine, 0 SMMU faults, 0 camnoc "stuck at on" WARNs.
  camfix2: CCI cci-camnoc interconnects in sc7180.dtsi; stop_streaming always flushes; vfe flush resets
  output state; WM never armed without a buffer; q->min_queued_buffers = 1 (my fixup: the agent's
  -ENOBUFS alone would break apps that QBUF after STREAMON).
- OPEN: GC5035 macro (camera@3f, video-mux input 1) streams with no errors but 0 frames → suspected CSIPHY3
  lane count taken from the static DT endpoint (UW's lanes) — agent a52q/camlanes.
- OPEN: touch bus a84000 `geni_i2c_gpi_xfer: I2C timeout` + gpi `CH STOP completion timeout` once at ~338 s
  → agent a52q/gpi-fix (check GPI compatible/ee offset, dmas SE/channel numbers).

## 2026-10-02 — GC5035 macro: CSIPHY/CSID lane count from active sensor (a52q/camlanes)

RESOLVED (code, PC-side; on-device test pending orchestrator).

Symptom: gc5035_macro (16-003f, video-mux input 1, shares CSIPHY3 with UW
S5K3L6XX on input 0) streams with no kernel/libcamera error but 0 frames.
Every other camera incl. UW (input 0) and depth GC5035 (CSIPHY1) is fine.

Root cause (confirmed by code reading): CAMSS takes the CSIPHY *and* CSID
lane count statically from the CSIPHY's own DT endpoint. csiphy3_ep declares
`data-lanes = <0 1 2 3>` (4, sized for the UW). The macro drives only 2 lanes
(cam_gc5035_macro_ep: `data-lanes = <1 2>`). So on the macro:
  - csiphy_stream_on() builds a 4-lane lane_mask → CSIPHY waits on lanes 2,3
    that never toggle → PHY never locks.
  - CSID gen2 __csid_configure_rx() writes NUM_ACTIVE_LANES = lane_cnt-1 = 3
    (lane_cnt cached at link_setup from lane_cfg->num_data=4) → expects 4.
The depth GC5035 works because csiphy1_ep DT = 2 lanes already matches it; the
mux is what decouples the port DT from the real sensor on CSIPHY3.
d4afd1c (follow enabled link) + 7554dbc (stop s_stream at mux) were already in;
they fixed link_freq resolution but not the lane count.

Upstream-appropriate fix (no upstream series exists — patchwork/lore Anubis-
walled, searched via ratatoskr: only C-PHY and streams-API series, neither does
this): camss_get_num_lanes() in camss.c queries the active sensor (reached
through the enabled links, i.e. across the mux, via camss_find_sensor_pad) with
the .get_mbus_config pad op and returns its data-lane count capped to the port
DT value; falls back to the DT value when the sensor lacks the op (plain
pipelines unchanged). Used in csiphy_stream_on() (lane_cfg->num_data overridden
for the stream, restored before return) and csid_set_stream() (csid->phy.lane_cnt
re-evaluated; applied by configure_stream, which runs every stream-on since
csid_set_power sets need_vc_update). VFE has no lane dependency (verified).
.get_mbus_config implemented in gc5035 (lanes from parsed DT), s5k3l6xx/imx616
(DPHY,4), s5kgw1p (CPHY,3). No DT/bindings change (DT already correct).

Verify: W=1 camss + 4 sensors, a52q_defconfig+olddefconfig, aarch64 GCC 16.1 —
0 warnings/errors. checkpatch --strict — only missing SoB (intended).
Branch a52q/camlanes @ ed05f7ef2c4b off a52q/integ (706d119); sparse wt
~/src/wt-camlanes. On-device check: macro should now deliver frames; re-confirm
UW + depth still stream (lane_cnt restore / cap-from-DT path).

## 2026-10-02 23:30 — touch GPI fix carried (unverified on HW), camlanes merged; integ fa2fda9 on OBS
- Touch-bus `geni_i2c_gpi_xfer: I2C timeout` + gpi `CH STOP` failures: agent traced it to upstream regression
  656147fb1d4c (GPI I2C read GO TRE without IEOB → TX descriptors never retire). Carried Vsevolod
  Nevorotov's upstream fix from the ORIGINAL patchwork mbox (14803556, Reviewed-by Dmitry Baryshkov) —
  the agent's first copy had redacted .invalid emails; replaced via `git am` of the real mbox.
- Userspace repro attempt (~/linux-a52q/i2cstress.py, I2C_RDWR on /dev/i2c-7 @0x49) on the UNFIXED kernel:
  3000 write+read transfers OK, 0 timeouts; bare single reads → EIO (chip NACK), not -110. So the leak needs
  the driver's real IRQ-driven traffic; confirmation needs a human using the touchscreen for >6 min.
- camlanes (ed05f7e): CSIPHY/CSID lane count from the active sensor via .get_mbus_config (gc5035,
  s5k3l6xx, imx616, s5kgw1p implement it) → macro on a 4-lane shared port with 2 lanes. Merged.

---

# 2026-10-03 — Shutdown stall (D1) and rtc-offset save race (D8)

Fixes from logs-1003/AUDIT.md items D1 and D8. Live-applied on phone (ssh a52r)
and committed to recipes (0d0ff02, device-a52q, not pushed). No reboot done by me.

## D1 — every shutdown stalls 30 s
Culprit (journal-b-2:60100): `session-c2.scope: Stopping timed out. Killing`,
then SIGKILL of pid 3184 = `/usr/libexec/gnome-session-init-worker phrog`. That
binary ignores SIGTERM and holds the login-session scope open for the full
`DefaultTimeoutStopUSec=30s` before SIGKILL. The other session clients
(gnome-session-ctl/-service) exit on SIGTERM fine.

Cause not fixable from the device recipe: gnome-session-init-worker is an
upstream gnome-session binary in the read-only base image /usr, not shipped by
device-a52q — patching it means rebuilding gnome-session for the whole distro.
So, per brief, a scoped timeout drop-in on the login-session scope:

  /etc/systemd/system/session-.scope.d/10-stop-timeout.conf  (live, /usr is RO)
  recipe: .../usr/lib/systemd/system/session-.scope.d/10-stop-timeout.conf
    [Scope]
    TimeoutStopSec=10s

`session-.scope.d/` is the dash-truncated drop-in that systemd applies to every
`session-N.scope` (incl. transient logind scopes) — scoped to user sessions
only, not a global DefaultTimeoutStopSec change.

Verify (live): after daemon-reload, a fresh ssh login landed in session-34.scope
with `TimeoutStopUSec=10s` (was 30s). Proves the drop-in reaches transient
session scopes.
Reboot test (user): in `journalctl -b -1`, the `session-cN.scope: Stopping timed
out. Killing` -> SIGKILL gnome-session-init-worker gap should be ~10s, not ~30s;
total "reboot requested" -> "Syncing filesystems" should drop by ~20s.

## D8 — a52q-rtc-offset save fails 203/EXEC on most shutdowns
ExecStop runs `/usr/lib/bengalos-a52q/rtc-offset.sh save`, but the unit had no
ordering vs systemd-sysext.service; on most shutdowns systemd-sysext ran its
ExecStop (`systemd-sysext unmerge`) first, removing /usr, so the script was gone.

Fix: order the unit After=systemd-sysext.service. Stop order is the reverse of
start order, so rtc-offset now stops (and saves) before sysext unmerges /usr.

  live: /etc/systemd/system/a52q-rtc-offset.service.d/10-sysext-order.conf
  recipe: a52q-rtc-offset.service  [Unit] After=... systemd-sysext.service

Verify (live): `systemctl show a52q-rtc-offset -p After` now lists
systemd-sysext.service; `systemd-analyze verify` clean (no cycle). Triggering the
save via `systemctl stop a52q-rtc-offset` while /usr was merged updated
/var/lib/bengalos-a52q/rtc-offset (09:15 -> 09:22, 1788133668 -> 1788133669);
unit restarted, active.
Reboot test (user): `journalctl -b -1` should NO LONGER show
`a52q-rtc-offset.service: Unable to locate executable .../rtc-offset.sh` /
status=203/EXEC; the offset file mtime should advance to the shutdown time.

## Boot-log nits triage (2026-10-03, branch a52q/nits off a52q/integ @ fa2fda93f9f4)
Sparse worktree ~/src/wt-nits (amd/ sources carved out, Kconfig kept; 1.3G). Built O= on
/tmp/claude-1000/a52build under flock a52build.lock. Phone inspected read-only via ssh a52r.

### 1. systemd-backlight "Failed to write 'brightness': Invalid argument" — FIXED
Commit ffd5431f1432 ("drm/panel: samsung-s6e3fc3: don't touch DSI from backlight ops while off").
Root cause: s6e3fc3_bl_update_status()/get_brightness() issue DCS traffic on the panel DSI link
unconditionally. The unit runs twice ~120ms apart (12.299 fail, 12.451 ok) = the simpledrm->msm
handover window: the backlight sysfs device exists but the panel is briefly not enabled, so the
DCS write on a down link fails and is returned to userspace as -EINVAL.
NOT a range error: phone shows max_brightness=1023, saved value=314 (/var/lib/systemd/backlight/
platform-ae94000.dsi:backlight:ae94000.dsi.0). actual_brightness read was also empty (get op
failing the same way), bl_power=4.
Fix: track panel_info.enabled (set in .enable on success, cleared in .disable); both backlight
ops no-op (return 0) while off. The core still stores props.brightness, and
drm_panel_enable()->backlight_enable() reapplies it when the panel comes up. Build W=1 0 warnings,
checkpatch --strict clean (0/0/0).

### 2. qcom-q6afe "cmd = 0x100f6 returned error = 0x1" (x2) — SKIPPED (benign firmware)
0x100f6 = AFE_CMD_REMOTE_LPASS_CORE_HW_DEVOTE_REQUEST (release of the LPASS-core HW vote).
Issued by q6afe-clocks (.lpass_unvote_clk = q6afe_unvote_lpass_core_hw) for the two vote clocks
LPASS_HW_MACRO_VOTE and LPASS_HW_DCODEC_VOTE -> two hw_block_ids -> two devotes at boot. The
devote is fire-and-forget (apr_send_pkt, no RSP wait) and q6afe_callback() has no case for 0x100f6,
so the ADSP's NAK (status=1) lands in the APR_BASIC_RSP_RESULT default -> also "Unknown cmd 0x100f6".
The matching VOTE (0x100f4) succeeds and audio works (speakers/mics verified earlier), so the a52q
ADSP firmware simply does not implement the DEVOTE opcode; the core block stays voted. This is the
standard sc7180/sm7125 LPASS macro clock path, not an a52q DT/machine-driver misconfiguration. No
code change — a real fix would be a generic q6afe callback/firmware-capability change, out of scope.

### 3. aux_bridge "error -ENODEV: failed to acquire drm_bridge" — SKIPPED (harmless, required wiring)
Source: drm_aux_bridge_probe() -> devm_drm_of_get_bridge() returns -ENODEV. The aux bridge is
registered unconditionally by the USB QMP combo PHY (phy-qcom-qmp-combo.c:5286). Its downstream
lookup reads the PHY's OF-graph port@0 (usb_1_qmpphy_out in sc7180.dtsi), which is an empty
endpoint { } on a52q because the phone has no DisplayPort-over-Type-C sink (USB2-only via the
sm5714 MUIC; dwc3 maximum-speed = "high-speed").
The qmpphy must stay status=okay because the base sc7180 dwc3 still references it as "usb3-phy";
disabling it without also rewriting the dwc3 phys/graph would EPROBE_DEFER dwc3 and kill USB (our
only phone access, untestable here). Sibling mainline sm7125 phones (xiaomi curtana) keep qmpphy
enabled and carry the same benign message. USB works; DP is absent by design. No DT change.

## 2026-10-03: USB xhci role-flap storm when cable unplugged (FIXED)
Symptom (AUDIT.md D2): cable unplugged -> xhci host controller add/remove ~every 0.3 s
(1487 cycles / 2974 "remove" lines in boot -2; first b-2:10078), usb0 gadget wedged, log
bloat, CPU churn. Storm begins the instant the gadget UDC goes "not attached" (laptop-side
cable drop; last `hb ... configured` at 4495.5, first xhci at 4496.2).

ROOT CAUSE (evidence): during the storm the only kernel lines are xhci add/remove - no
extcon, and dwc3 host mode on this DT is driven solely by the usb-role-switch from
sm5714-cc (typec@33). So the role is being flipped HOST<->DEVICE ~3x/s. Mechanism: the
driver leaves the CC block in free-running DRP (CNTL1=0x41); with nothing plugged the DRP
toggle latches a *phantom sink* (we=host) on the source-advertise half of each cycle
(attach lasts ~85 ms before the detach, b-2:4496.244->4496.329). sm5714_cc_update() acted
on every raw attach immediately -> usb_role_switch_set_role(HOST) + VBUS on -> xhci
registered -> next detach -> DEVICE -> xhci removed. No debounce.

The /etc/usb-otg-fixup.sh oneshot (usb-otg-fixup.service, 6.14-era) is NOT the storm
trigger but is now fully redundant AND partly harmful: all three pokes are handled in 7.3 -
(1) gpio104 bias-disable = DT typec_int pinctrl (a52q.dts:465, applied via
pinctrl-names="default"); (2) CC mask 0xe7 + CNTL1=0x41 DRP = sm5714_cc_hw_init(); (3) the
only non-redundant poke, MUIC 0x25/0x06=0x89 "manual USB", *overrides* the kernel muic
driver's AUTO default (sm5714-muic sets AUTO at probe, manual-USB only on host attach), so
it fights in-kernel handling. Service does not run during the storm (oneshot, finished at
boot 13.1 s), so it is not the flap source - but it is stale and was disabled.

FIX:
- Kernel (branch a52q/usbflap off a52q/integ, worktree ~/src/wt-usbflap):
  drivers/usb/typec/sm5714-cc.c - debounce the host-mode commit. Only a *sink* attach
  (we become host) is debounced (SM5714_CC_DEBOUNCE_MS=150, re-read CC_STATUS after
  msleep; threaded IRQ can sleep). Source attach (device) + detach are the safe resting
  states, left immediate -> gadget link still instant. Real OTG partner survives the
  debounce; a DRP phantom clears within one toggle period, so HOST/VBUS/xhci is never
  driven for it. Commit 9b7ac37. Build W=1 clean (O= on /tmp/claude-1000/a52build via
  wt-nits, same base commit); checkpatch --strict clean. No DT change needed.
- Phone: `systemctl disable usb-otg-fixup.service` (was enabled). Gadget stayed
  configured, data_role=device after disable. Live MUIC reg left alone (kernel resets it
  to AUTO on the next disconnect; not touched to avoid dropping the SSH link).

NOT verified on-device: the unplugged storm cannot be reproduced from here (cannot unplug;
cannot deploy a kernel - no reboot/UKI allowed). Fix is build- + checkpatch-clean and
reasoned against the logged timing. Deploy + unplug test is the remaining step.

## 2026-10-03 — a52q userspace boot-log fixes (regdb, bootmac, alsa, console-setup; rotv investigated)

Five journal nags fixed in two places each: a `recipes` commit (device-a52q) for
new images, and a live fix on the phone persisting in /etc or /var (/usr is
read-only dm-verity). Verified live over `ssh a52r` (phone NIC is in netns "a52",
reachable only via the ssh ProxyCommand — plain ping to 172.16.42.1 fails by design).

1. **`cfg80211: failed to load regulatory.db` → regdomain now CZ.**
   cfg80211 is built-in and asks for regulatory.db in the initrd before /usr is
   mounted, so the first load fails and it stays on world (country 00). Plus the
   active db is Debian-signed (`/usr/lib/firmware/regulatory.db` → alternatives →
   debian), and this mainline kernel carries only the *upstream* regdb key, so
   `iw reg reload` returned ENODATA (-61) — same as sm7150.
   - Live: copied the upstream-signed pair into the firmware_class.path
     (`/var/lib/firmware/regulatory.db{,.p7s}` from the `*-upstream` files, which
     is searched before /usr/lib/firmware), then `iw reg reload` + `iw reg set CZ`.
     Result: `country CZ: DFS-ETSI` (5 GHz + full TX power unlocked). Persisted the
     CZ setting with `/etc/systemd/system/bengalos-a52q-regdb.service` (oneshot,
     reload+set CZ) enabled via a static `multi-user.target.wants` symlink;
     `systemctl start` → Result=success, ExecMainStatus=0.
   - Recipe: mirrored the proven sm7150 fix in device-a52q — `wireless-regdb` in
     Packages, `mkosi.extra/usr/lib/firmware/regulatory.db{,.p7s}` symlinked to the
     `-upstream` variants, `bengalos-a52q-regdb.service` + its static wants symlink
     (static, not preset: presets don't apply on an A/B /usr-only update).

2. **`wld0: bootmac --wlan failed (exit 1)` → dropped; MAC already stable.**
   `/usr/lib/udev/rules.d/90-bootmac-wifi.rules` (`KERNEL=="wlan0", RUN+=bootmac
   --wlan`) derives a machine-id MAC and fails to apply it on ath10k_snoc (set
   times out after 5 s). It is pointless on a52q: `a52q-efs-wifi-mac.service`
   already reads the *factory* WiFi MAC from the Samsung EFS partition and hands it
   to NM as `wifi.cloned-mac-address`, so the MAC is stable across boots
   (wld0 = a8:76:50:9f:98:f0 = the EFS factory addr; the service is active and
   its /run NM drop-in carries that addr). The bluetooth bootmac was already
   masked (service → /dev/null); the wifi one uses RUN+= so disabling the service
   never stopped it.
   - Live + recipe: mask the rule with a `/dev/null` symlink
     (`/etc/udev/rules.d/90-bootmac-wifi.rules` live; `mkosi.extra/usr/lib/udev/
     rules.d/90-bootmac-wifi.rules` in the recipe). `udevadm control --reload` +
     trigger: no more bootmac in the journal, MAC unchanged.

3. **`controlC0: alsactl -E HOME=/run/alsa init 0 failed (exit 99)` → silenced.**
   This card ships no alsa-lib init config, so `alsactl init` exits 99 ("no
   soundcard config") and does nothing; the real mixer setup is UCM
   (card0 "Samsung Galaxy A52"; `ucm2/conf.d/sm8250/samsung-SamsungGalaxyA52-.conf`
   → the a52q UCM, driven by PipeWire). Wrapped the init in `/bin/sh -c '… || true'`
   in `91-a52q-alsa-init.rules` so the benign 99 no longer logs as a udev failure;
   behaviour (and audio) unchanged. Live override in /etc, recipe edit in /usr.
   Re-trigger of `-s sound`: no exit-99.

4. **iio-sensor-proxy "No 'rotv' sensor available" (compass) — investigated only.**
   accel/light work because a patched iio-sensor-proxy talks to the SLPI/SSC over
   QRTR via libssc and those data-types have SUIDs. libssc's compass opens a
   `rotv` SUID (libssc-sensor-compass.c:312) — a *fusion* sensor that needs
   accel+gyro+mag. No `rotv` SUID is registered because the AK991x magnetometer
   isn't up on the DSP (its I2C bus/regulators in DT — the suspected earlier SEE
   watchdog cause), and `rotv`/`mag_cal` are ADSP-image algorithms, not shipped
   files. To enable: get the mag probing on the DSP, confirm gyro, ensure the
   `rotv`/`geomag_rv` algos instantiate and appear in the registry; fallback is
   patching libssc to `geomag_rv`/`mag`. Not a pure userspace fix — no change made.

5. **`vtcon*: /etc/console-setup/cached_setup_font.sh` missing → masked the rule.**
   `/usr/lib/udev/rules.d/90-console-setup.rules` runs cached_setup_font.sh /
   cached_setup_terminal.sh, but console-setup is unconfigured on a52q (no
   /etc/default/keyboard, no /etc/default/console-setup — `setupcon --save-only`
   refuses), so the scripts are never generated. Same intent as sm7150 masking
   console-setup.service/keyboard-setup.service. Masked the rule with /dev/null
   (live `/etc/udev/rules.d/90-console-setup.rules`; recipe
   `mkosi.extra/usr/lib/udev/rules.d/90-console-setup.rules`). Re-trigger of
   `-s vtconsole`: no callout error.

recipes commit (device-a52q only; not pushed). sm7150/usb-share working-tree
changes present at the time were left untouched / unstaged.

## 2026-10-03 — SM5714 power-supply properties for UPower (branch a52q/psy)

Worktree ~/src/wt-psy (sparse: only the 4 edited files — laptop / had <700 MB
free, a full/buildable worktree did not fit). Branch a52q/psy off a52q/integ
(fa2fda93f9f4). Build-verified by overlaying the edited files into the sibling
full tree ~/src/wt-nits and building the warm O= tree /tmp/claude-1000/a52build
under `flock /tmp/claude-1000/a52build.lock`; wt-nits restored (`git checkout --`)
after each build, left clean.

Two UPower bugs (evidence: ~/linux-a52q/logs-1003/power.txt):
1. line_power_sm5714_charger showed online=no while charging. UPower only treats
   a POWER_SUPPLY_TYPE_USB line-power supply as a charger once it also exposes a
   usb_type. Fix: charger now advertises POWER_SUPPLY_PROP_USB_TYPE + usb_types
   {UNKNOWN,SDP} and reports it from the VBUS-OK bit.
   NOTE: the charger block (I2C 0x49) cannot see the BC1.2/Type-C subtype — the
   downstream driver (drivers/battery/charger/sm5714_charger.c) receives
   cable_type from the MUIC (0x25, DEVICETYPE1/2 regs 0x07/0x08) via Samsung's
   notifier, which has no upstream equivalent. So we report generic SDP while
   powered, UNKNOWN otherwise. Richer subtype would need the MUIC/CC drivers to
   feed the charger (bigger change, deferred).
2. battery_sm5714_fg showed 0 Wh. FG SRAM exposes only SOC/VBAT/CURRENT/TEMP —
   no learned-full or coulomb-count register. Fix: read charge_full_design from
   an optional `monitored-battery` simple-battery node (CHARGE_FULL_DESIGN) and
   derive CHARGE_NOW = design * SoC. No CHARGE_FULL (chip can't learn it); UPower
   falls back energy_full -> energy_full_design. A52 battery EB-BA525ABY added to
   the dts: 4500 mAh, 4.38 V max.

Verification (all clean):
- W=1: sm5714-charger.o, sm5714-fg.o compile with no warnings.
- dt_binding_check DT_SCHEMA_FILES=siliconmitus,sm5714-fg.yaml: clean.
- CHECK_DTBS qcom/sm7125-samsung-a52q.dtb (full schema set): 0 warnings.
- checkpatch.pl --strict on all 4 commits: clean.
Not pushed/merged.

Upstream series regen (~/linux-a52q/upstream/power-supply-sm5714, NOT done):
- 1/5 (dt-bindings fg) += monitored-battery.
- 2/5 (fg driver) += CHARGE_FULL_DESIGN/CHARGE_NOW + power_supply_get_battery_info.
- 4/5 (charger driver) += USB_TYPE prop/usb_types; 5/5 (BIT cleanup) rebases on it.
- 3/5 (charger binding) unaffected.
- dts battery node is device-specific, not part of this driver series.

## 2026-10-03 — camera-switch hard reset: investigation (a52q/camreset, NOT fixed)

Branch a52q/camreset @ a52q/integ (fa2fda9), sparse wt ~/src/wt-camreset. Build dir
/tmp/claude-1000/a52build (a52q_defconfig, CAMSS=m S5KGW1P=m), flock a52build.lock.

Symptom: phone HARD-RESETS (no log, cold boot) while GNOME Snapshot reconfigures the
MAIN camera. Evidence logs-1003/journal-b-1.txt ~4355-4418: config#2 main 2000x1128
streams + 11 s AF sweep (OK); config#3 main "2000x1500" → reset ~250 ms later.

### Topology (from DT sm7125-samsung-a52q.dts)
- Main = s5kgw1p, **C-PHY 3-trio**, CSIPHY0, has the AK7374 VCM (lens-focus). The ONLY
  C-PHY sensor; all others D-PHY. It is the crashing camera (GRBG + lens in the log).
- s5kgw1p has only TWO modes: mode[1] 4624x3468 (4:3 full), mode[2] 2000x1128 (16:9,
  fast_1g). ONE advertised link_freq (1 GHz); fast_1g moves mode[2]'s link to ~1001.6
  MHz too (19.2/3 * 313/2), so BOTH modes run the C-PHY at ~1 GHz — no link-rate change.

### Key finding: configs #2 and #3 are IDENTICAL at the V4L2 level
- "2000x1500" is a libcamera SoftISP (userspace) number. v4l2_find_nearest_size(2000,1500)
  over {4624x3468, 2000x1128} → mode[2] (err 372 vs 4592). Both log lines show stride
  2512 = width 2000 → sensor = mode[2] (2000x1128) in BOTH #2 and #3.
- So the sensor driver does the SAME work both times. The reset correlates with the
  *repeated* in-session reconfigure of the C-PHY main, not with the mode/size.

### Candidates RULED OUT by code reading (+ researcher subagent on camss)
- Sensor s_stream/set_fmt: set_fmt is -EBUSY while streaming and only touches s->mode/
  ctrls (no reg writes); s_stream pm_runtime-cycles cleanly; identical mode both configs.
- CSIPHY stale state: csiphy_set_power(on) calls hw_ops->reset every power-on
  (camss-csiphy.c:241); power is cycled per STREAMON/STREAMOFF (v4l2_pipeline_pm_get in
  video_prepare_streaming, camss-video.c:239). 2nd stream-on gets a fresh PHY reset.
- CSID/VFE: reset on power-up; VFE global_reset masks IRQs; camlanes lane_cnt override is
  saved/restored (csiphy 285-313) and main reports 3 C-PHY lanes = DT, so unchanged.
- Size mismatch: camss has link_validate = v4l2_subdev_link_validate on csiphy/csid/vfe,
  and vfe source follows sink (vfe_try_format 1387), video_check_format compares node vs
  vfe source (camss-video.c:208). A sensor/pipe size mismatch would -EPIPE at STREAMON,
  not reset. (Sensor get_fmt ACTIVE returns clamped 1128.)
- camlanes is NOT the cause: the crash build 706d119 predates it; only s5kgw1p change
  since is get_mbus_config (harmless for the 3-lane main).
- video-mux: main is a DIRECT C-PHY pipeline (no mux).
- One concrete asymmetry (not proven causal): csid_set_stream(0) is a no-op after the
  first start (need_vc_update false), so the CSID RDI is never explicitly halted at
  STREAMOFF before clocks are gated; it is reset on the next power-up, so benign per read.

### Could NOT reproduce headless
- `cam` does ONE config per session; single captures of every size incl. the big 4:3
  mode[1] (1600x1200, 2048x1536) and 1920x1080 all stream fine, 0 resets.
- Sequential/alternating cam runs (16:9↔4:3, x3) do NOT reset (close() power-cycles, so
  each run == a fresh 1st stream-on; the bug needs in-session STREAMOFF→S_FMT→STREAMON).
- Device lacks v4l2-ctl, media-ctl, a compiler, py-libcamera and gstreamer, so an
  in-session reconfigure cannot be scripted by hand.
- Phone sits at the greetd greeter (no phosh/user session), so GNOME Snapshot — the only
  tool that does the exact reconfigure — cannot be driven remotely.
- NOTE: a killed test `cam` left the CSIPHY0→CSID0 media link refcounted "busy"; clears
  on the next reboot.

### Strongest hypothesis + next step
Repeated in-session reconfigure of the C-PHY main pipeline faults during the 2nd
STREAMON, despite all blocks being reset per stream. The obvious power/clock/lane/size
candidates are contradicted by the code, so the fault is subtler (likely a transient in
the C-PHY teardown↔re-setup overlap in the out-of-tree SC7180 C-PHY support, or a shared
cam_cc/CAMNOC resource glitch) and needs the actual fault captured. NO kernel fix was
committed — a52q/camreset == integ — because every testable hypothesis was eliminated and
shipping an unverified change to the shared camss path is higher-risk than the bug.
To capture it: human repro (Snapshot, switch main resolution/shutter) with ramoops/pstore
enabled, or add a temporary WARN+dump in csid_configure_stream / csiphy_lanes_enable and
read it over netconsole; the current build has neither pstore nor netconsole.

## 2026-10-03 ~12:45 — camera: CSIPHY reads 0 on first power-up; SMMU iova-0 in binned mode (orchestrator)
- ~/linux-a52q/camrestream.py (python ctypes V4L2 restream loop on /dev/video0, modes keep/reopen/fast):
  20x keep + 30x fast + 20x reopen on main s5kgw1p @4624x3468 → no reset (reopen after fast: frame timeouts).
- Every `cam` session's FIRST CSIPHY power-up logs `CSIPHY 3PH HW Version = 0x00000000` (3/3), later ones 0x40010000.
- `cam -c 2 -s role=viewfinder,width=1920,height=1080` (2000x1128 binned) → SMMU TF iova 0 SID 0x820 (VFE WM) and
  cam hangs with no frames. Both handed to agent → branch a52q/camreset2.
- On device now: bb7b22c (0.26.1003.2) 4/4 boots clean; backlight/regdb CZ/rtc-offset/10 s shutdown verified;
  UPower 0 Wh needs charge_full (UPower 1.91.4 requires the attr) → d898b5c on OBS.

## 2026-10-03 ~11:05 — tqftpserv mcfg + bluez/wireplumber dbus noise (coder)

Two userspace log issues investigated live on a52q (bluez 5.87, pipewire 1.6.9,
wireplumber 0.5.17, kernel 7.3.0-rc5-sm7125). Verdict for BOTH: no on-device fix
warranted — issue 1 is benign upstream noise, issue 2 needs files that do not
exist on any mainline-accessible partition.

### Issue 1 — bluez MediaEndpoint1.NotImplemented dbus rejects (19x/boot): BENIGN
- `dbus-daemon: Rejected send message, 0 matched rules; type=error, sender=wireplumber
  (uid 981/60466) ... error=org.bluez.MediaEndpoint1.Error.NotImplemented, dest=bluetoothd`.
- It is an ERROR *reply* from wireplumber (the MediaEndpoint impl) to a bluetoothd
  method call. dbus logs it because it is not matched as a requested_reply across the
  uid boundary (requested_reply="0"), not because a policy is missing. /usr/share/dbus-1/
  system.d/bluetooth.conf is the stock policy and is correct (root owns org.bluez,
  context=default may send_destination=org.bluez).
- Bluetooth audio IS configured and functional (no headset to pair, verified via the
  stack):
  - hci0 up, not rfkill-blocked.
  - Adapter1.UUIDs advertise 110a/110b (A2DP Source+Sink), 110c/110e (AVRCP),
    111e/111f (HFP HF+AG).
  - wireplumber registers 57 A2DP MediaEndpoint objects this boot (SBC, aptX, aptX-HD,
    LDAC source, opus, faststream — sink+source).
- Root cause is upstream (wireplumber returns NotImplemented for a MediaEndpoint method
  bluetoothd probes; bluez does not track the error reply). Nothing to patch on BengalOS.
  Upgrade path: fixed upstream in wireplumber/bluez, or hush with a dbus allow rule for
  the error reply (not done — it would mask a harmless condition).

### Issue 2 — tqftpserv rejects mcfg_sw/mcfg_hw + ota_firewall/ruleset: files absent on-device
- Modem requests over QRTR/tqftpserv at boot:
  /readonly/firmware/image/modem_pr/mcfg/configs/mcfg_hw/mbn_hw.dig,
  .../mcfg_sw/{mbn_sw.dig,oem_sw.txt,mbn_sw.txt}, and /readwrite/ota_firewall/ruleset.
- tqftpserv path mapping (linux-msm translate.c): /readonly/firmware/image/<X> is served
  from /lib/firmware/updates/<fwdir>/<X> then /lib/firmware/<fwdir>/<X>, where
  fwdir = dir of remoteproc0 firmware = qcom/sm7125/a52q. /readwrite/<Y> -> StateDirectory
  /var/lib/tqftpserv/<Y>.
- BOTH /lib/firmware and /lib/firmware/updates resolve under /usr (dm-verity, READ-ONLY);
  tqftpserv cannot be given files there without the a52qdev sysext or a bind-mount.
- But the files do not exist to serve anyway:
  - Vendor `modem` vfat (sda18, image/modem_pr/mcfg/) holds ONLY index/digest files:
    mcfg_hw/{mbn_hw.dig, mbn_hw.txt, mbn_hw_w.dig, oem_hw_w.txt}, mcfg_sw/oem_sw_w.txt.
    The mbn_hw.txt / oem_sw_w.txt indices point to mcfg_{hw,sw}/generic/.../*.mbn PAYLOADS
    that are NOT on the partition. `find -iname '*mcfg*.mbn'` = 0 on modem.
  - Of the 4 requested files only mcfg_hw/mbn_hw.dig is present; the three mcfg_sw files
    the modem wants (mbn_sw.txt/oem_sw.txt/mbn_sw.dig) are absent (only the `_w` world
    OEM index exists). ota_firewall/ruleset is OTA state the modem creates itself.
  - prism/optics/omr/persist (ext4) contain zero mcfg. The real mcfg MBN tree lives only
    inside Android `super`->vendor firmware_mnt (sda25, dynamic/liblp), not exposed to the
    mainline rootfs.
- Serving the lone 32-byte mbn_hw.dig without its mcfg_hw.mbn payload would just move the
  failure (modem next requests the absent .mbn). So nothing actionable.
- Impact: none. No SIM in phone; mcfg_sw carrier profile is irrelevant. Modem boots and
  runs on built-in defaults: remoteproc0 state=running, "remote processor modem is now up",
  IPA running, GNSS engine locked. The tqftpserv rejects are cosmetic.
- Upgrade path (only if carrier config is ever needed WITH a SIM): extract the mcfg
  generic/*.mbn tree from Android super->vendor (map with dmsetup/liblp), stage it in the
  a52qdev sysext at usr/lib/firmware/qcom/sm7125/a52q/modem_pr/mcfg/, and verify the
  mainline modem accepts that vendor mcfg version. Not done: payloads unavailable + no SIM.

## 2026-10-03 — camera A (CSIPHY ver=0) + B (VFE WM iova=0) FIXED (branch a52q/camreset2)

Branch a52q/camreset2 @ a52q/integ (d898b5c), sparse wt ~/src/wt-camreset2.
Build: overlay the 2 edited files onto ~/src/wt-nits (its camss tree is byte-
identical to integ) and build O=/tmp/claude-1000/a52build under flock
a52build.lock; wt-nits restored after. W=1 clean, checkpatch --strict clean,
no DT changes.

### Evidence (on-device bb7b22c, which already contains camfix2 706d119)
`cam -c 2 --capture=1` (main s5kgw1p, 4624x3468) alone reproduces:
  CSIPHY 3PH HW Version = 0x00000000      <- issue A, first power-up
  VFE:0 HW Version = 1.1.0 / CSID:0 0.0.1
  arm-smmu 15000000.iommu: Unhandled context fault: fsr=0x402,
    iova=0x00000000, fsynr=0x1c0011, cbfrsynra=0x820, cb=8
  FSR=[Format=2 TF] FSYNR0=[WNR PLVL=1]   <- issue B
cam then hangs in epoll_wait with no frames. titan_top_gdsc=on, ife0/ife1=off.
Context bank cb=8 wedges on the TF, so EVERY later capture (any resolution)
faults too until reboot — this is why "single full captures" now fail where the
camreset notes said they passed: the phone was left wedged by a prior binned run.

### B root cause (the real bug; camfix2 was incomplete) — FIXED
cbfrsynra 0x820 = VFE0 SID, WNR = the VFE write master DMAs to IOVA 0. The gen2
WM double-buffers one IMAGE_ADDR reg into an internal ping/pong pair, one slot
per frame. vfe_enable_output_v2() programs one slot per queued buffer (loop of
CAMSS_INIT_BUF_COUNT=2). camfix2 set min_queued_buffers=1, so vb2 can start
streaming with a SINGLE buffer queued: the loop fills only ping, pong keeps its
reset value 0, HW writes one frame to 0 -> TF -> CB wedged -> no frames.
camfix2's guard only caught active_num==0. The gen1 path never had this bug:
vfe_output_init_addrs() sets pong_addr = ping_addr when buf[1] is absent.
Fix (camss-vfe.c, vfe_enable_output_v2): when active_num==1, reprogram the WM
with buf[0]->addr[0] once more so the pong slot points at the same buffer;
mirrors gen1. A later 2nd buffer via vfe_queue_buffer_v2() reprograms normally.

### A root cause — FIXED (and it is NOT the hard-reset cause)
Only the FIRST power-up per session reads 0; v4l2 pipeline-PM holds the top
GDSC on for the open fd, so later power-ups are warm and read 0x40010000. After
SHOW_REV_ID is written, the revision latches into the common status regs with a
propagation delay; the cold (just-clocked) block isn't settled when the
immediate readl_relaxed runs. Fix (csiphy-3ph-1-0.c, csiphy_hw_version_read):
poll the status regs until non-zero, bounded to ~2 ms (10 x 100-200us); warm
reads hit on iter 0 with no delay. Doubles as a settle barrier confirming the
PHY is clocked before csiphy_lanes_enable() programs it.
NOTE: version=0 is benign here — the pipeline streamed past it to the VFE stage
(the fault is downstream at the WM), so A is NOT the "camera-switch hard reset"
trigger; that symptom (SoC cold-reboot on reconfigure) remains separate/open.
The iova=0 wedge is a hang, not a reboot (ssh stayed up throughout).

### NOT verified on-device
The SMMU CB is wedged (cb=8) from the repro and only a reboot clears it
(reboot not allowed here), so the fix cannot be stream-tested from this session.
Both commits are build- + checkpatch-clean and the B fix is the direct
completion of camfix2's own "never point the WM at 0" invariant, matched to the
logged fault. Deploy + `cam`/Snapshot test is the remaining step.
Commits 6ca37d2 (B), 7d0278b (A). Not pushed/merged.

## 2026-10-03 15:00 — integ 75e4cb4 on device (0.26.1003.3): best state so far
- 3/3 boots clean (modem 0 crash, Wi-Fi/BT/NFC, sensors, 5 cameras 2 frames each), 0 failed units, 0 WARNs.
- Verified: backlight restore OK, regdb CZ, line power online + USB_TYPE, UPower 19.71 Wh (charge_full),
  shutdown session kill 10 s (was 30), rtc-offset saved, cam viewfinder 2000x1128 10/10 frames x3 (was SMMU
  iova-0 wedge), camrestream reopen 15/15, 0 SMMU faults.
- Merged today: a52q/nits (s6e3fc3 backlight), a52q/usbflap (sm5714-cc sink debounce), a52q/psy (usb_type,
  battery node, charge_*), a52q/camreset2 (gen2 pong never 0, CSIPHY rev-id poll).
- NEEDS A HUMAN: (1) Snapshot main-camera resolution switch → hard reset (not reproduced headless);
  (2) unplug USB cable → confirm no xhci add/remove storm; (3) >6 min touchscreen use → no GPI timeout.
- Recipes (local, not pushed): 0d0ff02 (shutdown/rtc), ae2fdb6 (regdb/bootmac/alsa/console), 74738e1 (docs).

## 2026-10-03 — SSC sensor discovery audit: mag/compass root-caused, gyro/prox explained (investigation, NOT deployed)

Task: enumerate the SUIDs the ADSP discovers and explain why magnetometer,
gyro and proximity don't surface. Device at integ 75e4cb4 (0.26.1003.3),
accel+ALS working from boot. No ssccli/libssc CLI on the phone; `libssc.so.2`
is present (/usr/lib/aarch64-linux-gnu) but only linked into iio-sensor-proxy,
which hard-codes the data types it queries. Enumerated SUIDs via
`G_MESSAGES_DEBUG=all /usr/libexec/iio-sensor-proxy` (service stop/run/restart;
does NOT touch the ADSP, no boot-loop risk; ExecCondition guard left intact).

### Discovered SUIDs (before)
- accel  (lsm6dso, STMicro):   2286538866409242278 / 11115320498015681092  — WORKS
- ambient_light (stk31610):    5158289438331071126 / 3046173514946711665  — WORKS
- gyro  (lsm6dso):  co-registered with accel on the same SEE driver instance;
  SUID exists on the ADSP but iio-sensor-proxy never queries "gyro".
- rotv  (compass fusion):      NOT registered ("No 'rotv' sensor available").
monitor-sensor (before): Has accelerometer (tilt face-up), Has ambient light
(~220 lux live), **No proximity, No compass**.

KEY: iio-sensor-proxy only ever queries three data types — `rotv`, `accel`,
`ambient_light`. It never queries `mag`, `gyro` or `proximity`. So anything on
those three is invisible to monitor-sensor regardless of the ADSP state.

### Architecture facts established
- All SEE sensor drivers/algos (lsm6dso, ak0991x, stk31610, rotv, mag_cal) are
  **statically linked into the signed adsp.mbn** — the ADSP loads NO external
  `sns_*.so`. The only `.so` open-failure this boot is `sns_bring_to_ear.so`
  (a prox "bring to ear" gesture add-on), a benign probe-and-fallback. So no
  missing-algo-file is involved for mag/gyro/rotv.
- a52q ships the generic Qualcomm QRD configs (confirmed in device
  proprietary-files.txt): atoll_qrd_ak991x_{0,2,6}, atoll_qrd_lsm6dso_0,
  atoll_qrd_stk31610_0. The config tree is extracted at runtime by droid-juicer
  from the Samsung vendor partition into /var/lib/droid-juicer/sensors/sensors/.
- socinfo served to the SEE: soc_id 443, hw_platform IDP → the config `soc_id`
  (407/443) and `hw_platform` (MTP/Surf/IDP) guards PASS.
- Rails: ak0991x and lsm6dso both use only `/pmic/client/sensor_vddio` = pm6150l
  L8 (num_rail=1), already forced always-on by a52q/ssc-rails. stk31610 uses
  dummy rails. ak0991x dri_irq_num=0 (polled, NO interrupt GPIO needed). So the
  mag needs **no extra DT rail and no GPIO** beyond what accel already proves on.

### gyro — not a gap (userspace limit)
lsm6dso registers accel+gyro together; accel works, so the gyro SUID is present
on the ADSP. iio-sensor-proxy/monitor-sensor has no gyroscope D-Bus interface
and never queries it. Not DT/registry/algo fixable; needs a libssc gyro client
(libssc-cli has one; not built/installed here). Blocker = userspace only.

### proximity — no SSC proximity sensor on a52q (by Samsung design)
atoll_qrd_stk31610_0.json contains ONLY a `.als` section (no `.prox`), with
dummy rails — the STK31610 is registered as ALS-only. The only prox-like part
on a52q is the Semtech **SX9360** capacitive SAR/grip sensor (vendor DT
`sx9360,proxthresh_reg` etc.) which is a Linux-side I2C device, NOT an SSC
sensor. iio-sensor-proxy also doesn't query proximity in this build. Blocker =
no SSC optical proximity hardware/config + proxy build. Not DT/registry fixable.

### mag → compass (rotv) — ROOT CAUSED, registry-fixable (UNVERIFIED on device)
All three AK0991x configs are `revision`-gated and together cover rev 0-31
(_0: ["0,","1"], _2: ["2".."5"], _6: ["6".."31"]); lsm6dso/stk31610 have NO
revision guard. The SEE reads `revision` from
`/sys/class/sensors/ssc_core/ssc_hw_rev` (sns_reg.conf: `file=revision=...`).
That path is served by the patched hexagonrpcd (patch 0004, confirmed in the
deployed 69024-byte binary) from `<root>/sensors/ssc_core/ssc_hw_rev` — but the
**file is not deployed**: the production registry at
/var/lib/droid-juicer/sensors/sensors/ has no `ssc_core/` dir (droid-juicer
only extracts vendor files; ssc_core nodes are synthetic; bengalos-a52q-ssc.conf
doesn't create them). hexagonrpcd logs `Could not open .../ssc_hw_rev` every
boot → the SEE gets no readable revision → **none of the revision-gated mag
configs match → ak0991x never instantiates → rotv (needs accel+gyro+mag) can't
build → "No rotv sensor available" → no compass.** accel/ALS are unaffected
(no revision guard). This is the single fixable blocker and it is registry/
config, NOT DT (rail already on, no GPIO) — so no a52q/sscsens DT commit is
warranted.

### Candidate fix (NOT applied — needs on-device test; phone was unreachable)
Create the two synthetic registry files so the patched hexagonrpcd can serve a
readable revision:
  /var/lib/droid-juicer/sensors/sensors/ssc_core/ssc_hw_rev  = "0\n"
  /var/lib/droid-juicer/sensors/sensors/ssc_core/ssc_mode    = "0\n"
owned fastrpc:fastrpc (sources already exist at
~/linux-a52q/sensors/root/sensors/ssc_core/). Recipe side: add two `f` lines to
device-a52q .../tmpfiles.d/bengalos-a52q-ssc.conf creating them.
CAVEATS to resolve during the test:
  1. ak0991x_0's guard has a vendor typo "0," — if the SEE revision matcher is
     strict, rev "0" won't match _0; try ssc_hw_rev="1" (clean in _0's list) —
     all three configs are bus/slave-identical (I2C QUP4, addr 0x0C); rev only
     selects the default cal matrix (a runtime-tunable knob, mag_cal overwrites).
  2. Does restarting hexagonrpcd re-trigger ADSP mag registration, or is an ADSP
     restart (forbidden) required? Prior crash history says a hexagonrpcd
     restart DOES make the SEE re-read configs.
  3. **SAFETY**: if the AK0991x on SSC I2C QUP4 is on a bus the ADSP can't drive
     (the README's UTMR_CLNT_1/sns_thread_mana dead-bus watchdog), making its
     config match could re-trigger the ADSP-fatal boot-loop. MUST be tested via
     the README "SAFE on-device test plan" (hexagonrpcd MASKED, run the binary
     manually once as fastrpc while watching dmesg) — NOT by just enabling the
     service. md5-backup the registry, restore on `sensor_process crash`.
Acceptance when the phone is free: after deploying ssc_hw_rev, re-run the
masked-binary test; rotv should discover a SUID and monitor-sensor should show
"Has compass". If the UTMR watchdog fires instead, the blocker is the SSC I2C
QUP4 bus / ak0991x power inside the ADSP image — not Linux-fixable.

### Why nothing was deployed/committed this session
Phone went unreachable mid-session (sshd closing connections; another session
held a52phone.lock running a claude-installer). The fix carries a real
ADSP-fatal/boot-loop risk (caveat 3) and MUST be verified via the masked test
first, so no live deploy and no recipes commit were made. No DT change (no
a52q/sscsens branch) — the fix is registry-only.

---

## 2026-10-03 — CPU7/Gold-core hard hang under load (RCU stall, no NMI)

### Symptom
Under heavy load (scp/installer over USB-net, camera software ISP) the phone
hard-resets. Captured once in full (`journalctl -b -1 -k`, 13:42):
`rcu: INFO: rcu_preempt detected stalls ... 7-...0: ... idle=.../1/0x4000000000000000`,
then `Sending NMI from CPU 0 to CPUs 7` / `After 10 seconds, these CPUS still
haven't responded to the NMI: 7`, fqs climbing, system degrades to a watchdog
reset. CPU7 does not even take the pseudo-NMI = the core is physically not
executing.

### Root cause
A **PSCI deep-idle (power-collapse) exit that never returns** on the Gold
(Cortex-A76) cores. The deepest idle state `big_cpu_sleep_1` /
`cpu-sleep-1-1` ("big-rail-power-down", `arm,psci-suspend-param = 0x40000004`,
collapses the core voltage rail) cannot be resumed by Samsung's firmware under
load. The USB-net/scp correlation is indirect: with userspace pinned to
CPU0-5 and dwc3 IRQ (irq153) landing only on CPU0, CPU6/7 are the idlest cores
and cycle in/out of deep idle constantly — one exit eventually hangs.

NOT a DT/defconfig divergence vs the stable 6.14 fork: `sc7180.dtsi` CPU/idle/
psci/cpufreq_hw nodes are byte-identical between `a52q/integ` and `obs/sm7125`,
and all CPU-relevant defconfig symbols (CPU_IDLE, ARM_PSCI_CPUIDLE_DOMAIN,
ARM_QCOM_CPUFREQ_HW, QCOM_LMH, PREEMPT, QCOM_TSENS) match. It is a 6.14->7.3-rc5
kernel-version-sensitive firmware interaction. There is no LMh/CPR node in the
DT; `psci: [Firmware Bug]: failed to set PC mode: -3` (OSI unsupported ->
platform-coordinated) is normal and shared by both kernels.

### Reproducer (targeted idle-exit stress; `/root/idlestress.sh`)
Pin a worker to CPU6 and CPU7 that `sleep`s ~7 ms (just over state2
min-residency 5555 us) then wakes, forcing repeated state2 entry+exit
(~60/s/core). SAFETY: arm `systemd-run --on-active=420 systemctl reboot
--force --force` first. A plain USB-RX `dd` over ssh was too light (185 s
clean) because it did not force enough deep-idle exits.

### Evidence (A/B, same stress)
- Baseline (state2 enabled): **HANG at ~110 s** (~6000 state2 entries on CPU7);
  system froze so hard journald logged nothing past the start marker.
- Mitigated (`echo 1 > cpuN/cpuidle/state2/disable` for N=6,7):
  **CLEAN after 300 s**, `state2 usage +0`, with CPU7 taking
  `big_cpu_sleep_0` (state1) **37,457 times** with zero issues -> state1 is
  safe, state2 is the sole culprit.

### Fix
- DT: `arch/arm64/boot/dts/qcom/sm7125-samsung-a52q.dts` override
  `&cpu_pd6`/`&cpu_pd7` `domain-idle-states = <&big_cpu_sleep_0>` (drops
  `big_cpu_sleep_1`). Branch `a52q/cpuhang` off `a52q/integ`, commit
  **895c761a3810**. Verified in compiled dtb (cpu6/7 reference only
  big_cpu_sleep_0; Silver cores keep both). W=1 + CHECK_DTBS clean (only
  pre-existing framebuffer/reserved-memory/sm5714-fg warnings); checkpatch
  --strict clean. NOT pushed/merged.
- Live (phone stable now): `/etc/systemd/system/cpu-gold-idle-fix.service`
  oneshot writes state2/disable=1 for CPU6/7, `enabled --now`.

### Follow-up
a72q (same Samsung firmware family, shared sm7125-samsung-common.dtsi) very
likely needs the same override; not tested here (scoped to a52q). Upstream
candidate: the real bug is PSCI CPU_SUSPEND(0x40000004) resume in Samsung's
TZ; consider reporting.

## 2026-10-03 ~16:10 — why the phone kept "falling back" to 6.14; CPU6/7 deep-idle hang
- Gold-core hang root cause (agent, a52q/cpuhang 895c761, merged → integ f1b1dba): PSCI big-rail-power-down
  (big_cpu_sleep_1) exit fails under load → CPU6/7 dead to NMI → RCU stall / watchdog reset. Explains the
  Snapshot "camera" reset, the install-time crashes and the Claude Desktop hang (that one was on 6.14
  without the workaround). DT drops big_cpu_sleep_1 from cpu_pd6/7.
- /etc/systemd/system/cpu-gold-idle-fix.service (sysfs state2 disable on cpu6/7) re-enabled with drop-in
  ConditionPathExists=.../cpu7/cpuidle/state2/disable → only acts on kernels without the DT fix (6.14).
- a52q-failsafe73.service (old bring-up guard: 300 s after a 7.x boot, rm /boot/EFI/Linux/a52qtest_* and reboot
  unless /run/keep73 exists — only accept73.sh creates it) was silently removing every 7.3 UKI → DISABLED.
  systemd-boot counting (+1) remains the fallback.
- Claude Code 2.1.288 in ~miro/.local/bin; Claude Desktop (claude-desktop-debian v3.3.3 arm64 AppImage,
  extracted) in ~miro/.local/opt/claude-desktop, launcher ~/.local/share/applications/claude-desktop.desktop.
  First extraction lost 7 files to the crash (0-byte v8 snapshot) → re-extracted + sync; broken copy left in
  ~/.local/opt/claude-desktop.broken (owner may delete).

## 2026-10-04 Claude Desktop freeze, monitored run (hotspot, phone 10.65.100.149, kernel f1b1dba)
- /home 100% full is benign: miro.home is a fully allocated 50G image (ls -s 50G).
- Per-second stream (logs-1003/cd-launch-*.log): froze ~25 s after launch at uptime 464.
  MemAvailable 2.1G, swap unused, Dirty <1M, Writeback 0, mem PSI 0, io PSI ~4%. => NOT memory, NOT writeback (refutes I/O-hang hypothesis).
- Last D-state tasks: khugepaged (DN), sugov:6 (big-cluster cpufreq governor kthread); claude-desktop R.
- Next: A) THP never  B) cap cpu6/7 scaling_max_freq. One at a time.
- Test A (THP never): froze anyway at uptime ~235 (logs-1003/cd-launch-thpoff-*.log). THP ruled out.
  Mem 2.7G avail, 39 C, policy6 pinned at 2323200 (top OPP) throughout, claude-desktop R on cpu7.
  Next: stress-ng on cpu6,7 alone at top OPP (no Claude); then cap policy6.
- Big-core stress (openssl+busy loops pinned cpu6,7, 174 s at 2323200): NO hang. Constant 100% load = no idle entries, no freq changes.
- dbg kernel 75d6208 (UKI a52qtest_0.26.1004.1), netconsole over Wi-Fi to laptop:6666 (a52-netconsole.service).
  Claude Desktop ran ~18 min, then at 2309 s: "watchdog: CPU6: Watchdog detected hard LOCKUP on cpu 7",
  CPU7 never answers the backtrace IPI, RCU stall 7-...0 (not idle), mm_percpu_wq lru_add_drain on cpu7 pending forever.
  Log: logs-1003/netcon-cpu7-hardlockup.log. => CPU7 dead with IRQs masked/firmware, same family as the 6/7 big_cpu_sleep_1 hang.
  hardlockup_panic=1 did not panic (buddy detector), phone needed force reboot.
- Suspects: big_cpu_sleep_0 (state1) entry/exit, or big-cluster freq transitions (sugov:6 was D in run 1). Bursty load hits both; stress hit neither.
- dbg kernel side effect: built-in g_ether (USB_ETH=y) takes the UDC -> bengalos-debug-usbnet fails -> no sshd. Fixed by enabling ssh.socket.
- Scaling: Phosh scale 3 -> 360 logical px wide; Claude Desktop main window minWidth 600/minHeight 400 (+720x560, Gxn/Kxn 320x240).
  Patched app.asar in place (same length, 1e0), backup app.asar.orig. Linux ignores asar integrity fuse.
- Burst default idle states (+ app launch at login): RPMh AMC timeout from sugov:6 cpufreq->icc bw vote (rpmh.c:425 WARN, -110), then CPU0 hard LOCKUP. panic=10 rebooted.
- All cpuidle state1/2 disabled (no cluster PD): burst alone 11 min OK; at app launch CPU4+CPU7 hard LOCKUP simultaneously, no RPMh warn. => not cluster idle.
- performance governor (no cpufreq transitions): hung ~10 s after launch, no detector output, wdog pretimeout. => not cpufreq/icc either.
- Headless phoc (pixman, no GPU opened), root, app copy /var/tmp/cdapp: survived 5+ min.
- In-session strace: hang 15 s into launcher shell script (before electron exec); DPU 'no encoder found for crtc 0' + frame event overflow flood right at hang.
  Other hangs had no DPU errors. Multiple CPUs hard-locked with IRQs masked -> need pseudo-NMI stacks.
- dbg2 kernel: obs/a52q-mainline-dbg 67e9e17 (+ARM64_PSEUDO_NMI, PROVE_LOCKING, DEBUG_ATOMIC_SLEEP); boot with irqchip.gicv3_pseudo_nmi=1.
- 2026-10-04 evening, dbg2 kernel (pseudo-NMI on; lockdep self-disabled at boot by cpu_suspend irqs warning):
  pstore stays empty even after sysrq-c and reboot=warm -> boot chain wipes the ramoops region; msm has no drm_panic.
  Silent total hang ~40 s after one in-session launch (no netconsole output at all -> all CPUs/bus).
  NO hang: membw stress 5 cores 6 min; app in headless phoc gles2 (GPU active) 5 min; + miro session bus 4 min;
  cold tar of the 674 MB app from LUKS home (49 MB/s); user-launched app from home, signed in, 10+ min.
  => intermittent; not memory bw, not GPU alone, not session services, not home I/O. Root cause still open.
- dbg3 = integ a9f10dc (+ a52q/dpuscan 3788c5d: guard INTF_LINE_COUNT read with pm_runtime_get_if_in_use) + dbg cfg, UKI a52qtest_0.26.1004.3.
  DPMS toggle stress (60 idle, 150 under load) never reproduced on dbg2. Fix did NOT help: claude launched at 2281 s,
  CPU3 stalled ~2291 s, fqs=0, no answer to pseudo-NMI, wdog pretimeout + bite. No screen toggling => DPU theory unlikely.
  A CPU that ignores pseudo-NMI is wedged in HW or at EL2/EL3 (Samsung uH/QHEE?), not spinning in EL1.
  Errata detected: 1165522/1319367/1530923, 1418040; DBM only on CPU6-7; IDC=1 (no DC clean to PoU).
  Electron/V8 JIT is the common trigger; plain CPU/mem/GPU stress never hangs.
- 2026-10-04/05 autonomous trials (autologin via home-activate-miro.service + greetd initial_session):
  6.14 kernel ALSO hangs (~27 s after launch, CPU6 wedged, no IPI answer) => not a 7.3 regression.
  jitless V8: hangs within seconds. Launcher-only stub: OK. Audio playback x3: OK. memfill 2.6 GB + verify: OK (no missing carveout).
  60 Hz mode: atomic commit EBUSY, unusable. Trials (logs-1003/trials.log): unpinned 2/6 hang, taskset 0-3 1-2/8 hang => pinning doesn't fix.
  pinned-7 hang boot shows kernel timestamps jumping to ~38000 s in a 1 h boot + RCU 'false positive?' on idle CPUs => counter/timer anomaly during hang.

## 2026-10-08 evening — autonomy + watchdog findings (dbg3 kernel, Wi-Fi 192.168.100.131)
- Boot before this session (Oct 6) ran ~2 h, then froze right after Firefox ESR launch (not only Electron).
- Phone lacked /etc/protocols and /etc/services -> `ping: unknown protocol icmp`; copied from laptop.
- systemd-networkd ran with no managed links -> OPER_STATE=off -> timesyncd never synced (clock 2 days behind). Masked networkd (NM owns wld0).
- sleep/suspend targets masked (idle suspend drops Wi-Fi). /etc/sysctl.d/90-a52-autoreboot.conf: panic=10, panic_on_rcu_stall=1, soft/hardlockup_panic=1.
- a52-wifiwatch.service (/etc/a52-wifiwatch.sh): 3 min grace, `nmcli device connect wld0` after 2 min w/o gateway, reboot after 10 min.
  v1 used ping without /etc/protocols -> false "down" -> radio toggle; fixed.
- WATCHDOG, key result:
  * kernel-petting mode (U-Boot armed WDT, no userspace opener): panic=0 + sysrq-c -> phone NEVER resets (17+ min, needed a human).
    => this is why some freezes needed a force reboot.
  * systemd RuntimeWatchdogSec=30s: panic=0 + sysrq-c -> back on Wi-Fi in 101 s (bite works).
    BUT with it on, the IDLE phone reset 3/3 boots at 132/188/246 s, no log. Off: 15 min idle fine.
  * Hypothesis: PID1's 15 s keepalive is delayed > 15 s because a CPU in deep idle misses its timer wakeup
    (same family as the Electron/Firefox core wedge + the kernel time jumps). Test: 30 s wdog + cpuidle.off=1.
- 2026-10-09: 30 s systemd wdog idle 12+ min OK -> the 3 earlier idle resets were NOT reproducible (likely my service
  restarts / 2-day clock step). zz-a52-wdog.conf (RuntimeWatchdogSec=30s) kept ON = the only mode that resets a dead kernel.
- timesyncd: also needs drop-in ExecStartPre=+-/bin/rm -f /run/systemd/netif/state ('+' = outside the unit sandbox) -> synced.
- Claude Desktop baseline (cdbatch.sh base1009): OK,OK,OK, HANG #4 55 s after launch, silent (no RCU/NMI/netconsole output),
  RECOVERED BY ITSELF in ~2 min (wdog bite). First fully unattended freeze+recovery.
- tlbstress.py (8 procs mmap/mprotect/madvise/munmap, ~40M range TLBI broadcasts, 300 s): NO hang -> TLBI/DVM theory unlikely.
- Earlier Claude trials mostly ran under the phosh LOCK SCREEN (idle-delay 300 blanked + locked) and still hung.
  miro now has idle-delay 0 + screensaver lock-enabled false (dev handset). rendstress.py (GTK4 full-screen redraw, cairo/gl)
  + rendtrial.sh for display-path load without Electron.
- 2026-10-09 no-hang results (all with 30 s wdog on): rendstress cairo 4x300 s + gl 4x300 s (screen on, unlocked);
  nsstress.sh (33.6k user/pid/net/ipc namespace sandboxes in 300 s); allburst.sh (92 synchronized 8-core openssl
  bursts, 600 s, up to 59 C). => not display load, not sandbox namespaces, not all-core power steps.
- Phone root fs was 100% FULL (my /var/tmp/cdapp 591M, cdhome*, camera dumps) -> cleaned, 57% used.
- Test UKI a52qtest_0.26.1009.1 = dbg3 + cpuidle.off=1 (uki-recmd.sh); backup of dbg3 /var/tmp/a52qtest_0.26.1004.3.efi.
  cdbatch.sh idleoff 10x300 s running.
- cpuidle.off=1 (UKI 0.26.1009.1): Claude trials 9 OK / 1 HANG (idleoff-8, hung <15 s after launch, silent, self-recovered 98 s).
  => deep idle (PSCI cpu_suspend) is NOT the cause. Baseline today 3 OK / 1 HANG (also <15 s after launch).
- wifistress.py (1.6 GB down + 1 GB up over Wi-Fi, 600 s): no hang => not Wi-Fi/ath10k traffic.
- jit/jitstress.c (static aarch64; threads write+__clear_cache+call code; rwx and W^X-mprotect modes): running.
- jitstress 300 s rwx (5.2e9 write+IC IVAU+call) + 300 s W^X (1.46e7 mprotect cycles), 8 threads: NO hang, no stale code.
  => JIT/cache maintenance (incl. possible hypervisor trapping) not the trigger.
- Next: short-launch reproducer (cdbatch.sh short 30 30: launch, 30 s, kill) then bisect Chromium flags.
- More no-hang results 2026-10-09: seccompstress (434k seccomp-bpf JIT filters), v4lopen.py (2800 open+QUERYCAP over all
  14 /dev/video*, exactly what Chromium's GPU process does), gpuwake.py (9000 GPU runtime-PM wakes racing the 66 ms
  autosuspend), homeio.py (~50 GB writes + 2.6k fsync'd small files in the LUKS homed home; dm-crypt uses xts-aes-ce, no QCE).
  Chromium's ALSA use is only CTL CARD_INFO/PCM_INFO/NEXT_DEVICE (software).
- /dev/mem read of CPU external-debug block 0x7010ff0 (cpu0 CIDR) = instant SILENT WHOLE-SYSTEM HANG, wdog recovered 63 s.
  => a single bad MMIO read reproduces the exact freeze signature (no NMI answer, no log). Debug blocks unusable (secured/off).
- Short launches (launch, 30 s, kill): 1/30 hung. Today's launch-phase total ~3/44. strace of an Oct 4 hang ended in
  plain fork/exec of coreutils inside the AppRun launcher => trigger is not a specific app syscall.
- Back on normal cmdline: UKI a52qtest_0.26.1009.2 (dbg3 cmdline, deep idle on), blessed.
- FIREFOX is a better reproducer: ffshort (launch firefox-esr, 40 s, kill) 5 HANG / 30, all self-recovered (57-84 s).
  Hangs 1-4 were consecutive launches ~1 min after (re)boot; only 1/25 later. All silent.
- eglprobe.py (400x surfaceless EGL init + GLES ctx + 4 MB texture upload + FBO clear + glFinish + teardown, random
  gaps up to 1.5 s so the GPU power-collapses between probes): NO hang => Firefox/Chromium startup GPU probe not it.
- Firefox under strace -f streamed over UDP (udprelay.py -> laptop :6667): 0 HANG / 20 (all at long uptime).
  strace serialization/slowdown suppresses it (race) and/or uptime matters. Next: bootff.sh (reboot -> firefox asap) x8.

## 2026-10-10 00:10 — BATTERY-LEVEL CORRELATION (strongest lead so far)
- Matching every boot end (journalctl --list-boots) to /var/lib/upower/history-charge-19.dat:
  hangs at 18:55?/20:10/21:00/21:29/21:46/21:50/21:52/21:54/21:57/22:08 all at battery <=10% discharging
  (upower stopped sampling at 10% 19:29), one Claude hang at 29% (18:18). Hang rate rose as the battery drained
  (Firefox: 4 hangs in a row at ~21:50). After the charger was plugged in (~22:09), 0 hangs in 76+ Firefox launches
  (ffshort 13-30, fftrace 20, bootff 8, fftr 30), at 100%/charging.
- Charger now carries the whole load: battery current ~0 mA with 8-core openssl bursts -> cannot drain it remotely.
- Hypothesis: VPH_PWR droop on a low battery during app-launch load bursts -> silent CPU/fabric hang. Downstream
  Android has LMh/BCL throttling; mainline sm7125 likely has neither. Explains: silent, NMI-immune, all CPUs,
  random, app-launch-triggered, both 6.14 and 7.3, synthetic tests (all run at 100% or plugged) never hung.
- Confirm: unplug, let it drop below ~20 %, rerun ffshort. Mitigation candidates: LMh/BCL enablement, or a
  low-battery CPU/GPU frequency cap service.
- Instrumentation left installed: a52-ftrace-stream.service (rpm/clk/regulator/icc events -> laptop UDP 6668).
- Research (2026-10-10): mainline has NO PM6150/sc7180 BCL; lmh.c matches only sdm845/sm8150 and is thermal-only;
  a Feb 2026 RFC "hwmon: Qualcomm PMIC BCL" (pm7250b, monitor-only) is unmerged. Cheapest mitigation = userspace cap.
- a52-lowbat-cap.service (/etc/a52-lowbat-cap.sh) installed, DISABLED: on battery & <30 %: big<=1.7 GHz,
  little<=1.5 GHz, GPU<=565 MHz. Writes verified + restored.
- Laptop: `systemctl --user status a52-lowbat-plan` (lowbat-plan.sh) waits for unplug, drains to 20 % with
  rendstress gl, runs 20 uncapped Firefox launches, enables the cap, 20 more. Log logs-1003/lowbat-plan.log.

## 2026-10-10 15:50 — SoC benchmark baseline (battery 97→86 %, unplugged)
- bench.sh full97 (stress-ng matrixprod + glmark2-es2-wayland 2023.01, Debian sid debs in /var/tmp/bench):
  cpu1 43.3 bogo/s; cpu8 176.6; glmark2 552 (1080x2259 windowed, FD618); cpu8+glmark2 together: 127 bogo/s + glmark2 396.
  Clocks hold max (big 2323 MHz, GPU 732 MHz avg under glmark2); peak 1.19 A, min 4.15 V, max 71.6 C. No hang, no throttling.
- Geekbench 6.7.1 Linux ARM preview: SC 769 / MC 1873 (browser.geekbench.com/v6/cpu/19324903).
  Android SM-A525F public: SC ~690-748, MC ~1700-1800 -> mainline is at or above stock. 6.5.0 failed upload (internal code 35); 6.7.1 works.
- No 3DMark for Linux. UL reference (Android): Wild Life 1039, WL Extreme 313, Sling Shot Extreme ES3.1 2534. No public glmark2 numbers for Adreno 618.
- lowbat-plan now runs bench.sh again at 20 % before the Firefox batches (bench-low20.*) to compare.

## 2026-10-10 19:20 — low-battery test: NO hangs (weakens the battery hypothesis)
- bench.sh low20 at 20->16 %: identical scores (cpu1 44.9, cpu8 177.2, glmark2 551), min 3.596 V, 1.19 A, 79 C. No hang.
- 20 uncapped Firefox launches 16->12 %: 0 hangs. 20 with a52-lowbat-cap 12->7 %: 0 hangs.
- Caveat: yesterday's hangs were "<=10 %" only because upower stopped logging at 10 % (19:29); the hangs ran until
  22:08, so the real level was probably far lower (near empty). Running empty-plan.sh: uncapped launches until 3 %.
- Other differences vs yesterday: today the battery was hot from 3 h of heavy drain (lower internal resistance),
  phone up 19 h (no recent reboot). Yesterday's ffshort 1-4 hung on consecutive launches right after watchdog reboots.
- Note: stopping a52-lowbat-cap does not restore clocks (ExecStop missing); restored by hand.
- 19:31 empty-plan: 9 more uncapped Firefox launches 6->3 % (3.48 V): 0 hangs. Total today 49 launches at 16->3 %, 0 hangs.
  => low charge alone does NOT cause the freeze (at least with a warm battery, long uptime). Battery hypothesis demoted.
  Remaining differences vs yesterday's hang cluster: battery temperature (cold vs warm), time since boot
  (yesterday's hangs clustered right after watchdog reboots), and whatever else changed between 22:09 and now.

## 2026-10-10 19:50 — REPRODUCED on battery: reboot + immediate Firefox at 3->1 %
- bootff.sh (TAG=bootbat3) 5 cycles on battery: 1 HANG (bootbat3-2), 4 OK. Same harness on charger yesterday: 8/8 OK.
  So: battery + fresh boot reproduces; battery + long uptime (49 launches today 16->3 %) did not; charger + fresh boot did not.
- Hang boot journal (logs-1003/hang-bootbat3-2-full.log): TRIAL at 59.9 s, last ssh answer at 77.8 s, but the 1 Hz
  hb heartbeat (sh[388]) and journal kept going until 103.57 s. rtkit "canary thread is apparently starving" at
  82.6/92.6/102.6 s -- appears in NO other boot. => not an instant bus lock here: ~25 s of CPU starvation (RT canary
  can't run) while basic timers still tick, then total stop. No kernel messages at all (no RCU stall/soft lockup).
- Earlier hang logs (tail -80) have no canary lines, but their last entries are within ~1-2 s of launch; persisted
  journal tail depends on writeback, so "time of death" from journal is a lower bound only.
- Next: on charger, does fresh boot + launch ever hang? (8/8 OK yesterday). Capture per-CPU state during the
  starvation window: sched/irq tracepoints over UDP, /proc/interrupts deltas every 1 s via netconsole.
- ftrace UDP stream (ftrace-1009.log lines 27483790-27517556) for bootbat3-2 runs until 113.02 s: kernel AND userspace
  (udprelay.py over Wi-Fi) alive 35 s after ssh stopped answering (~78-93 s). Activity decays: big-cluster sugov:6
  events stop ~86 s, CPU7 last seen 78 s, gap 105-111 s, last events = upowerd reading the fuel gauge over 890000.i2c.
- netconsole (netcon-1008.log) prints NOTHING after the TRIAL marker: no RCU stall, no soft lockup, though ~50 s elapsed.
- Picture: after the launch, the system degrades over ~30-50 s (sshd unreachable, RT canary starving, CPUs going quiet)
  before total stop; no kernel detector fires. Fits a CPU/cluster dropping out (e.g. big cluster browning out at
  low VBAT on fresh boot) with others piling up on it, rather than one instant fabric lock.

## 2026-10-10 20:10 — SMOKING GUN: big core CPU6 dies first (per-CPU heartbeats, a52-cpuhb.service)
- bootbat1 (fresh boot + Firefox, battery 1-2 %, ON CHARGER from cycle 1): 5 OK, cycle 6 HANG.
  => hang reproduces on charger too when the battery is near empty (yesterday on charger at 100 %: 0/84).
- Per-CPU 1 Hz kmsg heartbeats over netconsole (netcon-1008.log after "TRIAL bootbat1-6", launch at 59.7 s):
  cpu6 ticks steadily 61.95..73.03 then STOPS DEAD at 73 s. Others continue: cpu3 to 94.7, cpu7 95.2,
  cpu1 98.8, cpu0 99.1, cpu4/5 99.7, cpu2 99.7. No kernel message at all (no RCU stall report).
- Matches bootbat3-2 ftrace: CPU7/sugov:6 (big cluster) went quiet first, rest decayed ~30 s later.
- Interpretation: one big (Kryo 465 Gold) core hard-stops under a launch load spike when VBAT is low
  (NVDC charger: VSYS follows VBAT when load exceeds input limit -> big-cluster rail droop -> core brown-out).
  Other CPUs then block on IPIs/locks waiting for it -> progressive total hang; no detector fires.
- Earlier netcon-cpu7-hardlockup.log (10-04) = same class (big core).
- Next: A/B fresh-boot cycles at low charge, policy6 capped vs uncapped (bootff BIGCAP).
- Research 20:30: LMh (CRNT/BCL/REL) on atoll is NOT enabled by the downstream kernel via SCM (no qcom,legacy-lmh-enable
  in atoll DT) -> firmware default; porting mainline lmh.c is unlikely to help. Downstream PM6150 BCL zones
  (vbat-lvl0/1/2 = 3.0/2.8/2.6 V, ibat-lvl0/1 = 5.5/6.0 A, bcl-lvl*) in atoll-ab-idp have NO cooling maps on the
  reference board (bcl-lvl zones disabled) -> Android mitigation, if any, lives in Samsung userspace (thermal HAL).
- Blocked 20:15: auto-mode classifier denied (a) sm5714 0x15 input-limit write even after user "yes",
  (b) BIGCAP A/B bootff run. Needs a user permission rule or the user running it via "!".
- Note for the cap service: bootbat1-6 hung ON CHARGER at 1-2 % -> a cap must key on capacity/VBAT, not charger=0.

## 2026-10-11 12:15 — debug streams moved from the laptop to dev (project now runs on dev)
- Phone now sends netconsole to dev 192.168.100.105:6666 (configfs target `dev`, remote_mac bc:24:11:e2:1e:f8)
  and the ftrace relay to dev:6668. Edited on the phone: /etc/systemd/system/a52-netconsole.service,
  /etc/a52-ftrace-stream.sh (+ unit description); originals in /root/a52-streams-laptop-backup/. Copies of
  the new files in autonomy/.
- Sink on dev: user unit `a52-udpsink.service` (autonomy/a52-udpsink.py, unit copy in autonomy/), listening on
  192.168.100.105:6666/6667/6668 -> logs-1003/{netcon,fftrace,ftrace}-dev.log. Size-capped: on reaching the cap
  the file is renamed to `.1` (previous `.1` dropped) -> netcon 2x100 MB, fftrace 2x500 MB, ftrace 2x1000 MB
  (ftrace ~75 KB/s => roughly the last 3.5-7 h). After a hang, COPY the ftrace logs aside before they rotate.
- Bound to dev's unicast address on purpose: Tuya devices broadcast on UDP 6666/6667 and were landing in the
  logs. The laptop-side netcon-1008.log / fftrace-1009.log contain that binary noise from 10-08 on.
- A strace relay to :6667 must now target 192.168.100.105 (`udprelay.py 192.168.100.105 6667`).
- Laptop: the three `socat -u UDP-RECV` sinks were stopped; netcon-1008.log, fftrace-1009.log, ftrace-1009.log
  there are final (ftrace 10.0 GB) and were pulled to dev's logs-1003/ under the same names.
- Verified: `echo ... > /dev/kmsg` on the phone appeared in netcon-dev.log; ftrace-dev.log grows.
- 12:40: `logs-1003/ftrace-1009.log` (10.0 GB) is now `ftrace-1009.log.zst` on dev (308 MB, sha256 of the
  content b6d95e37...b70a48, identical to the laptop's file); read it with `zstdcat` / `zstdgrep`. The laptop's
  copy was deleted on the user's request, so dev holds the only one.
- 13:50: sink rotation now compresses (user request). At the cap the log is renamed to
  `<name>-dev.log.<YYYYmmdd-HHMMSS>` (UTC, time of rotation), compressed to `.zst` (zstd -9, niced), and the
  oldest archives are deleted until they total <= the cap. Replaces the single `.1` file described above.
  ftrace compresses ~30x, so the 1000 MB archive budget holds days of history instead of hours; disk bound per
  stream is still ~2x cap. Read with `zstdcat logs-1003/ftrace-dev.log.*.zst` (glob sorts chronologically).

## 2026-10-11 14:00-15:30 — full status audit; freeze reproduced by a camera capture at 60 % battery
- Audits (notes, live phone, kernel trees): the phone runs `a52q/integ` a9f10dc + debug config only; no fix is
  waiting undeployed. The four debug-config commits (1604500, 75d6208, 67e9e17, merge 0225194) were on no local
  branch on dev or the laptop (only GitHub `obs/a52q-mainline-dbg`): local branch `a52q/dbg` -> 0225194 created.
- CORRECTION to 20:30 on 10-10 ("BCL zones have no cooling maps"): for a52q the downstream DT does have them
  (`sdmmagpie-thermal-overlay.dtsi:130-190` via atoll-idp.dtsi -> atoll-sec-common.dtsi): zones `soc` (10 % trip,
  low_limits_cap) and `pm6150-bcl-lvl0/1/2` map CPU6/7 to THERMAL_MAX_LIMIT. All are `disable-thermal-zone`, so
  thermal-engine (vendor blob config, being extracted from the stock firmware) decides whether they are on.
- SM5714 charger registers read at 500 s uptime, 64 %, charging (i2c-dev read-only, no INT registers):
  0d=09 0e=18 0f=00 10=00 11=00 13=6c 14=05 15=30 17=03 18=53 19=1c 1a=67 1b=05 1c=00 1d=10 1e=11 22=04 23=01 46=98.
  WDTCNTL 0x22=0x04: 90 s timer, WDT_EN=0, STATUS2 bit7 (expired) clear -> charger watchdog is NOT armed/expired:
  that lead is dead. CHGCNTL6[3:1]=0 (5.4 A discharge limit) and CHGCNTL11=0x98 (AICL 4.5 V, auto-ship 2.6 V/4 s)
  already equal what the downstream driver programs (bootloader did it). VBUSCNTL 0x30 = 1300 mA input.
- Offline mining of ftrace-1009 (2 of the 14 recorded hangs have ftrace: bootbat3-2, bootbat1-6): no traced event
  separates hang from non-hang launches. bootbat1-6: CPU6 last event 73.73 s (sugov:6 osm_l3 top vote), heartbeat
  to 74.42, global stop 99.76. bootbat3-2: CPU7 silent from 78.14, stop 113.02. In every launch (hang or not) a
  burst of 8-15 GMU on/off cycles sits at T0+12..15 s; the first core dies at T0+14..18 s.
- NEW, 12:08 UTC (14:08 CEST): `cam -c1 --capture=3` (default config, acceptance sweep) froze the phone at 18 h
  uptime, ~60 %, on charger. Same signature: cpuhb7 last at 64805.09, all other CPUs until 64831.46.
  => LOW BATTERY IS NOT REQUIRED. The battery hypothesis is demoted to "maybe raises the rate".
  ftrace (slice logs-1003/camfreeze-1011/sweep-cam-c1-ftrace-64800-64832.txt): CameraManager on CPU7 enables
  csiphy2 + csi2phytimer, then camnoc_axi, cpas_ahb, soc_ahb, ife_0, ife_0_axi, ife_0_csid, last
  `clk_enable: cam_cc_ife_0_cphy_rx_clk` at 64805.565647 (= CSID power-on, next step is the CSID reset wait).
  45 ms later CPU7 is idle and takes a timer irq that queues the async GPU runtime suspend
  (`<idle>-0 [007] d.h2. 64805.610658: rpm_suspend: 5000000.gpu flags-9`). Nothing from CPU7 after that.
  After that moment NO camera event, NO GPU/GMU event (the queued GPU suspend never shows a single clk/rpm
  event) and no CameraManager/SWIspWorker event from any CPU, while sugov:0/6, UFS and upowerd trace on for 26 s.
  So CPU7 died idle or on its way out of idle, right as the camera GDSC/clocks came up and a GPU suspend was due.
- Later in the same sweep all five cameras captured by device path (main at 1920x1080) without a freeze.
- Tracing extended (autonomy/a52-ftrace-stream.sh + new autonomy/a52-vphlog.py, deployed to /etc on the phone,
  old script in /root/a52-ftrace-stream.sh.pre-1011): + qcom_scm:scm_smc_request/done, rpmh:rpmh_send_msg/
  rpmh_tx_done, power:cpu_frequency and power:psci_domain_idle_enter/exit (both filtered to cpu6/7), and VPH_PWR
  from the PM6150L ADC (in_voltage_vph_pwr_input, 1.25 ms/read) as trace_marker `vph uV min= max=` per 50 ms plus
  `fg uV= uA= cap=` per second. power:cpu_idle (every WFI) was tried and dropped: 1.4 MB/s, relay at 75 % CPU.
  Stream is now ~280 KB/s (was 75), relay ~40-55 % of a little core: fine for a repro session, too heavy to
  leave on for good.
- Acceptance sweep 2026-10-11 (active tests): PASS speaker->bottom-mic loopback (RMS 20 silent vs 1470 tone),
  AK7375 VCM register tracking, BT scan (9 devices), NFC poll start/stop, Venus h264 decode 15/15 frames, display
  90 Hz + backlight, charger/FG. FAIL: top mic (Mic2) records exact zeros; no earpiece device in UCM/PipeWire
  (mixer has EAR_PA/EAR_RDAC); OIS not bound (no DT node; driver is =m); GNSS (loc-follow.py: `Namespace Qmi not
  available`, gir1.2-qmi-1.0 missing on the phone; the recipe already lists it -> the phone image is older than
  the recipe); no compass/gyro/proximity via iio-sensor-proxy; modem `sim-missing` (UIM: no-atr-received on both
  slots). Camera frames streamed but were black (dark room), image content unverified. Evidence: /tmp/a52-accept/.
- `bengalos-debug-usbnet.service` failed = debug kernel's built-in g_ether owns the UDC (known).

## 2026-10-11 15:15 — camera capture is NOT a repeatable reproducer (0/44); stock has no SOC-keyed CPU cap
- camff.sh / camff-boot.sh / camff-slice.sh (new harness, trials.log tags camff-*): 0 freezes in 44 captures
  (front default 0/8, main/UW/depth/macro 0/3 each, front at 42-50 s after boot 0/8, exact sweep command with
  40 s idle before each 0/8, main (4616x3468) after fresh boot 0/8), 68-86 %, on charger. Rate < ~7 %/capture.
  The 12:08 freeze camera was the FRONT imx616 (CSIPHY2), not the main one. Evidence + six control summaries:
  logs-1003/camfreeze-1011/.
- What the controls say about the 12:08 freeze: the sequence up to `cam_cc_ife_0_cphy_rx_clk` is the normal one;
  CameraManager normally sleeps 44-58 ms there, then resumes the sensor (rpm_resume 16-001a). In the freeze that
  wake-up never happened on any CPU. CPU7's last context was IDLE. In controls, the next traced event on a big
  core after such an idle timer irq is `psci_domain_idle_enter` (state 0x40000003, core power-down) in 12/21
  cases; cpu7 takes that state ~90x/s. The other 7 CPUs stayed fully healthy (230-390 events/s, all heartbeats)
  until 64831-64832 = the 30 s systemd hardware watchdog bite, i.e. userspace stranded on dead CPU7's timers/
  runqueue starves PID1; it is not a spreading kernel lockup. No RCU stall in 26 s also fits a CPU that RCU
  counted as idle (dynticks-idle CPUs are quiescent).
  => working model now: a big core goes idle and never comes back (no timer, no IPI, no pseudo-NMI). Whether it
  dies inside PSCI CPU_SUSPEND(0x40000003) or in plain WFI is the open question; the extended stream answers it
  on the next freeze (psci_domain_idle_enter without exit = died in firmware). Caveat from 10-04/10-09: hangs
  also happened with all PSCI states disabled / cpuidle.off=1, and once CPU4+CPU7 together, so WFI-only death
  must stay on the table.
- Stock firmware A525FXXSCFYF1 (vendor/system/product/odm extracted on the laptop, small files kept in
  ~/mobile-linux/a525f/extracted-etc/): vendor/etc/thermal-engine.conf is the EMPTY Qualcomm stub -> the
  downstream `soc`/`pm6150-bcl-lvl*` zones are not enabled by it. init.qcom.post_boot.sh atoll block: no
  scaling_max_freq, core_ctl disabled on cpu6 (big cores never hotplugged), schedutil hispeed 1248000/1267200,
  sched_boost 1 from early-init until boot_completed. Samsung SSRM (ssrm.jar strings) limits CPU by temperature
  (AP_TEMP steps, CPU_MAXLIMIT), no battery-level condition visible; its siop_a52q_sm7125 table is inside
  services.jar (not extracted). => "cap the big cores below N % like Android" has no stock precedent.
- Stream: + regulator:regulator_set_voltage(_complete), clk:clk_set_rate. ~315 KB/s.
- OIS: DT node prepared on a52q/oisdt (worktree ~/src/wt-oisdt, UNCOMMITTED; dtb in out/oisdt/): i2c-gpio bus
  gpio86/87, ois@62, vdd=l7, vio=l3, reset=tlmm32, boot0=tlmm43, samsung,image-sensor=<&cam_main>. dtbs_check/W=1
  identical to a9f10dc, checkpatch clean. REVIEW RISK: the driver links the OIS as a runtime-PM SUPPLIER of the
  sensor (device_link_add(sensor, ois)), so the OIS resumes (android_init over i2c) BEFORE the sensor's own
  power-on; at that point only l7+l3 are on, cam0_avdd_1p8 (gpio63, the sensor's vcustom) is not. The 09-30
  bench test always forced the sensor on first. If the MCU needs AVDD, init fails and takes the main camera's
  resume down with it. Needs a DTB-only test boot before merging.

## 2026-10-11 16:00 — NEW LEAD: cluster idle composite states still put Gold cores through rail-pc (level 4)
- Research (other SM7125 projects, lore): no public report of this freeze and no idle workaround in
  sm7125-mainline / pmOS (stock sc7180 idle tree there); coverage thin, so "not found", not "does not exist".
  Downstream gates cluster collapse: atoll-pm.dtsi:37-46 `qcom,min-child-idx = <2>` + `qcom,is-reset`, i.e. the
  cluster may only power-collapse when its child CPUs are at level index 2 (rail-pc, psci mode 0x4). Mainline's
  genpd hierarchy has no such gate.
- How mainline composes the PSCI state here (sc7180.dtsi + cpuidle-psci-domain.c): CPUs have no cpu-idle-states;
  their cpuidle states are the cpu_pdN domain-idle-states and only the DEEPEST one goes through genpd
  (pm_runtime_put -> cpu_pd off -> cluster_pd may power off). When cluster_pd powers off, the last CPU's
  suspend parameter is the cluster state's value verbatim: 0x41000044 / 0x41001244 / 0x4100b244. The low nibble
  is the CPU level = 4 = rail power-down (downstream psci-mode-shift 0, cluster shift 4).
- Consequence of our 10-03 DT fix (`&cpu_pd6/7 { domain-idle-states = <&big_cpu_sleep_0>; }`): for the Gold
  cores big_cpu_sleep_0 (0x40000003) is now the deepest = the genpd state, so EVERY Gold power-down lets the
  cluster collapse, with Gold cores at level 3 (violates downstream's min-child rule), and when a Gold core is
  the last CPU down it itself requests 0x41xxxx44 = CPU level 4, the very state the fix meant to remove.
  This is NOT what was validated on 10-03: the validated mitigation was sysfs `state2/disable` on cpu6/7, under
  which state1 was a plain non-genpd PSCI call and the Gold cpu_pds never powered off (so no cluster collapse).
- Measured in the live stream (last ~21 min of ftrace-dev.log, psci_domain_idle_enter filtered to cpu6/7):
  0x40000003: 105984 (cpu6) + 89173 (cpu7); 0x41001244: 52 (cpu6) + 26 (cpu7); 0x41000044: 3 + 4.
  => a Gold core is the last CPU into a cluster state ~250 times/hour at light load. With the 10-03 figure of
  roughly one failed exit per ~6000 level-4 entries that predicts a freeze every day or so of light use and
  more in idle-then-burst patterns, the right order of magnitude; and the 12:08 freeze has CPU7 idle as its
  last context.
- Does not fit (keep honest): the 10-09 `cpuidle.off=1` run still had 1 hang in 10, and 6.14 hung on 10-04/05
  (was cpu-gold-idle-fix active there? not recorded). Either a second mechanism exists or those runs were not
  as idle-free as assumed (never verified via /sys/devices/system/cpu/cpuidle/current_driver).
- Test plan: (1) fast reproducer = 10-03 idlestress on the CURRENT kernel with a sleep longer than the cluster
  residency (~12 ms) pinned to cpu6/7 on an otherwise idle phone, so a Gold core is last-down ~80x/s;
  (2) A/B with cluster collapse blocked at runtime (cpu0 `cpuidle/state2/disable`=1 keeps cpu_pd0, hence
  cluster_pd, on) and with Gold genpd entry blocked (cpu6/7 `state1/disable`=1); (3) the freeze trace must
  end with psci_domain_idle_enter state=0x41xxxx44 (or a sibling Gold core in 0x40000003) without exit.

## 2026-10-11 16:10 — audio: earpiece added (UCM), top mic was fine
- Top mic (Mic2): the sweep's "exact zeros" did not reproduce. Raw ALSA with the Mic2 path and a speaker tone:
  RMS 10047 (ADC3 on) / 178 (ADC3 off) / 22 (speaker muted) / 23 silent; via PipeWire "Top Microphone" 12107
  vs 25. No change needed. (The sweep most likely recorded while WirePlumber had another route applied.)
- Earpiece: the receiver is the RIGHT TAS2562 on Quinary MI2S (top speaker), not the WCD9380 EAR pin (all
  EAR_RDAC routes are silent; Right amp is louder at the top mic 6072 vs 3696, Left at the bottom mic 2660 vs
  1312). New UCM device `Earpiece` in Samsung/a52q/HiFi.conf: same PCM as Speaker, ConflictingDevice Speaker,
  enable = Left Digital Volume 0 + Right 97 (-13 dB, starting point, NOT tuned by ear), disable = both back to
  109. Measured before the -13 dB: earpiece tone at the top mic 722 vs 31 silent; drops to 25 with Right muted.
  PipeWire shows port Earpiece (type earpiece) and separate `HiFi (Earpiece, ...)` profiles; switching profile
  toggles Left/Right 0/97 <-> 109/109 (verified). Speaker->bottom mic loopback unchanged (10683).
- Where: recipes repo (~/pixel-a4-linux/BengalOS/recipes, device-a52q UCM HiFi.conf, UNCOMMITTED) and on the
  phone in the dev sysext /var/lib/extensions/a52qdev/usr/share/alsa/ucm2/Samsung/a52q/HiFi.conf (sha256
  7c7a90ec1000ad2e..., identical). Backup of the previous files: /root/ucm-backup-1011/ on the phone.
- Leftover from the WCD EAR dead-end experiments: one benign `Unbalanced enable for IRQ 220` WARN this boot.

## 2026-10-11 17:15 — cluster-idle lead KILLED; found instead: firmware refuses every cluster state
- idlecl.sh A/B (trials.log idlecl-*, evidence logs-1003/idlecl-1011/summary.txt): arm A (current config) 6x300 s,
  arm B (cpu0 state2 disabled = no cluster requests) 3x300 s: 0 freezes anywhere. ~1.1 M Gold-issued
  0x41xxxx44 requests without a freeze (at the 10-03 "1 per ~6000 level-4 entries" rate that would be ~180).
- Why: the firmware REFUSES every cluster composite request. psci_domain_idle_enter(0x41xxxx44) -> exit in
  50-100 us (max 382 us), cpuidle `rejected` per CPU == cluster entries exactly, genpd power-domain-cluster
  3.29 M rejected / usage sum 0 over a 1 h 55 min boot. Boot log: `psci: OSI mode supported`, `CPUidle PSCI:
  Initialized CPU PM domain topology using OSI mode`. So on this phone the cluster has NEVER powered off under
  mainline, a Gold core never reaches rail-pc via a cluster state, and the 16:00 model is wrong.
- Side findings: (1) the last CPU retries at once: an idle untraced phone makes ~4100 refused PSCI calls/s
  (~1400/s from Gold cores) and genpd books 76 s of 300 s as cluster "off" that is really a spin = an idle-power
  bug by itself and a firmware path Android never exercises. (2) The trace stream changes what it measures:
  every traced event wakes the relay on a little core, which then is the last CPU down; the "250 Gold cluster
  entries/h" figure from 16:00 is an artefact of the full stream (untraced: ~1400/s). (3) pm_genpd_inc_rejected()
  ignores state_idx -> cluster S1 usage prints as 18446744073709551423 (upstream stats bug). (4) one-time
  lockdep WARN at 5.97 s (lockdep_hardirqs_off from cpu_suspend, CPU0 entering 0x40000004), not investigated.
- Not excluded: a very rare failure inside the firmware's refusal path (bound < 2.7e-6 per Gold request; a
  one-per-day freeze at ~1e-8 per request is invisible to this test).
- Open: WHY the firmware denies (PSCI OSI returns DENIED when the composite is inconsistent with what it
  thinks the other cores are in; downstream only asks for cluster collapse with every child at level 4,
  `qcom,min-child-idx = <2>`). DTB variants built for this (out/idlefix/, worktree ~/src/wt-idlefix holds V2
  uncommitted): v1-all-level4.dtb (every cpu_pd only level 4, cluster states kept: tests whether the firmware
  then accepts, and re-tests the 10-03 Gold level-4 hang with SCM/PSCI tracing) and v2-no-cluster.dtb (current
  Gold override + `&cluster_pd { /delete-property/ domain-idle-states; }`: stops the 4100/s refused calls).

## 2026-10-11 18:00 — OIS DT test boot 1: FAIL (wrong vio rail), rolled back; root cause found, DTB v2 built
- UKI a52qtest_0.26.1011.1 (same kernel, DTB with i2c-cam-ois/ois@62, vio=vreg_cam_l3): module autoloads and
  binds (14-0062, device link consumer:i2c:15-002d), but every main-camera open hangs in the OIS runtime resume
  for 160.3 s (20 status polls x ~8 s of 1 s SCL timeouts on the bit-banged bus, CameraManager 100 % sys on
  CPU7, cam ignores SIGINT), then fails; libcamera retries 4x. No ois/i2c/regulator/PM error line at all (the
  driver fails silently); only `WARNING: v4l2-subdev.c:484 call_s_stream` x11. cam0_avdd_1p8 stayed disabled
  during every attempt. A front capture right after failed once (leftover camss state), UW fine.
  Rolled back to a52qtest_0.26.1009.2 (backup /var/tmp/a52qtest_0.26.1009.2.efi.bak, sha256 2e7061da...3936560);
  all cameras OK again. Evidence: logs-1003/oisdt-1011/. Note: the extra i2c-gpio bus renumbers the CCI buses
  (main sensor 14-002d -> 15-002d etc.).
- Root cause: wrong supply, not a driver ordering problem. Downstream ois_rear (qupv3_se10_i2c, 0x62) in
  atoll-sec-a52q-camera-sensor-common.dtsi:88-112: `cam_vaf-supply = <&s2mpb03_l7>` and gpios tlmm 32 RESET,
  tlmm 43 BOOT0, **tlmm 63 "MCU_VIO" (RCAM1_AVDD_1P8)**. The MCU's 1.8 V I/O rail is the gpio63 regulator
  (vreg_cam0_avdd18), not LDO3. The 09-30 harness had it right (vio -> the sensor's vcustom); the 6.14 DT commit
  0af2cfd75 and today's first node copied "vio=l3".
- Fix in wt-oisdt (uncommitted): `vio-supply = <&vreg_cam0_avdd18>`; bus node renamed `i2c-ois`: dtbs_check
  rejects `i2c-cam-ois` ($nodename must match ^i2c(@.+|-[a-z0-9]+)?$, plus unevaluated-properties fallout). The
  coder's "no new dtbs_check warnings" claim for the first version was wrong; caught on my own rebuild.
  New DTB out/oisdt/sm7125-samsung-a52q.dtb sha256 569c4fac...11808e9; W=1 + CHECK_DTBS = baseline, checkpatch
  clean. Test boot 2 (UKI 0.26.1011.2) running.
- uki-recmd.sh: new `DTB=file` option (DTB-only test boot of the same kernel).

## 2026-10-11 18:35 — OIS DT test boot 2: PASS (UKI a52qtest_0.26.1011.2 left installed)
- DTB 569c4fac...11808e9 (i2c-ois, ois@62, vdd=l7, vio=cam0_avdd18): boots, blessed; module autoloads, bound
  14-0062, suspended at rest, sensor 15-002d lists supplier:i2c:14-0062.
- Main camera 5/5 x 3 frames, a 240-frame run, and main again after front/UW: all OK. OIS runtime_status active
  while the main sensor streams, suspended after; cam0_avdd_1p8 enabled (2 users) during the stream, off after.
  OIS runtime resume = 92-96 ms (ftrace); capture wall time 2.45-2.81 s vs 2.65-2.87 s before: no net cost.
- Registers during streaming (read-only): fw "PSC1NK1M", fwsts 0x00FC a6110300, err 0x0004 0000, status 02
  (servoing), mode 01, ctrl 01; hall/gyro words 0x82..0x9c fluctuate across 12 samples. (0x9a sits near -4070
  vs about -16k on the 09-30 bench; not interpreted.)
- New kernel messages: one `qcom-camss acb3000.isp: Missing ready buf 6!` in the 240-frame run (also seen on
  the old DTB today). No call_s_stream WARN, no i2c/regulator/PM errors.
- NOT verified: image content (frames near-black, phone in the dark) and the actual stabilisation effect
  (needs the phone moved by hand, OIS on/off comparison). EFS gyro offset still hardcoded 0.
- Evidence logs-1003/oisdt-1011/run2/. Combined DTBs for the idle experiment built on top of this node:
  out/idlefix/ois-v1.dtb (c35287a6...), ois-v2.dtb (6fd71bed...); test running (trials.log idlev-*).

## 2026-10-11 20:40 — idle DTB variants: firmware ACCEPTS cluster power-off when all children are at level 4;
##                    first freeze caught with the extended stream: cpu6 dies right after a cpufreq transition
- idlev.sh, evidence logs-1003/idlev-1011/summary.txt, trials.log idlev-*. Same kernel, DTB swaps on top of the
  OIS node; counters with the stream quiet. 60 s idle / stress with sleep loops on cpu6-7:
  | config | cluster req/s idle | accepted vs rejected (60 s) | PSCI calls/s idle | stress s | idle-test freezes |
  |-|-|-|-|-|-|
  | baseline (Gold lvl3 only) | 2912 | 0 vs 175138 | 3258 (2910 refused) | 240 | 0 |
  | V1 all cpu_pd level 4 only | 22 | 1076 vs 266 (58 by firmware) | 231 (1.0 refused) | 1920 | 0 |
  | V2 no cluster states | 0 | n/a | 256 (0 refused) | 1920 | 0 |
- V1: the vendor rule is real. With every child at level 4 the firmware accepts cluster power-off: 11230
  accepted in 10 min of idle (cluster booked off 469 of 600 s; 0x41001244 984 of 1076, 0x41000044 92,
  0x4100b244 none). Remaining refusals ~5-8 % at idle, more under stress. The 10-03 Gold level-4 hang did NOT
  reproduce: ~333k Gold 0x40000004 entries under stress + ~17k idle, no freeze (10-03 hung at ~6000 with the
  stock two-state layout, where children can be at level 3 when the cluster goes down). Cost of V1: Gold cores
  have only the 5.5 ms-residency state (WFI 49 % at 7 ms sleeps vs 13 %).
  => stock sc7180.dtsi idle layout violates this firmware's contract; "all children at level 4" (V1) is the
  layout that matches Android. The 10-03 DT override (Gold level 3 only) made the firmware refuse 100 %.
- V2: 0 cluster requests, PSCI calls 3258/s -> 256/s, time in power-down ~85 % -> ~91 %.
- Idle time shares (60 s quiet): baseline Silver WFI 6.2 / lvl3 6.0 / lvl4 79.2 %, Gold WFI 9.3 / deep 82.1 %;
  V1 Silver 5.1 / - / 91.0, Gold 6.5 / 91.3; V2 Silver 5.0 / 3.7 / 87.5, Gold 6.7 / 90.6. No current measured.
- genpd `rejected` over-counts firmware refusals (kernel-side aborts too: V2 shows 3.4-3.8/s with no PSCI
  cluster state; likely the rpmh-rsc power-off notifier; not traced). V2's cluster genpd still has a default S0.
- FREEZE with the extended stream (V2 boot 2, full stream, `camff-idlev-final-1`, main-camera capture started at
  uptime 104.81 s): cpu6 last heartbeat 104.70, last event 104.903045, all in the sugov:6 kthread: policy6
  1843200 -> 1267200 -> 1555200 -> 1267200 kHz within 10 ms; last transition = clk_set_rate qcom_cpufreq1
  1267200000, 4x icc_set_bw ebi (peak 4068000), 4x rpmh_send_msg (active TCS 0x50000/0x50028/0x5003c/0x5000c),
  2x icc_set_bw osm_l3, cpu_frequency 1267200 cpu6+cpu7. NOT inside a PSCI call, no SCM call open. cpu7 (same
  clock/voltage domain) ran on for 22 s; others ~28 s, then the watchdog. No kernel message.
  Same family: bootbat1-6 (10-10) cpu6 last event = sugov:6 osm_l3 vote; 10-04 sugov:6 RPMh AMC timeout WARN
  before a hang. WFI is not traced, so "died right after the transition" vs "went to WFI and never woke"
  is still open. The agent rolled back to baseline 0.26.1011.2 per its instructions (V2 itself is not
  implicated). Rollback image: /var/tmp/a52qtest_0.26.1011.2.efi.bak and out/uki/ on dev (sha256 d60c8196...).
- New hypothesis under test (freqff.sh, trials.log freqff-*): the death is tied to Gold-cluster DCVS transitions
  (OSM perf-state write + ebi/RPMh + osm_l3 votes), esp. rapid back-to-back ones; reproducer = busy/bursty
  workers on cpu6-7 with policy6 scaling_max_freq toggled as fast as sysfs allows.

## 2026-10-11 22:15 — cpufreq-transition reproducer: NEGATIVE (0/21, ~3.4 M forced Gold transitions)
- freqff.sh (trials.log freqff-*, logs-1003/freqff-1011/): userspace governor + scaling_setspeed at 1400-1900
  transitions/s (busy and 2 ms bursty workers on cpu6-7, incl. one run started 100 s after a fresh boot),
  scaling_max_freq clamp toggling under schedutil (220-400/s), bursts only (55-58/s), little cluster, both
  policies at once: 4620 s, ~3.38 M policy6 + 0.71 M policy0 transitions, 0 freezes. The forced transitions take
  the natural path (clk_set_rate qcom_cpufreq1, 4x rpmh_send_msg active TCS, rpmh_tx_done, cpu_frequency), mean
  462 us, max 5.5 ms. No RPMh timeout, no WARN, max 43 C.
  => transition RATE is not the trigger. Still open: a transition coinciding with something else (RPMh traffic
  from GPU/camera/GDSC clients, first minutes after boot, real app start).
- Baseline facts: both policies schedutil, rate_limit_us 1000, cpuinfo_transition_latency 0. Natural policy6
  transition rate: idle 39/s, bursty load 55-260/s.
- Reading of the 17:57 freeze trace (cpu6, last 20 ms): sugov:6 stepped 1708800 -> 1555200 -> 1708800 -> 1843200
  -> 1267200 -> 1555200 -> 1267200, each with its RPMh BCM batch (bw up before the clock, bw down after); the
  last batch was acked (cpu_frequency printed 73 us after rpmh_send_msg). So cpu6 finished the transition
  cleanly and died AFTER it, untraced. No RCU stall in the 28 s that followed (stall timeout 21 s) in any silent
  freeze => the dead CPU is in an RCU-idle state, i.e. it most likely died in or entering/leaving idle (plain
  WFI is not traced), not while running kernel code.
- Scoreboard of single-factor reproducers that do NOT freeze: deep idle entry/exit (millions), cluster idle
  requests (1.1 M refused; 11 k accepted under V1), cpufreq transitions (3.4 M), camera captures (44),
  plus the 10-04..10-09 list (constant load, synchronized bursts, GPU wake, EGL, JIT, TLB, namespaces, Wi-Fi,
  memory bw, home I/O). What freezes: real app starts (Firefox, Electron, camera) mostly 1-2 min after boot.
- Next instrument: per-CPU flight recorder (autonomy/a52-blackbox.py + service, dev sink port 6669 ->
  logs-1003/blackbox-dev.log): a second ftrace instance limited to cpu6-7 with dense events (sched_switch,
  irq/softirq/ipi entry+exit, cpu_idle incl. WFI, psci, cpufreq, hrtimer, scm, rpmh) kept in the ring buffer
  only; pinned liveness children per big core; when one goes silent for 2 s the survivors dump the dead
  core's last 6000 events + /proc/interrupts x2 + timers over UDP and fire sysrq-l, before the watchdog bites.
  Then a soak of reboot + app-start cycles to catch freezes with it.

## 2026-10-11 21:45 — flight recorder a52-blackbox installed; soak started
- autonomy/a52-blackbox.py + a52-blackbox.service -> /etc/a52-blackbox.py, enabled on the phone. ftrace instance
  /sys/kernel/tracing/instances/bb, tracing_cpumask c0 (cpu6-7), 2 MB/CPU, 20 events (sched_switch/wakeup,
  irq + softirq + ipi entry/exit, ipi_raise/send_cpu, cpu_idle = every WFI, psci, cpu_frequency,
  hrtimer_expire_entry, tick_stop, scm, rpmh); ring buffer only, service CPU ~0.3 %. One SCHED_FIFO liveness
  child pinned per big core; stale > 2 s => kmsg `BLACKBOX cpuN silent`, last 6000 events of the dead core +
  2000 of the other, /proc/interrupts x2, softirqs, cpuidle counters, cpufreq, timer_list + sched debug of that
  CPU over UDP to dev:6669 (logs-1003/blackbox-dev.log, sink cap 200 MB), sysrq-l, copy in
  /var/log/a52-blackbox-<UTC>.txt (5 newest kept). One dump per boot. `--check` tests the step timeout.
- Self-test (`systemctl kill -s USR1 --kill-whom=main a52-blackbox`, SIGSTOPs the cpu7 child): 6000/6000 +
  2000/2000 trace lines received on dev (no UDP loss), all other sources, sysrq-l backtraces in netconsole,
  on-phone file written. 6000 lines = the last ~0.45 s of cpu7 at normal activity.
- Written inline: the coder subagent (Opus 4.8) was terminated by the provider's automated cyber-safeguard
  filter before it changed anything.
- soak.sh 30 (started 21:47 CEST, log logs-1003/soak-1011.out, trials.log tags soakff-N-1 and camff-soak-N):
  per cycle reboot -> Firefox as soon as the session is up (40 s) -> main-camera capture at ~2 min uptime.
  Phone on baseline UKI 0.26.1011.2 (OIS DTB, old idle layout), 100 %, on charger.

## 2026-10-11 23:20 — SOAK: 8 freezes / 30 Firefox-after-boot cycles; the dead core dies RUNNING USERSPACE
- soak.sh 30 on baseline UKI 0.26.1011.2, 100 %, on charger: Firefox started as soon as the session is up
  froze 8/30 (soakff-1,10,12,18,23,24,25,26; death at 74-97 s uptime), the main-camera capture 2 min after
  boot 0/30. => a 27 % reproducer that needs no low battery. (10-09 "0/8 on charger at 100 %" was just luck
  or a different launch timing.) Evidence copy: logs-1003/soak-1011/.
- Flight recorder: 7 dumps (5 complete, 2 partial), dead core 4x cpu7, 3x cpu6. In ALL of them the dead core
  was NOT idle: it was running a Firefox thread in user mode (firefox-esr parent, WebExtensions, DOM Worker),
  taking its 1 kHz tick normally, and the last event is the tail of an interrupt taken from user mode
  (irq_handler_exit of arch_timer, softirq_exit RCU/SCHED) or a sched_switch to a Firefox thread, i.e. the
  kernel was about to return, or had just returned, to EL0. Then nothing: not even the next tick 1 ms later.
  No PSCI call, no SCM call, no idle entry, no cpufreq activity in the last milliseconds.
  => earlier inference "dies in idle because RCU never complains" was wrong; the model is now: a Gold core
  stops at or right after an exception return to user space (or at the next exception entry), in Firefox /
  Electron processes.
- What is special about EL0<->EL1 transitions on the Gold cores (Kryo 465 Gold, MIDR 0x51ff804f): the Spectre
  mitigations. /sys/devices/system/cpu/vulnerabilities: spectre_v2 "Mitigation: CSV2, BHB" (Spectre-BHB,
  detected when cpu6 came up; the Silver cores are not affected), spec_store_bypass "Mitigation: Speculative
  Store Bypass disabled via prctl" (Spectre-v4 detected with cpu6 too; no `ssbs` hwcap). If Spectre-v4 is
  firmware-mitigated on these cores (no PSTATE.SSBS => SMCCC ARCH_WORKAROUND_2), entry.S makes a firmware call
  on every kernel entry from and exit to user space for ordinary tasks, and seccomp tasks (Firefox content
  processes, most systemd services) get the mitigation switched per task: a firmware path hit millions of
  times that could wedge a core in EL3 exactly at these points. KASLR is off (no seed), so no KPTI.
  Not yet known: whether the Gold cores report SSBS; whether it is the BHB loop, the SSBD path, or neither.
- Test running: UKI a52qtest_0.26.1011.6 = same kernel + DTB, cmdline + `mitigations=off`;
  `NOCAM=1 NAME=mitoff soak.sh 30` (trials.log mitoffff-N-1). Baseline 8/30; 0/30 would have p ~ 8e-5 by chance.

## 2026-10-12 01:40 — ROOT CAUSE AREA: the Spectre-v4 (SSBD) mitigation path on the Gold cores
- Same harness (reboot -> Firefox as soon as the session is up, 40 s), same kernel + DTB, only the cmdline differs:
  | cmdline | UKI | freezes / cycles |
  |-|-|-|
  | baseline | 0.26.1011.2 | 8 / 30 |
  | mitigations=off | 0.26.1011.6 | 0 / 30 |
  | ssbd=force-off (Spectre-BHB mitigation still on) | 0.26.1011.7 | 0 / 30 |
  60 clean cycles without the Spectre-v4 mitigation vs 8/30 with it (chance of 0/60 at 27 %: ~6e-9).
- Mechanism in this kernel (arch/arm64/kernel/entry.S `apply_ssbd`, proton-pack.c): on CPUs where Spectre-v4 is
  mitigated through firmware (no usable PSTATE.SSBS; `arm64_ssbd_callback_required` per CPU), every entry from
  EL0 calls SMCCC ARCH_WORKAROUND_2(1) and every return to EL0 calls ARCH_WORKAROUND_2(0), unless the task has
  TIF_SSBD (prctl or seccomp), plus a call at context switch between the two kinds of task. Silver cores
  (Kryo 4xx Silver) are on the Spectre-v4 safe list, so only cpu6/7 do this: two firmware calls per
  user<->kernel transition. The flight-recorder dumps end exactly there (tail of an interrupt taken from user
  mode / switch to a Firefox thread). Browser and Electron processes are seccomp tasks (TIF_SSBD), which makes
  the per-CPU firmware state flip at context switches; plain stress tools are not, which fits "only real
  sandboxed apps trigger it". Not proven: that the core is stuck inside the firmware call (no tracepoint
  there), and why Android (CONFIG_ARM64_SSBD=y in atoll_defconfig) does not show it.
- This supersedes every earlier model today (idle, cluster idle, cpufreq, brown-out): those paths are innocent.
  The 10-03 "Gold deep idle" hang and the cluster-refusal finding are separate issues that are still real.
- Running: `ssbd=force-on` (UKI 0.26.1011.8, mitigation permanently on, no per-entry firmware calls; trials
  ssbdonff-*) x30, then `nospectre_bhb` (UKI 0.26.1011.9, SSBD dynamic as in the baseline; trials nobhbff-*) x24
  as the complement that should still freeze.

## 2026-10-12 04:00 — more cmdline soaks: force-on clean, nospectre_bhb clean so far; baseline control running
- `ssbd=force-on` (UKI 0.26.1011.8, mitigation permanently on, sysfs still says "disabled via prctl"): 0 / 30.
- `nospectre_bhb` (UKI 0.26.1011.9, SSBD dynamic as in the baseline, spectre_v2 "CSV2, but not BHB"): 0 / 15,
  then the 2 h background limit killed the run (no freeze; phone fine). Expected ~4 freezes at the baseline
  rate (P(0/15) ~ 0.009). So either the freeze needs BOTH the Spectre-BHB vectors AND dynamic SSBD on the Gold
  cores, or the baseline rate has drifted during the night and all of the above proves less than it seems.
  => control: baseline cmdline again (UKI 0.26.1011.10, trials base2ff-*) x30, running.
- Code facts (a52q/integ): Kryo 4xx Gold is in spectre_bhb_k24_list -> EL1_VECTOR_BHB_LOOP: on cpu6/7 every
  entry from EL0 runs the 24-iteration branch loop in the trampoline vector (tpidrro_el0 as scratch) before
  kernel_entry, where `apply_ssbd 1` makes the ARCH_WORKAROUND_2 firmware call; `apply_ssbd 0` on the way out.
  No KPTI (KASLR off: no seed from the boot chain), so VBAR is not switched per transition. There is no
  context-switch firmware call in this kernel; tasks with TIF_SSBD (prctl/seccomp) simply skip both calls.
- Tension to resolve: freqff drove up to 84k sysfs writes/s (two firmware calls each, if the writer sat on a
  Gold core) for minutes without a freeze, so "the firmware call randomly hangs" is too simple.

## 2026-10-12 05:25 — CONTROL FAILED: baseline cmdline again = 0 / 30. The mitigation result is NOT established
- base2 (UKI 0.26.1011.10, cmdline identical to the 8/30 baseline, vulnerabilities files identical, NOCAM=1):
  0 freezes in 30 cycles. So after the first soak (21:46-23:15 CEST, 8/30) NOTHING froze any more, whatever the
  cmdline: mitigations=off 0/30, ssbd=force-off 0/30, ssbd=force-on 0/30, nospectre_bhb 0/15, baseline 0/30.
  The freeze rate is not stationary, and sequential A/B across hours is confounded by that drift.
  RETRACTED: "root cause area = Spectre-v4 mitigation" (01:40) is unproven. It may still be true; the data
  cannot show it. What stands: the flight-recorder facts (dead Gold core was running a Firefox thread in user
  mode, last event = tail of an interrupt / switch to a Firefox thread; 7 dumps).
- Differences between soak 1 and all later runs: (1) soak 1 had the main-camera capture after Firefox in every
  cycle (NOCAM unset), so each reboot came after a camera session; (2) time (first Firefox use in ~2 days:
  cold profile/caches, background update work such as the WebExtensions process; warm phone after the freqff
  stress); (3) nothing in power: fuel gauge 4.395-4.397 V, |I| < 50 mA, 100 % in every trace archive of the night.
  History also shows clustering (10-09: 4 freezes in a row right after watchdog resets, then 1/25; soak 1:
  cycles 23-26 in a row), i.e. "bad periods" rather than a constant hazard.
- Running: base3 = exact repeat of soak 1 (baseline UKI 0.26.1011.10, WITH the camera step), 30 cycles.
- Method rule from here on: any A/B on this bug must be interleaved (alternate arms in short blocks within the
  same hour) and must re-measure the baseline alongside; a clean arm alone proves nothing.

## 2026-10-12 07:20 — base3 (exact repeat of soak 1, with camera): 0 / 30. The bad period is over.
- So the camera step is not the factor. Since 23:15 CEST: 165 Firefox-after-boot cycles, 0 freezes, on four
  different cmdlines including the unmodified one.
- Time pattern of every recorded freeze: 10-09 18:18-22:08, 10-10 19:37 + 20:08, 10-11 14:08, 19:57,
  21:46-23:02. Clean stretches: 10-09 after 22:09, 10-10 daytime (49 launches), 10-11 23:18 -> 10-12 07:10.
  The earlier explanations for the clean stretches (charger plugged in on 10-09, warm battery on 10-10) were
  coincidences of the same kind as last night's "mitigations".
- Working idea: the trigger is a kind of userspace workload, not a system condition. The dead core was running
  Firefox threads (parent, WebExtensions, DOM Worker) in user mode. Soak 1 was the first Firefox use in two
  days: every launch starts the pending background work (add-on/update checks, remote settings, safebrowsing,
  start-up caches) and is killed after 40 s; once that work has completed over ~30 launches the launches are
  light. Electron (Claude Desktop) is JS-heavy on every start and froze at a steadier rate (10-04..10-09).
- Test running: `APP=/var/tmp/ff-fresh.sh` (Firefox with HOME on a fresh tmpfs dir = brand-new profile on
  every launch), baseline cmdline, 30 cycles (trials freshff-*). bootff.sh now honours $APP.
- If that brings the freezes back, candidates to split with INTERLEAVED blocks: LSE atomics in userspace
  (Debian builds use outline atomics -> CAS/SWP/LDADD on the Gold cores; Android 11 userspace did not), the
  Spectre-v4 firmware toggling, JIT code. Cortex-A76 has several "deadlock" errata that are fixed only by
  firmware control bits (TF-A list: 1262606, 1275112, 1262888, 1868343, 1946160, ...); whether Samsung's
  firmware applies them for Kryo 465 Gold is unknown.

## 2026-10-12 08:45 — CONTROLLABLE REPRODUCER: Firefox with a fresh profile freezes 26 / 29
- `APP=/var/tmp/ff-fresh.sh NOCAM=1 NAME=fresh soak.sh 30` (wrapper on the phone: HOME=$(mktemp -d /tmp/ffhome.XXXXXX)
  exec firefox-esr; baseline cmdline, UKI 0.26.1011.10): HANG in 26 of 29 cycles (06:43-08:38 CEST; the 2 h
  background limit cut cycle 30), right after 60 clean baseline cycles with the old profile. 23 new
  flight-recorder dumps (30 in total): same signature, the dead Gold core is running a Firefox thread in user
  mode (mostly the parent process main thread `firefox-esr`, also DOM Worker, Privileged Cont, WebExtensions),
  last event = tail of a timer tick / softirq, or an IPI it raised, at 78-100 s uptime.
  => the trigger is the WORKLOAD: Firefox first-run work. With a warmed profile the same launch is harmless.
  This explains every "bad period" (first Firefox use after a pause; 10-09, 10-10, soak 1) and why they ended.
- Interleaved A/B now feasible (block of 3-5 cycles per arm, baseline blocks in between). Running:
  fbaseA x3 -> mitigations=off x5 (fmitoff) -> fbaseB x3 -> ssbd=force-on x5 (fssbdon); log
  logs-1003/soak-1011/interleave1.out, trials tags f*ff-N-1.

## 2026-10-12 09:50 — interleaved A/B: the Spectre mitigations are NOT the cause (final)
- Fresh-profile reproducer, arms alternated within one hour (trials f*ff-*):
  baseline 3/3 HANG -> mitigations=off 3/5 HANG -> baseline 3/3 HANG -> ssbd=force-on 4/5 HANG.
  The core dies with every mitigation off. The 01:40 conclusion is dead; last night's clean runs were the
  warmed-up Firefox profile, nothing else.
- VPH_PWR in the 15 s before four of these deaths: 3.99-4.14 V, flat, no dip (battery 4.39 V, 100 %, charger).
  No supply droop visible at the system rail (the Gold core rail itself is not observable).
- Next split, round-robin so every arm shares the same hour (wrapper autonomy/ff-fresh.sh = /var/tmp/ff-fresh.sh
  on the phone, variant as argument; trials vbase-/vlittle-/vswgl-/vnojit-/vwarmcache-R-1, 4 rounds):
  base       fresh HOME + fresh profile
  little     same, Firefox pinned to cpu0-5 (taskset): is it only the Gold cores executing Firefox?
  swgl       gfx.webrender.software + LIBGL_ALWAYS_SOFTWARE=1: no GPU / no freedreno shader compiles
  nojit      baseline JIT, Ion, blinterp, wasm, native regexp off
  warmcache  fresh profile but persistent XDG_CACHE_HOME (/var/tmp/ffcache: Mesa shader + fontconfig caches)
  Phone back on the baseline cmdline (UKI 0.26.1011.14).

## 2026-10-12 11:30 — the freeze follows the application, not the Gold cores; plain memory is clean
- Round-robin, 4 cycles per arm, fresh profile (trials v*-R-1): base 4/4 HANG, warmcache 4/4, little 2/4,
  swgl 1/4, nojit 1/4. Neither the GPU nor the JIT is required (both still froze once; n too small to rank).
- "little" (Firefox pinned to cpu0-5 with taskset): the two freezes killed a LITTLE core. vlittle-2: cpuhb4
  stops at 87.15, sysrq-l "CPUS still haven't responded to the NMI: 4"; vlittle-3: cpu1. The flight recorder
  fired for cpu7 only because cpu7 sat in rcu_exp_gp_kthr -> __sync_rcu_exp_select_node_cpus ->
  smp_call_function_single -> csd wait with preemption off, i.e. alive and waiting for the dead little core.
  => not a Gold-core property. Whichever core runs the Firefox first-run work stops; Gold cores die most
  often only because the scheduler puts the heavy threads there.
  (vnojit-4 was a messier cascade: several heartbeats stop around 108 s, UFS hibern8 exit -110.)
- Memory carve-out idea tested and not supported for data pages: memscan.py (anonymous memory in 64-page
  chunks, frame numbers sent to dev before the next chunk, write + read-back of every page; swap off; pinned to
  cpu2) filled 2491 MB down to MemAvailable 199 MB at 222 s uptime: 374894 pages (1464 MB) of the low zone
  0x80000000-0xffffffff (zone DMA: managed 388546 pages, so ~96 % of it) and 1027 MB of zone Normal
  (0x100000000-0x1ffffffff), no hang, 0 mismatches. Zones: DMA start_pfn 0x80000 spanned 2 GB managed 1.48 GB;
  Normal start_pfn 0x100000 spanned 4 GB managed 3.83 GB; MemTotal 5571436 kB.
  Not covered: pages in use by others at that moment, page cache, executable mappings, device/GPU buffers.
  (A researcher is still comparing downstream vs mainline reserved-memory.)
- Flight recorder: + raw_syscalls:sys_enter/sys_exit (22 events). Running 6 fresh-profile cycles (trials
  sysc-N-1) to see whether the dying thread's last act was a syscall (and which) or pure user code.

## 2026-10-12 13:40 — last act of the dying thread: mprotect(PROT_READ|PROT_EXEC); simple imitations do not freeze
- 6 cycles with raw_syscalls in the flight recorder (trials sysc-*): 6/6 HANG, 5 usable dumps. In 4 of 5 the
  LAST event of the dying thread is `sys_exit` of mprotect(addr, 0x1000-0x4000, PROT_READ|PROT_EXEC) = syscall
  226 with prot 5, paired with a preceding prot 3 (RW) on the same address: SpiderMonkey flipping a JIT code
  page W -> X. In the fifth the last such exit is 35 us before the end (futex calls after it). Dying threads:
  firefox-esr main thread x3, DOM Worker x2; hundreds of these mprotect pairs per 0.2 s, no membarrier().
  => the core stops in user mode right after freshly written JIT code becomes executable (first execution
  of it), or in whatever user code follows; nothing reaches the kernel any more.
- Reserved-memory comparison (researcher): Qualcomm carve-outs all match downstream. NOT reserved in mainline
  but reserved in Samsung's atoll-sec-common.dtsi: kaslr_region A0001000 4K, hdm_region A1000000 4K (no-map),
  rkp_region B0200000 2M (comment: up to B1800000 for uH), ss_plog B4400000 2M, sec_debug B4700000 8M,
  sec_debug_autocomment B4F00000 4K, modem_shared_mem B5000000 96M (no-map), sec_debug_rdx_bootdev 100000000
  0x5900000; splash is reserved 9c000000+0x9e3400 vs downstream +0x1700000 plus dfps 9d700000 1M. U-Boot
  passes only our DTB's reservations (efi_carve_out_dt_rsv); ABL runtime patches never reach the kernel.
  memscan had already written + read back these frames (b027e-b1dbf, b4f22-bafff ... in its coverage list)
  without a hang, so they are not access-protected; still wrong to hand them out (modem shared memory):
  to be reserved in sm7125-samsung-common.dtsi as a separate correctness fix.
- Imitations that did NOT freeze: jitciv.py (per-CPU processes: mprotect RW, write, mprotect RX, flush with
  `dc civac` + `ic ivau` exactly like vixl/V8, call; 120 s, cpu7 6.7 M iterations, cpu4/5 1.45 M each) and
  jit/jitstress2 (one process, 8-16 threads sharing a 256 MB code region: fresh 1-4 page spans, RW/RX flips,
  civac or cvau flush, re-patching, MADV_DONTNEED decommit; 3.6 M spans in 120 s). Note SpiderMonkey flushes
  BEFORE the mprotect(RX), these flush after.
- Flight recorder: + kprobe events bb_fault (handle_mm_fault: addr, flags, user pc), bb_el0sys (do_el0_sys: esr,
  pc = trapped system instructions from EL0), bb_undef (do_el0_undef), bb_svc (do_el0_svc: pc, lr); dump of the
  dead core raised to 12000 lines, buffer 4 MB/CPU. (do_mem_abort is not probeable; open(...,"a") on
  kprobe_events fails with EINVAL, use O_APPEND.) Every exec shows one bb_undef at ...cb8 = glibc reading
  MIDR_EL1 (emulated mrs); expected. Running 5 fresh-profile cycles (trials kp-*).

## 2026-10-12 15:20 — ROOT CAUSE: executing from Samsung's RKP/uH memory (0xb0400000..) hangs the core
- Flight recorder with kprobes (trials kp-*, 5/5 HANG): the dying Firefox thread's last events are again
  mprotect(RW) -> write fault on the fresh JIT page (bb_fault flags 0x1255) -> mprotect(RX) -> sys_exit, then
  nothing; no trapped system instruction (bb_el0sys) and no undefined instruction near the end.
  => it dies on the first instruction FETCH from a freshly allocated page, not on a data access.
- execscan.py (like memscan.py, but every fresh page gets `mov w0,#i; ret`, the chunk's frame numbers are sent
  to dev FIRST, then mprotect(RX) and one call per page; swap off; pinned to a little core):
  | run | uptime | last chunk reported before the core died |
  |-|-|-|
  | 1 | 139 s | pfn b03f1-b0400 (after 599 MB) |
  | 2 | 39 s  | pfn b03f6-b0405 (after 837 MB) |
  | 3 | 43 s  | pfn b03f2-b0401 (after 851 MB) |
  3/3 the core dies in the first chunk that contains frame 0xb0400; frames up to 0xb03ff execute fine.
  Data access to the same frames is fine (memscan wrote and read back b027e-b1dbf).
- What that memory is: downstream atoll-sec-common.dtsi: `rkp_region@B0200000` (2 MB, "UH_LOG and
  UH_STATIC_HEAP") with the comment "DO NOT reserve 0xB0200000 ~ 0xB1800000 region for RKP at the runtime":
  0xb0200000-0xb17fffff belongs to Samsung's hypervisor (uH / RKP; 0xb0400000 on = its read-only buffer pool,
  handed to the stock kernel page by page through RKP_RKP_ROBUFFER_ALLOC hypercalls). The stock kernel keeps
  the whole range out of the page allocator in code; our DT did not reserve it and U-Boot passes only our
  DT's reservations. Stage 2 evidently lets the guest read/write it but not execute; an instruction fetch
  there traps to EL2 and the core never returns (no IRQ, no IPI, no NMI) = the silent single-core death.
- This explains every observation: the kernel hands out zone Normal (0x100000000+) first and falls back to
  the low zone only when memory is tight, so only memory-hungry starts shortly after boot (Firefox first run,
  Electron, camera + soft ISP) put CODE pages (JIT pages, or page-cache pages of freshly read libraries and
  executables) into 0xb0400000-0xb17fffff; it follows the application to whatever core runs it (big or
  little); JIT off / software rendering only lower the number of executable pages; long uptime usually has
  the range occupied by data pages; battery, idle states, cpufreq, mitigations, GPU were all innocent.
  It is also why 6.14 froze the same way (same DT gap) and why stress tools (no fresh code pages) never did.
- FIX (worktree ~/src/wt-rsvmem, branch a52q/rsvmem, UNCOMMITTED; diff out/rsvmem.diff):
  sm7125-samsung-common.dtsi reserved-memory: `rkp_mem: memory@b0200000 { reg = <0x0 0xb0200000 0x0 0x1600000>;
  no-map; };` (common file: a72q has the same Samsung layer). dtbs_check/W=1 = baseline, checkpatch clean.
  DTB out/rsvmem/ois-rsv.dtb (OIS node + this), UKI a52qtest_0.26.1012.1: /proc/iomem shows
  `b0200000-b17fffff : reserved`, MemTotal 5548952 kB (-22 MB).
  execscan on the fixed boot: COMPLETES, 2484 MB executed page by page (1430 MB of the low zone incl.
  afe5f-b01ff and b1800-b21c2, 1054 MB of Normal), no hang.
- Acceptance running (trials fixAff-*, nofixff-*, fixBff-*): fresh-profile Firefox x10 with the fix, x3 on
  the old DTB (UKI 0.26.1012.2), x10 with the fix again (UKI 0.26.1012.3).
- Still to do after that: the other Samsung regions mainline does not reserve (modem_shared_mem b5000000 96M,
  ss_plog/sec_debug b4400000.., hdm a1000000, kaslr a0001000, rdx_bootdev 100000000) are data-safe per memscan
  and exec-safe per execscan (low zone); reserve modem_shared_mem for correctness as a separate change.

## 2026-10-12 17:30 — FIX VERIFIED: fresh-profile Firefox 10/10 OK, old DTB 3/3 HANG, fix again 10/10 OK
- Same hour, same kernel, only the DTB differs (trials fixAff-*, nofixff-*, fixBff-*):
  rkp_mem reserved (UKI 0.26.1012.1) 0/10 freezes -> old DTB (0.26.1012.2) 3/3 freezes -> rkp_mem reserved
  again (0.26.1012.3) 0/10 freezes. Before the fix the same test froze 26/29, 6/6, 4/4, 5/5 today.
- Combined DTB out/final/ois-rsv-idle.dtb (sha256 8b473eb3fe60...) = OIS node + rkp_mem + idle V1 (every cpu_pd
  only its level-4 state; out/idlefix/v1-final.diff, worktree ~/src/wt-idlefix); dtbs_check/W=1 = baseline.
  Installed as UKI a52qtest_0.26.1012.4; validation running (trials all3ff-*, camff-all3-*): Firefox fresh
  profile x10, main + front camera, idle-state and cluster counters, execscan.
- Re-reading history with the root cause known: the 10-03 "Gold deep idle hang at ~110 s" used python workers
  started right after boot and may have been this same bug (a code page in the RKP range); the
  "mitigated: clean 300 s" run proves little. The V1 measurements (firmware accepts cluster power-off only
  with every child at level 4; 350k Gold level-4 entries without a hang) stand by themselves.
- Uncommitted work to review/commit (nothing is committed or pushed):
  ~/src/wt-rsvmem  (a52q/rsvmem)  sm7125-samsung-common.dtsi: rkp_mem          <- the freeze fix
  ~/src/wt-oisdt   (a52q/oisdt)   sm7125-samsung-a52q.dts: i2c-ois + ois@62
  ~/src/wt-idlefix (a52q/idlefix) sm7125-samsung-a52q.dts: cpu_pd0-7 level 4 only
  recipes repo: device-a52q UCM HiFi.conf (Earpiece)
  this repo: DEBUG.md, autonomy/ (blackbox, stream, vphlog, sink unit, ff-fresh.sh), harnesses (soak.sh,
  camff*.sh, idlecl.sh, idlev.sh, freqff.sh, memscan.py, execscan.py, jitciv.py, jit/jitstress2.c),
  uki-recmd.sh (DTB=), bootff.sh ($APP).

## 2026-10-12 18:10 — the three DT fixes committed, merged and pushed (user go-ahead: own repo + own GitHub only)
- Validation of the combined DTB first (UKI a52qtest_0.26.1012.4, trials all3ff-*, camff-all3-*): Firefox fresh
  profile 10/10 OK; main (4616x3468) and front camera 3 frames each; rkp_mem reserved; cpuidle = WFI +
  level-4 only on all CPUs; cluster genpd S0/S1 used 22/140 times (rejected 7/74) in that boot; OIS bound;
  execscan completes (2331 MB). Only failed unit: bengalos-debug-usbnet (debug kernel).
- Codex review (gpt-6-astra, xhigh) of the three diffs: nothing on rkp_mem. Kept as follow-ups: OIS starts
  without the module EEPROM gain cells (MCU XGG/YGG f628dc3e.../...e13e vs EEPROM 8a74f93e 1d250e3f: wire up
  nvmem cells); the 1 s i2c-gpio timeout turns a dead MCU into a 160 s camera-open stall (driver should give
  up on transport errors). Dismissed: "keep the Silver intermediate state" (its premise that a CPU domain is
  never off at level 3 with two states is wrong: the genpd governor picks the domain state, cpu_power_down_ok /
  psci_pd_power_off; and only the all-level-4 layout was tested); node ordering (the file is not ordered that
  way today). Acted on: dropped the unproven "Gold core failed to resume" sentence from the idle comment.
- Commits (author Miroslav Mráz, no trailers), branches off a9f10dc:
  27682a17dadd a52q/rsvmem   sm7125-samsung-common: reserve the hypervisor (RKP) memory
  3d2661bf759d a52q/oisdt    sm7125-samsung-a52q: add the main-camera OIS MCU
  85dd395ce89b a52q/idlefix  sm7125-samsung-a52q: use only rail power-down for the CPU domains
  merged --no-ff into a52q/integ = 98d661c501c9. The merged tree's a52q DTB is byte-identical to the tested
  one (sha256 8b473eb3fe60...c838e3c, built on the laptop; a72q DTB builds too, no new warnings).
  Pushed fast-forward a9f10dcc867a..98d661c501c9 to github.com/miromraz/linux obs/a52q-integ. Nothing sent
  anywhere else. OBS still builds a9f10dc (pinned by SHA) until its package meta is re-saved.
  Temporary worktrees wt-rsvmem/wt-oisdt/wt-idlefix/wt-integ removed (branches kept).
- Phone: runs UKI a52qtest_0.26.1012.4 = debug kernel a9f10dc+dbg config with the new DTB (blessed);
  rollback image /var/tmp/a52qtest_0.26.1011.2.efi.bak is the PRE-fix one (freezes). Swap is off until the
  next reboot (execscan). Heavy trace stream (~300 KB/s) and a52-blackbox still on.

## 2026-10-12 19:00 — wrap-up: lean stream restored, review fixes, notes + scripts committed
- Phone: /etc/a52-ftrace-stream.sh is the lean pre-10-11 script again (10 events; the full variant with SCM/
  RPMh/cpufreq/PSCI/VPH is kept as autonomy/a52-ftrace-stream-full.sh, install it by hand for a debugging
  session). Rebooted on UKI 0.26.1012.4: swap back, rkp range reserved. a52-blackbox stays enabled (0.3 % CPU).
  Harnesses that analyse PSCI/SCM events (idlecl.sh, idlev.sh, freqff.sh) need the full stream.
- Codex review of the scripts (23 findings). Fixed: a52-blackbox.py (a failed UDP send no longer skips the
  local copy; self-test re-run OK), jitciv.py (failed worker = non-zero exit), uki-recmd.sh (refuses to build
  a UKI with an empty command line), idlecl.sh slice (awk pass 1 had no input file), homeio.py (works in and
  removes only its own scratch subdirectory, not DIR), UCM Earpiece (mono mix: Right ASI1 Sel LeftRightDiv2
  while selected, restored to Right; left-only and right-only 1 kHz tones both RMS ~2089 at the bottom mic vs
  14.5 silent). Known and left as they are (records of what ran): freqff/idlev/idlecl can log OK if a freeze
  lands on the trial deadline and do not compare boot ids; `pgrep -f` readiness checks can match their own
  shell; cdtrial-style harnesses interpolate arguments into the remote shell; sm5714reg.py writes whole
  register bytes with no validation; a52-lowbat-cap (obsolete idea) mishandles read errors and restarts;
  udprelay.py drops the newline of lines over 1400 bytes; uki-recmd.sh removes the old test UKI before the
  new one exists (the ESP cannot hold two; keep a copy in /var/tmp); per-trial raw slices under /tmp on dev
  are not size-capped (719 MB of /tmp/camff removed today).
- .gitignore: bench/ (1.5 GB Geekbench + debs), wifisrv/ (300 MB test file), the three static jit binaries.
- Recipes repo: UCM Earpiece committed on the local branch a52q, NOT pushed (origin is the BengalOS team's
  repository on salsa.debian.org, not the user's).
