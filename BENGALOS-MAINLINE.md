# BengalOS a52q → mainline 7.3 by default

Date: 2026-10-01. Switches the Galaxy A52 4G (a52q, SM7125) BengalOS image from
the 6.14 downstream kernel to the mainline **v7.3-rc5** integration kernel, and
ships the userspace fixes proven on device this week. Recipes repo:
`~/pixel-a4-linux/BengalOS/recipes` (local commits only, not pushed).

Assumption stated up front: the recipe ships `hexagonrpcd` as a **prebuilt
aarch64 binary** committed under `mkosi.extra` (the same mechanism sunfish
uses — the image build does NOT build it from `hexagonrpc-fork`). So the
userspace sensor fix is "replace that committed binary", and the
`hexagonrpc-fork` source tree is left untouched (its a52q changes already live
as files in `~/linux-a52q/sensors/patches/` + its working tree).

## What changed (recipes commits)

1. **device-a52q: default to the mainline 7.3 kernel.**
   `mkosi.conf.d/mkosi.profiles/device-a52q/mkosi.conf` — the `[Content]
   Packages=` entry `bengalos-kernel-a52q` is replaced by the explicit image
   package **`linux-image-7.3.0-rc5-sm7125`**.
   - Why not the metapackage: `bengalos-kernel-a52q` lives in the *bengalos*
     repo and hard-Depends `linux-image-6.14.7-sm7125`. We may only commit in
     *recipes*, so we name the mainline image directly (bypassing the pin).
     Every other device likewise pins an exact `linux-image-<ver>` — this is
     the same pattern, just expressed in the recipe instead of the metapackage.
   - OBS source: `home:realni/linux-sm7125-mainline`, scmsync of github
     `miromraz/linux#obs/a52q-integ`, builds `linux-image-7.3.0-rc5-sm7125`.
   - **The one knob to bump**: when OBS rebuilds at a newer tag (7.3.0-rc6,
     7.3.0 final, …) the deb name changes; update this single line to match.
   - 6.14 stays available: `bengalos-kernel-a52q` / `linux-image-6.14.7-sm7125`
     is still in the repo as a fallback kernel.

2. **device-a52q: ship the a52q-patched hexagonrpcd (SSC sensor registry).**
   `.../device-a52q/mkosi.extra/usr/lib/bengalos-a52q/hexagonrpcd` — replaced
   the old sunfish-HEAD build (sha256 f3ec4e96…) with the a52q build
   (sha256 02f307c9…, from `~/linux-a52q/sensors/hexagonrpcd`), the binary
   verified on device. It carries three patches over the sunfish fork
   (`~/linux-a52q/sensors/patches/`):
   - 0001 hexagonfs virt_dir readdir + clone
   - 0002 rpcd_builder: expose registry / sns_reg_version / temp.json at the
     tree **root** (the SM7125 SEE PD resolves its registry base empty and
     opens `/../sns_reg_version` root-relative)
   - 0003 hexagonfs dup shared-fd fix (opendir("/") UAF → SIGSEGV)
   Source: `~/pixel-a4-linux/hexagonrpc-fork` (branch `sunfish-sensor-registry`,
   working tree has the three patches **plus** an `apps_mem.c` DMA-buf-request
   change; that tree is what produced the shipped binary). Rebuild:
   `meson setup build --cross-file cross-arm64.txt --buildtype=release &&
   ninja -C build hexagonrpcd/hexagonrpcd`.
   The service drop-in (`hexagonrpcd.service.d/10-a52q.conf`) and the SSC
   plumbing already point at this path — no other change needed.

3. **docs/devices/a52q.md** — default kernel noted as mainline 7.3; added a
   "Dual boot" subsection.

## Verified-already, no recipe change needed

- **UCM / audio.** Mainline card longname `samsung-SamsungGalaxyA52`; the
  conf.d symlink was added in recipes `0ee5d29`. `HiFi.conf` mixer names match
  the mainline card as tested on device (`QUIN_MI2S_RX Audio Mixer
  MultiMedia1`, the `Mic1` ADC1 path, `TX_CODEC_DMA_TX_3`). WirePlumber drop-in
  `51-a52q-no-fe-probe.conf` still valid. Both longname symlinks present.
- **Initrd / overlayfs.** The image build (mkosi 27) regenerates the UKI +
  initrd **per installed kernel**, so switching the kernel package produces a
  7.3 initrd automatically — the "stale initrd" / sysext-overlay failure in
  DEBUG was a *test-UKI* artefact (reusing a 6.14 UKI under 7.3). On mainline
  `OVERLAY_FS=y` and `QCOM_WDT=y` are built in (a52q_defconfig, OBS), so the
  initrd needs no extra 7.3 module for the sysext/overlay merge. No recipe
  change. (`modules-load.d/qcom_wdt.conf` is now a no-op on 7.3 — harmless, and
  still correct for the 6.14 fallback, so it is left in place.)
