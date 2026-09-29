# Camera kernel integration + boot test (2026-09-27)

## Built
- Tree /home/realni/src/linux-sm7125 (uncommitted WIP, not committed). Incremental build in `kbuild-trixie`
  (GCC 14.2.0-19), build #8. 0 compiler/dtc warnings.
- a52q_defconfig already had `CONFIG_EEPROM_AT24=m` and `CONFIG_VIDEO_AK7375=m`. The build `.config` is
  a52q_defconfig plus the BengalOS fragment (DM_VERITY, EROFS). A plain `make a52q_defconfig` would drop
  that fragment, so only these two options were set, with `scripts/config` + olddefconfig.
  Diff against the old .config: only these two lines.
- Rebuilt: vmlinuz.efi (vmlinux relinked; includes the WIP built-in sm5714-charger OTG-first change),
  sm7125-samsung-a52q.dtb, modules gc5035, imx616, s5k3l6xx, s5kgw1p, qcom-camss (deployed with
  --strip-debug, like the previous one), ak7375 (new), at24 (new). The other modules in the sysext
  `updates/` were byte-identical to the tree builds and were left alone.
- DT checks: `make W=1` of the dtb gives one warning only, the old one in common.dtsi (`/soc@0/i2c-18` simple_bus_reg).
  `dt-validate` (dt-mk-schema from the tree bindings): no findings on i2c@880000, camera-lens@c (ak7374
  is in the updated binding), eeprom@51, video-mux, or the sensor nodes. The sensor compatibles are still
  undocumented (known). Other findings are older and not camera related (cci compatible, pinctrl, etc).

## Deployed
- Modules copied to /var/lib/extensions/a52qdev/usr/lib/modules/6.14.7-sm7125/updates. depmod ran in
  /var/lib/a52qdev-mods, the same way as sysext-dev.sh, and modules.* were copied into the sysext.
  The profile was not re-copied. No live `systemd-sysext refresh`: the reboot merges it.
- UKI: `uki-test.sh 0.26.0927.3`, giving /boot/EFI/Linux/a52qtest_0.26.0927.3+1.efi. Rebooted while
  holding /run/a52cam.lock, then touched /run/dev-alive at once (up 0 min). Booted entry: a52qtest_0.26.0927.3.efi.
  It is blessed (the +1 counter is gone). `uname -v` = `#8 ... 10:02:17 UTC`.

## Verified on the phone (boot 10:08 UTC)
| check | result |
|-|-|
| sensors probe | s5kgw1p 20-002d, s5k3l6xx 21-002d, imx616 22-001a, gc5035 22-0037, gc5035_macro 22-003f subdevs present. Chip-id lines are logged for s5kgw1p, s5k3l6xx and imx616. gc5035 prints none, but both gc5035 instances stream |
| media devices | exactly one /dev/media0. 6 sensor-side data links, no duplicates (also after 6 libcamera sessions) |
| macro name | entity `gc5035_macro 22-003f`. libcamera looks for `gc5035_macro.yaml` |
| lens | entity `ak7375 9-000c` (func 0x20003). Ancillary link `s5kgw1p 20-002d -> ak7375 9-000c` flags 0x20000003 |
| focus_absolute | driver range 0..1023 step 1, default 0. Set 301/759/530/0/1023: G_CTRL matches, and an AK7374 read over i2c-9 (reg0..2) gives the same position, CONT=0x00 (active). -1/1024 clamp to 0/1023 |
| front EEPROM | `at24 9-0051: 8192 byte 24c64 EEPROM, read-only`. Full 8 KiB read, twice with the same md5 (3e1f804d...). Contains `C32ESNGF1NM`, `V701V003A52_QCF1`, LSC tables. It reads even with imx616 runtime-suspended, because at24 enables vcc-supply (L3) itself |
| libcamera (system 0.7.2, `cam` from /var/tmp/camwork/depth/bin) | `cam -l` lists 5 cameras (4 back, 1 front). 20-frame viewfinder stream OK on all 5, then UW again after macro (mux switch) |
| RAW colour bars (camcap.py + UW mux diff, csid0/vfe0 RDI) | main 4624x3468, UW 4000x3000, front 3264x2448: 0 empty rows, every row == row-2 (3466/3466, 2998/2998, 2446/2446), ~28.5-29 fps. depth + macro 2592x1944: 0 empty rows, GalaxyCore tiled pattern clean by eye (PNG), depth == macro. The test pattern was reset to 0 after each capture |

Scripts/logs on the phone: /var/tmp/camwork/integ/ (topo.py, focus.py, tpcap.sh, ana.py, tp-*.log,
front-eeprom.bin).

## Gaps / notes
- Focus range: the driver exposes the full DAC range 0..1023. The module's calibrated range is 301
  (infinity) .. 759 (macro), from the main EEPROM. Clamping to that range, or passing it to userspace,
  is not done. libcamera 0.7.2 simple pipeline shows no CameraLens/AF use, so the lens can only be set
  with V4L2 for now.
- libcamera still says "Unable to get rectangle" for s5kgw1p. The main driver has no get_selection.
  PixelArraySize falls back to the default, which is harmless.
- No per-sensor tuning yaml or sensor helper is installed yet: uncalibrated.yaml is used. That is the
  libcamera agent's part.
- `systemctl is-system-running` = degraded only because qcom-modem-setup.service fails. It failed in
  the previous boot too, so this kernel did not cause it.
- The main-sensor focus was checked through registers only. No sharpness sweep was done, because the
  phone lies face-up.
