# Mainline Linux bring-up for the Samsung Galaxy A52 4G (`a52q`, SM7125)

This repository is the **working lab notebook and tooling** for porting mainline
Linux and U-Boot to the Samsung Galaxy A52 4G (codename **a52q**, Qualcomm
Snapdragon 720G / **SM7125**, SoC family "atoll", close to `sc7180`). It is a
collection of session notes, reverse-engineering reports, upstream-bound kernel
patch series, device configuration extracted from the stock vendor image, and a
large set of debug/stress/acceptance scripts used on a real phone.

It is **not** a distribution and **not** a one-command installer. There is no
build system here, no released image, and no committed kernel — those live
elsewhere (see [Kernel and U-Boot source](#kernel-and-u-boot-source)). If you
land here hoping to flash a finished OS, this is not that; it is the raw
material behind the bring-up. The device-facing target is
[BengalOS](https://salsa.debian.org/BengalOS-team) (a Phosh/Debian image); the same work
also drives a postmarketOS install path.

> ⚠️ **The install scripts here are destructive and need an unlocked
> bootloader.** `repartition.sh` rewrites the GPT and `wipefs`es a partition;
> `install-pmos.sh` and `install-bengalos.sh` `dd` raw images straight over the
> phone's `cache`/`userdata`/`linux` partitions through U-Boot's USB
> mass-storage mode. You must already have unlocked the bootloader (which itself
> wipes the device) and flashed U-Boot. Mis-targeting any of these erases data.
> They are bring-up tools written for one developer's phone, not hardened
> installers — read them before running anything, and expect to recover a device
> that will not boot.

---

## Status

**As of 2026-10-12** (newest dated note: `DEBUG.md`). Unless noted, "works" means
observed on-device on the mainline **v7.3-rc5** integration kernel
(`obs/a52q-integ`) running BengalOS. The 6.14 downstream fork (`obs/sm7125`) is
kept as a fallback and is where several features were first proven. Anything the
notes do not state is listed as "not documented" rather than guessed.

### Working

|Area|Status|Source|
|-|-|-|
|Boot to Phosh userspace|✅|`DEBUG.md` 2026-10-01|
|U-Boot chainload (ABL → U-Boot → systemd-boot → kernel)|✅|`DEBUG.md` 2026-09-24|
|Display / DSI panel (s6e3fc3) + backlight|✅|`DEBUG.md`, `BENGALOS-MAINLINE.md`|
|GPU, Adreno 618|✅|`DEBUG.md` 2026-10-01|
|Touch (stmfts FTS5CU56A)|✅ *|`TOUCH-GPI-2026-10-02.md`|
|Wi-Fi (WCN3990 / ath10k)|✅|`GAP-2026-10-01.md`, `BENGALOS-MAINLINE.md`|
|Bluetooth (WCN3988)|✅|`GAP-2026-10-01.md`|
|NFC (s3fwrn5 / S3NRN4V), incl. RF poll|✅|`DEBUG.md` 2026-09-30|
|Audio: speaker, mic, earpiece (WCD938x + tas2562)|✅|`DEBUG.md` 2026-10-11|
|Sensors: accelerometer (LSM6DSO), ambient light (STK31610)|✅|`DEBUG.md` 2026-10-02, `SSC-RAILS-2026-10-02.md`|
|Cameras: main/UW/front/depth/macro via libcamera soft-ISP|✅ *|`cameras/`, `DEBUG.md` 2026-10-02|
|OIS MCU (main camera)|✅|`DEBUG.md` 2026-10-11/10-12|
|Charger + fuel gauge (sm5714)|✅|`GAP-2026-10-01.md`|
|Vibrator, volume/power keys, hall switch|✅|`GAP-2026-10-01.md`|
|USB gadget / USB networking|✅|`GAP-2026-10-01.md`|
|s2idle suspend / resume|✅|`DEBUG.md` 2026-10-01|
|Silent single-core freeze (was the main blocker)|✅ fixed|`DEBUG.md` 2026-10-12|

\* Touch: a GPI DMA TX-ring regression in mainline `gpi.c` was root-caused and a
fix carried on branch `a52q/gpi-fix`; on-device confirmation was still pending at
the time of the note. Cameras: capture works but camss is RDI-only, so debayering
is on the CPU (soft-ISP); image-quality tuning is per-sensor and partial.

The **silent freeze** was the project's long-standing blocker: a single CPU core
would die with no oops. It was root-caused (`DEBUG.md` 2026-10-12) to instruction
fetches landing in Samsung's RKP/hypervisor memory region (`0xb0400000…`), which
mainline's device tree did not reserve, and fixed by reserving that range in
`sm7125-samsung-common.dtsi`.

### Partial / not working / not documented

|Area|Status|Source|
|-|-|-|
|Cellular data / calls / SMS|❌ not documented working — modem boots and is detected (`mmcli`), DOG-stall boot race fixed, but the test unit has no SIM and the data path is untested|`GAP-2026-10-01.md`, `MODEM-STALL-2026-10-01.md`, `MODEM-STALL-2026-10-02.md`|
|Magnetometer / compass|⚠️ root-caused, registry-fixable, unverified on device|`DEBUG.md` 2026-10-03|
|Gyroscope|⚠️ readable; userspace limitation|`DEBUG.md` 2026-10-03|
|Proximity|❌ no SSC proximity sensor (Samsung uses the touchscreen)|`sensors/README.md`|
|USB-C OTG host / role switch|⚠️ CC attach-detect only; host untested; `TYPEC_MUX_SM5714` unset|`GAP-2026-10-01.md`|
|Camera full resolution (64 MP main, 32 MP front)|❌ needs proprietary remosaic|`cameras/main/REPORT.md`, `cameras/front/REPORT.md`|
|Fingerprint (under-display)|❌ no mainline path|`GAP-2026-10-01.md`|
|Thermal zones / cpufreq max|⚠️ unverified|`GAP-2026-10-01.md`|
|Deep sleep / battery life|not documented (s2idle works; low-power states not characterized)|—|
|Headphone-jack detection, video encode/decode|not documented for a52q|—|

---

## Kernel and U-Boot source

The kernel is **not** committed here. It lives at
**[github.com/miromraz/linux](https://github.com/miromraz/linux)**:

- **`obs/a52q-integ`** — the integration branch to build. This is
  v7.3-rc5 plus the base DT series and all of this project's ports and fixes;
  it is what OBS packages as `linux-image-7.3.0-rc5-sm7125` and what the on-device
  results above were observed on. Its tip when these notes were written is
  **`98d661c501c9`** (`DEBUG.md` 2026-10-12, `BENGALOS-MAINLINE.md`).
- **`obs/a52q-mainline`** — the cleaner base/`a52q_defconfig` branch the integ
  work rebases on (`GAP-2026-10-01.md`, defconfig `51966e7`).

Build it with `ARCH=arm64` and an aarch64 cross toolchain. `upstream/SERIES.md`
and `upstream/STATUS.md` track the same commits re-cut as clean,
upstream-submittable series (`up/*` branches) — none have been sent yet.

**U-Boot** is not vendored here either. `repack.sh` builds it from a local
(git-ignored) `u-boot/` checkout of upstream U-Boot with
`qcom_a52q_defconfig qcom-phone.config a52q.config` and packages it as an
Odin-flashable AP tar; boot-image header parameters come from the pmaports
`device-samsung-a52q` deviceinfo. The U-Boot bring-up and header gotchas are in
`DEBUG.md` (see "RESOLVED … U-Boot runs on a52q"); an upstream U-Boot patch
series branch `a52q-upstream` is mentioned there but the tree itself is not here.

---

## Repository map

Top-level directories:

- **`cameras/`** — per-sensor reverse-engineering and tuning (`main`, `uw`,
  `front`, `depth`, `macro`, `ois`), the a52q libcamera build and soft-ISP tuning
  files, and `INTEGRATION-KERNEL.md` / `INTEGRATION-LIBCAMERA.md`.
- **`upstream/`** — upstream-bound kernel patch series, one dir per subsystem,
  plus `SERIES.md` (plan + maintainers) and `STATUS.md` (regeneration state).
- **`sensors/`** — SSC/ADSP sensor registry and config extracted from the stock
  LineageOS vendor image, plus a patched `hexagonrpcd` binary and its patches.
  Start with `sensors/README.md`.
- **`autonomy/`** — on-device debug/monitoring systemd units and scripts
  (netconsole, ftrace streaming, the `a52-blackbox` flight recorder, Wi-Fi watch,
  auto-reboot, low-battery cap) used during the freeze hunt.
- **`patches/`** — snapshot WIP kernel/camera `.patch` files.
- **`tools/`** — the `cam-probe` out-of-tree kernel module and camera-capture /
  sensor-module helper scripts.
- **`lineage/`** — LineageOS dual-boot support: the `initwrap` shim that boots
  LineageOS from the `recovery` partition, `boot.args`, and a prebuilt
  `lineage-in-recovery.img`.
- **`jit/`** — small JIT/seccomp stress C programs written to reproduce the
  silent freeze.
- **`fw/`** — scripts (`install-fw.sh`, `pil-squash.py`) that pull proprietary
  firmware off *your own* phone's Android partitions; no blobs are committed.

First files to read: **`DEBUG.md`** (the full chronological bring-up log),
**`BENGALOS-MAINLINE.md`** (how the BengalOS image switches to the mainline
kernel and is flashed), and **`GAP-2026-10-01.md`** (the 6.14-vs-mainline
per-subsystem gap analysis). The dated notes `MODEM-STALL-2026-10-01.md`,
`MODEM-STALL-2026-10-02.md`, `SSC-RAILS-2026-10-02.md` and `TOUCH-GPI-2026-10-02.md`
are deep dives on specific problems.

The ~90 top-level scripts fall into groups: **install** (`install-bengalos.sh`,
`install-pmos.sh`, `repartition.sh`, `repack.sh`); **test UKI / dev overlay**
(`uki-test.sh`, `uki-recmd.sh`, `sysext-dev.sh`); **acceptance** (`accept73.sh`);
host-side phone presence (`a52-nicwatch.sh`, `phone-arrive.sh`); and a large body
of freeze/stress/forensics harnesses (`soak.sh`, `camff*.sh`, `freqff.sh`,
`idlev.sh`, `idlecl.sh`, `memscan.py`, `execscan.py`, `burst.py`, …). **Do not run
any of them blind** — most talk to a live phone and several flash or reboot it.

---

## Getting started

There is no reproducible one-shot path in this repo; the install is multi-stage
and depends on external inputs (the kernel tree, a built image, firmware off your
own phone). The sequence the scripts and notes describe is:

1. **Unlock the bootloader** on the A52 4G (wipes the device).
2. **Build and flash U-Boot.** `repack.sh` builds U-Boot (needs an external
   `u-boot/` checkout) and packages an Odin AP tar; flash it in Download Mode
   (the notes used `odin4`). U-Boot's "Enable USB mass storage" mode is what the
   install scripts write through. See `DEBUG.md`.
3. **Build the kernel** from `obs/a52q-integ` and an OS image (BengalOS, per
   `BENGALOS-MAINLINE.md`). These artifacts are not in this repo.
4. **Partition and install.** For dual-boot with LineageOS, `repartition.sh`
   splits `userdata` into a `linux` partition plus a smaller `userdata`. Then
   `install-bengalos.sh` (BengalOS → `linux`) or `install-pmos.sh` (postmarketOS
   → `cache` + `userdata`) `dd`s the image in over U-Boot UMS.
5. **Install proprietary firmware** off your own phone with `fw/install-fw.sh`.
6. **Verify** with `accept73.sh` (read-only on-device checks plus reboot
   regression) and the manual checklist at the end of `BENGALOS-MAINLINE.md`.

What is missing for a stranger to reproduce this end to end: the OS image build
recipes (they live in a separate, unpublished `recipes` repo referenced by
`BENGALOS-MAINLINE.md`), a prebuilt kernel/image, and the vendor firmware (by
design — it must come off your own device). Treat the notes as the authority and
read each script before running it.

---

## License

The scripts, tools and notes written for this project are licensed under the GNU
General Public License, version 3 or (at your option) any later version. See
[LICENSE](LICENSE).

That does not cover files that come from, or are patches against, other projects.
Those stay under their upstream licenses:

- Linux kernel patches in `upstream/`, `patches/` and
  `cameras/libcamera/kernel-s5kgw1p-get-selection.patch`, and the `cam-probe`
  kernel module in `tools/cam-probe/`: GPL-2.0, like the kernel.
- libcamera patches, packages and libraries under `cameras/libcamera/`.
- The `hexagonrpcd` binary and patches under `sensors/`.
- The sensor registry and configuration under `sensors/root/`, extracted from the
  phone's vendor image, and `lineage/lineage-in-recovery.img`, a LineageOS build.