- **droid-juicer.** `samsung,a52q.toml` extracts `vendor:etc/sensors` →
  `/var/lib/droid-juicer/sensors` (gives `sensors/config/*.json` +
  `sns_reg_config`) and `persist:sensors/registry/registry` →
  `.../sensors/registry`; `tmpfiles.d/bengalos-a52q-ssc.conf` links
  `sns_reg.conf`→`sns_reg_config` and `socinfo`, and `Z … fastrpc fastrpc`
  makes the subtree writable. Correct as-is.

## Test-only, must NOT be in the image (confirm absent)

journald `SyncIntervalSec=1s` drop-in; `a52q-heartbeat.service`;
`a52q-failsafe73.service`; the `/var/lib/a52q-test` hexagonrpcd drop-in. These
live only on the phone (runtime), never in the recipe — verified none are under
`device-a52q/mkosi.extra`.

## Build the image

Disk on this laptop is at 98% (6.4 GB free) — do **not** build locally (a build
set is ~10 GB). Build on the LXC build container, as sunfish does:

```sh
cd ~/pixel-a4-linux/BengalOS/recipes
make bengalos-a52q-immutable          # → build-a52q-immutable/BengalOS_<ver>.img
```

The build host must have the `home:realni Debian_13 aarch64` apt repo (serves
`linux-image-7.3.0-rc5-sm7125`) and `binfmt_misc` mounted (arm64 maintainer
scripts). Config-only sanity check (no network, runs here):

```sh
./bengalos-builder.py build-a52q-immutable/
mkosi -C build-a52q-immutable/ --profile image-immutable,device-a52q,zram,phosh summary
```

## Flash (first time — U-Boot UMS)

Samsung ABL rejects `fastboot flash` on the repartitioned table, so write the
image over U-Boot's USB mass-storage mode into the `linux` partition (64 GiB):

```sh
# U-Boot menu → enable USB mass storage; linux partition appears as /dev/sdX
simg2img build-a52q-immutable/BengalOS_<ver>.img - \
  | sudo dd of=/dev/disk/by-partlabel/linux bs=4M
sudo eject /dev/sdX            # phone keys don't abort UMS; eject from the host
```

## OTA (no UMS, no dd) — systemd-sysupdate A/B

The immutable image carries `systemd-sysupdate` transfers
(`/usr/lib/sysupdate.d/*.transfer`): UKI `%M_@v.efi.xz` plus usr / usr-verity /
usr-verity-sig, pulled from `https://bengalos.phosh.mobi/images/roaming/%a/%W/`,
installed A/B (`InstancesMax=2`, `TriesLeft=3`), then reboot into the new
usr+UKI. To push a locally built version without UMS:

1. Publish the split artifacts for the new version (`.efi.xz`, `usr`,
   `usr-verity`, `usr-verity-sig`) at the sysupdate URL (or point the device at
   a local mirror by overriding the transfer `Source` `Path=`).
2. On the phone: `/usr/lib/systemd-sysupdate update` then `systemctl reboot`.
   The old slot stays as the automatic fallback (boot-count).

NOTE: the literal "BENGALOS OTA WITHOUT UMS" scratch notes referenced in the
task were in the tmpfs scratchpad and were lost in the laptop reboot; the above
is reconstructed from the shipped `sysupdate.d` transfers + `recipes/README.md`.
If exact self-host steps resurface, fold them in here.

## On-device verification checklist (run when the phone is back)

Scripted: `flock /tmp/claude-1000/a52phone.lock ~/linux-a52q/accept73.sh 8`.
Manual spot checks after flashing/OTA the real image (not a test UKI):

- [ ] Boots to Phosh; `systemctl --failed` empty (or only expected).
- [ ] `uname -r` = `7.3.0-rc5-sm7125`; booted the image UKI (not a test .efi).
- [ ] No bootloader-watchdog reset ~28 s in (QCOM_WDT=y + OVERLAY_FS=y ⇒ sysext
      overlay merges, wdt pet). Survives >2 min.
- [ ] Wi-Fi `wld0` associates; BT `hci0` discoverable; NFC `nfc0` poll cycle.
- [ ] Touch (stmfts input); keys; vibrator; DSI panel + backlight.
- [ ] Modem: `mmcli -L` sees it; reboot 8–10× — no `DOG detects stalled
      initialization` / lost WLFW (PD_MAPPER=y fix).
- [ ] Audio: card "Samsung Galaxy A52"; speaker plays; `Mic1` records; WCD938x
      headset.
- [ ] Sensors: `hexagonrpcd` active (not failed); `journalctl -u hexagonrpcd`
      has no `Could not open /../sns_reg_version` / SEGV; `monitor-sensor`
      prints accel X/Y/Z and light; auto-rotate upright (mount matrix).
- [ ] GPU A618: devfreq to 750 MHz; libcamera softISP (EGL) works.
- [ ] Cameras: libcamera lists main (C-PHY s5kgw1p) + front imx616 + UW
      s5k3l6xx (+ GC5035); colour-bar TEST_PATTERN per camera.
- [ ] s2idle: `rtcwake -m mem -s 10` resumes without reset.
- [ ] Dual boot: U-Boot menu offers Linux + LineageOS; Lineage boots from the
      `recovery` partition via the initwrap shim.
