# a52q libcamera 0.7.2 integration (2026-09-27)

One patched libcamera 0.7.2 (Debian 0.7.2-1 source) for all five a52q cameras, soft ISP
(`simple` pipeline, GPU debayer). Nothing is installed system-wide; the orchestrator installs.

## Where things are

| what | where |
|-|-|
| patch series (git format-patch, on Debian 0.7.2-1 source with its quilt patches applied, i.e. `quilt push -a` state) | `cameras/libcamera/patches/0001..0016` |
| tuning files (also shipped by patch 0013) | `cameras/libcamera/ipa/simple/*.yaml` |
| Lsc block helpers | `cameras/libcamera/lscmesh.py` (reads the per-camera mesh dumps), `gen-s5kgw1p-lsc.py` (main mesh from the Chromatix blob, uses `uw/chromatix.py`) |
| Debian build script (container) | `cameras/libcamera/deb-build.sh` |
| kernel follow-up (not applied) | `cameras/libcamera/kernel-s5kgw1p-get-selection.patch` |
| evidence PNGs + stats | `cameras/libcamera/evidence/` (full PPMs + logs on the phone in `/var/tmp/libcamera-a52q/evidence/`) |
| installable output | phone `/var/tmp/libcamera-a52q/` (debs + `root/` install tree, see below) |
| dev build used for the tests | phone `/home/a52cam-uw/integ/bld` = 0001-0012 (+ `icam.sh`, `shot.sh`, `tp.sh`, `afmain.sh`, `lscgrey.sh`); phone `/home/a52cam-uw/fix/bld` = 0001-0016 (+ `fcam.sh`, `ftp.sh`; `rcam.sh` runs cam from the install tree) |
| test-pattern geometry check (scale x/y, crop centre) | `cameras/libcamera/geom.py IMG.ppm MODE_WxMODE_H` |

## Patch series

| # | patch | origin / notes |
|-|-|-|
| 0001 | s5k3l6xx helper + properties | uw, unchanged |
| 0002 | s5kgw1p helper + properties | main, rebased by hand onto 0001 |
| 0003 | imx616 helper + properties | front |
| 0004 | gc5035 helper + properties | depth |
| 0005 | gc5035_macro helper + properties | macro |
| 0006 | soft-ISP LSC (GPU debayer) | uw, unchanged |
| 0007 | soft IPA: refresh `IPACameraSensorInfo` at configure | new. Upstream 0.7.2 only passes it at init, so line duration (ExposureTime metadata), frame length and crop were those of the mode at pipeline creation |
| 0008 | LSC follows the mode's analogue crop | new. Mesh nodes span the full field of view; for cropping modes the mesh is bilinearly resampled over the crop |
| 0009 | AGC: log-space loop + VBLANK extension (to 15 fps) | Pixel 4a `libcamera-agc-vblank-and-dpc.patch`, AGC part. Changed: VBLANK floor = mode default (the a52q 30 fps modes allow 60-120 fps; with the control minimum a bright scene raised the frame rate), VBLANK written before exposure (priority / direct path). DPC (CPU debayer only) and the highlight shoulder not carried |
| 0010 | simple pipeline: reset VBLANK to default before configuring the soft IPA | new; drivers keep the extended VBLANK across mode changes |
| 0011 | AWB keeps gains across reconfigure | Pixel 4a `libcamera-awb-persist-gains.patch`, unchanged |
| 0012 | contrast-detect AF | Pixel 4a `libcamera-softisp-af.patch`. Changed: dropped its Brightness/AeEnable/ExposureValue controls (standard ids with non-standard ranges); LensPosition 0..100 maps to `[focus_min, focus_max]` (offset bug fixed) with optional tuning `lensRange`; inert without a lens; lens only driven when Af computed a position; lens moved also when a frame-start event exists |
| 0013 | a52q tuning files installed to `/usr/share/libcamera/ipa/simple/` | |
| 0014 | simple pipeline: prefer sensor modes matching the stream aspect ratio | new. Among the modes large enough, keep those within ~5% of the best aspect match, then the smallest as before. Main 1280x960 now from 4624x3468 (was 2000x1128) |
| 0015 | GPU debayer: centre the crop | new. The projection anchored the scaled image at the origin, so a mismatching aspect showed one edge of the field of view. Now centre-to-centre (CPU debayer already centred) |
| 0016 | GPU debayer: pad output buffers to a 4-line height | new. freedreno (A618, Mesa 26.1) needs a dmabuf of stride x align(height, 4) to import a linear render target |

