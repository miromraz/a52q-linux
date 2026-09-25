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
