# sysext-dev.sh — what a full a52qdev rebuild must include

`sysext-dev.sh` overlays the `device-a52q` profile `/usr` (+ rebuilt kernel modules)
onto a running BengalOS a52q as a systemd-sysext (`/var/lib/extensions/a52qdev`,
`/usr` is dm-verity). It does **not** by itself carry two sets of dev additions that
the stock image lacks. Both were dropped by the 2026-09-27 17:55 rebuild, which is
what killed the camera stack (all 5 sensors + VCM stuck in
`/sys/kernel/debug/devices_deferred` waiting for the S2MPB03 camera-PMIC regulators;
no `cam` tool; stock libcamera only). **A future rebuild must re-add both or the
cameras break again.**

## (a) Extra kernel modules (not in the stock image's modules.order)

Four modules the stock kernel package strips but the cameras/USB-C need. Confirm with
`comm -23 <(sort -u modules.order-of-tree) <(sort -u modules-on-phone)`:

| module | tree path (`~/src/linux-sm7125`) | why |
|-|-|-|
| `s2mpb03-regulator` | `drivers/regulator/s2mpb03-regulator.ko` | camera PMIC (pmic@56); supplies ldoN for all 5 sensors + AK7374 VCM |
| `at24` | `drivers/misc/eeprom/at24.ko` | camera EEPROMs 9-0050 / 9-0051 |
| `video-mux` | `drivers/media/platform/video-mux.ko` | macro/UW CSIPHY3 mux |
| `sm5714-cc` | `drivers/usb/typec/sm5714-cc.ko` | USB Type-C role detection |

Each must have vermagic `6.14.7-sm7125 SMP preempt mod_unload aarch64` and be built by
the Debian GCC 14 kbuild (`modinfo -F vermagic`, `objdump -s -j .comment | grep GCC`).
Rebuild if unsure:
`flock /tmp/claude-1000/kbuild.lock docker exec -u 1000:1000 -w /src kbuild-trixie make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j8 modules`

The **full** `updates/` set is larger than these four (sensor drivers, qcom-camss,
i2c-qcom-cci, v4l2-cci, ak7375, the audio agent's snd-soc-* / q6asm, etc.). The
authoritative list is whatever is currently in
`/var/lib/extensions/a52qdev/usr/lib/modules/6.14.7-sm7125/updates/` on the phone
(19 files as of 2026-09-28). When rebuilding from scratch, pass **all** of them to
`sysext-dev.sh` as args, e.g. after collecting every `.ko`:

```
EXTRA=~/linux-a52q/cameras/libcamera/sysext-extra \
  ./sysext-dev.sh /path/to/each/updates/*.ko
```

`sysext-dev.sh` stages them in `/var/lib/a52qdev-mods`, runs `depmod -b`, and copies
`updates/*.ko` + `modules.*` into the sysext. **Never** drop existing `updates/` files —
the audio agent also adds modules there.

## (b) Patched libcamera 0.7.2-1+a52q3 (via EXTRA=)

The stock image ships plain libcamera 0.7.2 with no soft-ISP tuning and no `cam` tool.
The a52q build is Debian 0.7.2-1 source + the 17 patches in
`cameras/libcamera/patches/` (sensor helpers, GPU soft-ISP LSC, AGC frame-duration,
AWB persist, contrast AF, 5 tuning yamls, aspect/crop fixes, and 0017: the simple
 pipeline handler opens the capture video node only while a camera is acquired so
 camss runtime-suspends when idle -- no /dev/video* held by WirePlumber, and captures
 survive s2idle).

### Build the debs

Native on the phone is impossible now (no upstream internet from the phone, per-session
podman storage). Build in an **arm64 Debian forky container on the laptop** (qemu-static,
binfmt F-flag works in containers):

```
W=~/linux-a52q/cameras/libcamera/build-work   # holds libcamera_0.7.2-1.dsc + tarballs + patches/ + deb-build.sh
docker run --rm --platform linux/arm64 -v "$W":/w -w /w debian:forky sh /w/deb-build.sh /w
```

`deb-build.sh` expects `$W/libcamera_0.7.2-1.dsc`, the orig/debian tarballs, and
`$W/patches/*.patch` (it copies them into `debian/patches`, `quilt push -a`, forces
`-Dsoftisp-gpu=enabled`, builds `-B`). Output debs land in `$W/`.

**Keep the built debs in `cameras/libcamera/debs/`** so this can't be lost again.

### Make the EXTRA= tree

Unpack the runtime debs (everything except `-dev`/`-doc`/`python3-`) into an `usr/`
tree and point `EXTRA=` at its parent:

```
E=~/linux-a52q/cameras/libcamera/sysext-extra; rm -rf "$E"; mkdir -p "$E"
# core runtime set actually installed 2026-09-28 (soft-ISP libcamera + IPA + cam):
for d in libcamera0.7 libcamera-ipa libcamera-tools; do
  dpkg-deb -x cameras/libcamera/debs/${d}_0.7.2-1+a52q3_arm64.deb "$E"
done
# optional compat (not installed this session; add to match a full runtime):
#   dpkg-deb -x cameras/libcamera/debs/libcamera-v4l2_0.7.2-1+a52q3_arm64.deb "$E"
#   dpkg-deb -x cameras/libcamera/debs/gstreamer1.0-libcamera_0.7.2-1+a52q3_arm64.deb "$E"
# `cam` (libcamera-tools) needs libevent_pthreads, which BengalOS lacks (it has libevent core only).
# The .deb has no candidate in a bare forky image; copy the .so from the build container instead:
docker cp lcb-build:/usr/lib/aarch64-linux-gnu/libevent_pthreads-2.1.so.7.0.2 "$E/usr/lib/aarch64-linux-gnu/"
ln -sf libevent_pthreads-2.1.so.7.0.2 "$E/usr/lib/aarch64-linux-gnu/libevent_pthreads-2.1.so.7"
```

Package → files (Debian 0.7.2-1 packaging):
- `libcamera0.7` → `usr/lib/aarch64-linux-gnu/libcamera*.so.*` (libcamera.so.0.7.2 + libcamera-base)
- `libcamera-ipa` → `usr/lib/*/libcamera/ipa` (`ipa_soft_simple.so` **+ its `.sign`**),
  `usr/libexec/*/libcamera/soft_ipa_proxy`, `usr/share/libcamera/ipa/simple/*.yaml` (tuning)
- `libcamera-tools` → `usr/bin/cam`
- `libcamera-v4l2`, `gstreamer1.0-libcamera` → optional compat (match prior install)

The `.so`, the `ipa_soft_simple.so` **and its `.sign`** (signature keyed to this build),
the `soft_ipa_proxy`, and the tuning yamls must all come from the **same** build.

## Deploy without a live refresh

The final `systemd-sysext refresh` in `sysext-dev.sh` re-merges live. The camera work
this session instead deployed files only and merged them with **one reboot** (avoids the
s2idle audio-RX wedge the other agent is chasing, and a live CCI refresh). To reboot:
`flock /tmp/claude-1000/a52phone.lock ssh a52r systemctl reboot` (back on ssh in ~90-120 s).
After a reboot, `touch /run/dev-alive` immediately (the test UKI reverts otherwise).