Builds warning-free with `-Dwerror=true` (dev build, gcc forky, aarch64).

## Tuning files

All have BlackLevel 64@10b, Awb, **Lsc** (17x13, `fadeGain: [8, 16]`), Ccm, Adjust, Agc. Lsc sources:
- s5k3l6xx (UW): uw agent's file, unchanged.
- s5kgw1p (main): lsc34_ife lux 1..460 table, decoded here with the UW decoder (`gen-s5kgw1p-lsc.py`).
  Trustworthy by structure: centre 1.007, corners 4.6-4.8 (R/G/B 4.8/4.7/4.4), smooth, left/right
  symmetric, same layout as the UW mesh the UW agent verified. Not checked on a flat field (no light).
  Plus `Af: lensRange: [280, 780]` (EEPROM inf 301 / macro 759, ~20 codes margin).
- imx616 (front), gc5035 (depth), gc5035_macro: the agents' mesh dumps (Gr/Gb averaged).
- The vendor turns LSC off in low light for all five sensors (lux index > ~500, table all 1.0); the
  8x..16x analogue-gain fade approximates that. Consequence: in the dark scenes below LSC is fully faded.

Every yaml loads without error (log: "Using tuning file .../<model>.yaml", `IPASoftLsc` "Mesh window"
line per configure, no IPA errors).

## Results (dev build on the phone, `LD_LIBRARY_PATH`/`LIBCAMERA_IPA_CONFIG_PATH`, lock held)

Scene: **all cameras see darkness** (rear cameras against the desk, front camera mean 0.3/255 even at
16x/66 ms; torch 4/8 only lit a faint green blob on the UW). No real-scene colour/exposure check possible.

| camera | stream | AGC in dark | test pattern through soft ISP | notes |
|-|-|-|-|-|
| main s5kgw1p | 2000x1128 (16:9 mode) -> 1280x960, 15 fps | 32x, 66.6 ms | colour bars correct order/hue | AF: lens found, range 280-780, full sweep drives the VCM 280->778, settles 690 (=LensPosition 82); AfState Failed on first run (peak/floor 1.29), Focused on second (1.59, noise - false positive in the dark) |
| UW s5k3l6xx | 4000x3000 -> 3992x3000; 2000x1500 -> 1024x768 | 16x, 66.5 ms | bars correct | solid grey (150/1023) at Gamma 1: LSC on (fade removed) centre 6.9 / corners 30 (x4.4), LSC off flat 6.0 -> mesh applied |
| front imx616 | 1632x1224 -> 1280x960 | 16x, 66.4 ms | bars correct | mesh window 6528x4896 (full) |
| depth gc5035 | 1296x972 -> 1280x720 / 960 | 48x, 66.4 ms | GC test chart, colours correct | |
| macro gc5035_macro | 1296x972 -> 1280x960 | 48x | identical to depth (same digital pattern, same CCM at that CT, LSC faded at 48x) | loads gc5035_macro.yaml |

- VBLANK extension works: dark scenes run 15 fps with 66 ms exposure (system libcamera: 30 fps, 33 ms),
  and a bright pattern returns to 30 fps (UW), not to the 60 fps the control minimum allows.
- Crop-aware LSC exercised with the patched s5kgw1p driver (below): 16:9 mode gives
  `Mesh window (312, 608)/4000x2256 of 4624x3468: x 0.067+0.865 y 0.175+0.651`. Without that driver
  patch the main camera reports no crop and its 16:9 mode gets the full-FOV mesh (over-corrects top/bottom).
- 15/30 fps alternation in the bar captures is `cam --file` writing every frame; without file output the
  stream is steady (checked on main).
- Aspect/crop (0014-0016, fix build, main, fade-to-grey pattern: 8 bars of mode width/8, restart every
  512 sensor rows): `evidence/aspect-geom.txt`, `main-4x3-{before,after}.png`,
  `main-16x9-crop-{before,after}.png`, `main-1000x750-after.png`. All five cameras stream 1280x720 and
  1280x960 without errors on the fix build; UW/front/depth/macro only have 4:3 modes, so 0014 does not change their choice.

## Install

