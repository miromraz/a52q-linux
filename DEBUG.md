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