Debs, built natively in the phone's forky container by `deb-build.sh` (Debian 0.7.2-1 packaging,
profiles nocheck,nodoc,nopython,noqt,nosdl, `-Dsoftisp-gpu=enabled`, IPA signatures verified by the
rules): `/var/tmp/libcamera-a52q/*_0.7.2-1+a52q2_arm64.deb` (0001-0016; +a52q1 was 0001-0013) = libcamera0.7, libcamera-ipa,
gstreamer1.0-libcamera, libcamera-v4l2, libcamera-tools, libcamera-dev (dbgsym debs stay in
`/home/a52cam-uw/integ/deb/`). Install tree: `/var/tmp/libcamera-a52q/root/usr/...` = contents of the
runtime debs (all except -dev). libcamera.so links libEGL/libGLESv2 (GPU debayer present).

Verified from the install tree without installing (`LD_LIBRARY_PATH=root/usr/lib/aarch64-linux-gnu`,
`LIBCAMERA_IPA_MODULE_PATH`, `LIBCAMERA_IPA_PROXY_PATH`, `LIBCAMERA_IPA_CONFIG_PATH=root/usr/share/libcamera/ipa`):
all five cameras stream 45/45 frames, each loads its own yaml, IPA runs in-process (signature valid), lens
found on main, no errors except the s5kgw1p selection ones. The +a52q2 tree was re-checked the same way on the main camera (1000x750 from 4624x3468, 60/60 frames,
centred, x/y scale 0.2168/0.2168, a52q tuning files loaded). `cam` from libcamera-tools needs
libevent-pthreads-2.1-7, which BengalOS does not ship (the runtime libs do not need it).
Replace **together**: libcamera.so.0.7.2 + libcamera-base, `libcamera/ipa/ipa_soft_simple.so` **and its
`.sign`** (signature keyed to this build), `libexec/.../soft_ipa_proxy`, `share/libcamera/ipa/simple/*.yaml`.
Then `ldconfig`. Snapshot/pipewire pick it up after a restart of wireplumber/pipewire.

## Known issues / not done

- Fixed by 0016 (was: "debayerGPU failed" on every frame, `cam` hung): the trigger is the output
  **height**, not the width. Every height that is not a multiple of 4 failed unless the page rounding
  of the buffer happened to cover the missing lines (1000x750, 1280x750, 512x750, 1280x718 failed;
  1000x752, 1008x756, 256x750 worked). Still upstream: a failing GPU frame is never completed
  (`process()` returns without emitting the buffers), so any other GPU error still hangs the request.
- Fixed by 0014/0015 (was: main 4:3 requests served from the 2000x1128 mode). Measured with the
  s5kgw1p test patterns it was **not anamorphic** (x/y scale 0.851/0.850) but a crop anchored at the
  left/top: 1280x960 showed sensor columns 0-1504 of 2000 (output centre = sensor x 752) and lost
  the right quarter; 3840x2160 lost the bottom rows. After: 1280x960 from 4624x3468, scale
  0.2773/0.2773, centre = sensor (2311, row phase 198 of 198 expected), 30 fps as before.
  Whether Snapshot's reported "stretch" is this crop or something in its own pipeline (rotation 270
  in the preview) was not checked: no user session on the phone (only the greeter), so Snapshot
  could not be run.
- s5kgw1p has no get_selection (libcamera logs ERRORs, no crop info): `kernel-s5kgw1p-get-selection.patch`
  (compile- and device-tested, not applied; main agent owns the driver).
- LSC orientation assumes the frame is not flipped by libcamera (true for the default Rotate0 request
  with rotation 270; an app asking for Rotate90 would get H+V flips and a mirrored mesh).
- LSC applies on the GPU path only; CPU debayer ignores it. DPC not ported (CPU only).
- AF LensPosition is 0..100 (not dioptres as the libcamera control defines).
- No real-scene verification of colour, AWB, AE, LSC or AF: needs light / the phone facing a scene.

## Incident

Testing the s5kgw1p selection patch (rmmod s5kgw1p / insmod / modprobe back, under the lock) lost the
ak7375 lens devnode; rebinding ak7375 alone left a stale ancillary link and **libcamera failed to enumerate
any camera** ("Failed to find MediaObject with id 333") for a few minutes. Recovered with: unbind ak7375,
rmmod s5kgw1p, bind ak7375, modprobe s5kgw1p -> all 5 cameras + lens back (verified). The unbind logged a
`_regulator_put` WARN (ak7375 regulator refcount may be off until reboot). Lesson: reload s5kgw1p only
together with the ak7375 unbind/bind in that order.
