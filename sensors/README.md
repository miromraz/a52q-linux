# A52 4G (a52q, SM7125) SSC sensor registry/config

Vendor sensor configuration for the ADSP sensor PD, extracted from
LineageOS 23.2 (`lineage-23.2-20260921-nightly-a52q-signed.zip`,
`vendor.new.dat.br` -> `vendor.img` ext4 -> `/etc/sensors`). SoC codename
is **atoll** (SM7125); the files match this unit: `sns_reg_config`/light
JSON select `soc_id 443`, `hw_platform IDP`.

Sensors present: **LSM6DSO** accel (`atoll*lsm6dso*`), **STK31610** ambient
light (`atoll_qrd_stk31610_0.json`), **AK991x** compass (`atoll_qrd_ak991x_*`).
No proximity (Samsung uses the touchscreen).

## Layout (`root/` == the hexagonrpcd `-R` root `/var/lib/droid-juicer/sensors`)

hexagonrpcd rewrites the DSP's Android paths to files under `-R`
(see `man hexagonrpcd`):

| DSP requests | served from |
|-|-|
| `/vendor/etc/sensors/config` | `<R>/sensors/config` |
| `/vendor/etc/sensors/sns_reg_config` | `<R>/sensors/sns_reg.conf` |
| `/mnt/vendor/persist/sensors/registry/registry` | `<R>/sensors/registry` (writable) |
| `/sys/devices/soc0` | `<R>/socinfo` |

So on-device:

```
/var/lib/droid-juicer/sensors/
  sensors/config/*.json
  sensors/sns_reg_config
  sensors/sns_reg.conf -> sns_reg_config   (symlink; the name the DSP opens)
  sensors/hals.conf                        (vendor HAL list; harmless on Linux)
  sensors/registry/                        (EMPTY + writable; ADSP regenerates it)
  socinfo -> /usr/share/bengalos-a52q/socinfo
```

`registry/` is runtime state on the phone's `persist` partition and is **not**
in an OTA, so it ships empty. The ADSP sensor PD writes the registry here from
`config/*.json` on first run, which needs (a) the dir writable by `fastrpc` and
(b) a hexagonrpcd with the HexagonFS write path (dir reads otherwise return
`ENOSYS` -> the "Function not implemented" log lines; file opens still work).

## Ownership

Everything under `.../sensors/` must be owned by **fastrpc:fastrpc** (hexagonrpcd
runs as that user and the ADSP writes back into `registry/`). `socinfo` is a
symlink managed on-device by tmpfiles and need not be re-shipped.

## Deploy (phone over USB-net, 172.16.42.1)

Use tar (preserves the `sns_reg.conf` symlink; plain `scp -r` would deref it):

```sh
# from laptop
tar -C ~/linux-a52q/sensors/root -cf - sensors | \
  ssh root@172.16.42.1 'tar -C /var/lib/droid-juicer/sensors -xf -'

# on phone (root)
systemctl stop iio-sensor-proxy hexagonrpcd
ln -sfn /usr/share/bengalos-a52q/socinfo /var/lib/droid-juicer/sensors/socinfo  # if missing
chown -R fastrpc:fastrpc /var/lib/droid-juicer/sensors/sensors
systemctl start hexagonrpcd
systemctl start iio-sensor-proxy
```

## Verify

```sh
journalctl -u hexagonrpcd -b | grep -i sns_reg   # no "Could not open .../sns_reg_config"
monitor-sensor --accel                            # should print accel X/Y/Z updates
monitor-sensor                                    # should also list light level
```

If `monitor-sensor` still says "No sensors": confirm `sns_reg.conf` resolves
(`ls -lL .../sensors/sns_reg.conf`), the subtree is `fastrpc`-owned, and
`registry/` is writable.

## Making it permanent in BengalOS

The repo already does this at first boot via droid-juicer. In
`recipes/mkosi.conf.d/mkosi.profiles/device-a52q/mkosi.extra/usr/share/droid-juicer/configs/samsung,a52q.toml`
the `folders` block copies `vendor:etc/sensors` -> `/var/lib/droid-juicer/sensors`
(becomes `.../sensors/`) and `persist:sensors/registry/registry` ->
`.../sensors/registry`, and `.../usr/lib/tmpfiles.d/bengalos-a52q-ssc.conf`
creates the `sns_reg.conf` + `socinfo` symlinks and chowns the subtree to
`fastrpc`. **No config change is needed** — this manual drop only fills in a
unit where droid-juicer had not yet run (or where `persist` lacked the
pre-built registry). Prefer that first-boot extraction over committing Samsung
blobs into the image. Only caveat: if the ADSP cannot regenerate `registry/`,
hexagonrpcd needs the HexagonFS write-path patch (see MeowArch fork).

## Patched hexagonrpcd for a52q (registry regeneration)

The build shipped in the recipe (sunfish fork HEAD) already has the write path
and maps `sns_reg_version` at `/mnt/vendor/persist/sensors/registry/`. But the
a52q (SM7125) SEE PD resolves its registry from a base that comes out **empty**,
so it opens the version file root-relative as `/../sns_reg_version` (which
resolves to `/sns_reg_version`) and writes its registry group files root-relative
too — none of which the Android-path mappings catch. That is the source of the
`Could not open /../sns_reg_version` + `(write)` errors and the empty `registry/`.
It also `readdir()`s virtual dirs, which upstream never implemented (the
`Could not read from directory: Function not implemented` lines).

`hexagonrpcd` here is a rebuilt binary (aarch64, glibc<=2.38, same as the shipped
one — runs on trixie 2.41) with three patches in `patches/`:

- `0001-hexagonfs-virt_dir-readdir-and-clone.patch` — add `readdir` (and the
  clone op below) to virtual dirs.
- `0002-rpcd_builder-a52q-root-relative-registry.patch` — expose `registry/`,
  `sns_reg_version` and `temp.json` at the tree **root** as well, backed by the
  same writable files as the `/mnt/vendor/persist` copy.
- `0003-hexagonfs-dup-shared-fd-fix-opendir-UAF.patch` — **crash fix.** When a
  path resolved to an already-open handle (the PD `opendir()`s its empty-string
  registry base, i.e. `/`), `hexagonfs_openat()` handed back the *same* fd object;
  `closedir()` then freed it and the next use of the root fd was a use-after-free
  → `SIGSEGV` (the `status=11/SEGV` seen on-device). Now such a result is cloned
  into an independently-owned fd. Latent upstream bug that patch 0001 exposed
  (virtual dirs became enumerable, so the PD started `opendir`-ing them).

Reproduced + fixed under ASan (`opendir("/")` → readdir → close → reuse root fd,
plus root-relative `sns_reg_version`/`temp.json` create/write/read); native
`meson test` passes. temp.json is writable: the PD creates it via `fopen("w")`;
the `Could not open /temp.json: No such file` lines are harmless read/stat probes.
The first two patches are purely additive; 0003 only changes the shared-handle
case, so this binary stays safe on sunfish/sm7150. Source: `~/pixel-a4-linux/hexagonrpc-fork`
(branch `sunfish-sensor-registry`); rebuild with
`meson setup build --cross-file cross-arm64.txt --buildtype=release && ninja -C build hexagonrpcd/hexagonrpcd`.

### Deploy the patched binary for a reboot test (no image rebuild)

`registry/` is already writable + `fastrpc`-owned (tmpfiles `Z`), and the new
root entries reuse those same files, so **no extra dirs are needed**. Do NOT try
to restart at runtime: stopping the ADSP remoteproc hard-resets this phone — the
test is a full reboot.

# The unit runs with User=fastrpc, PrivateTmp=yes and ProtectSystem=strict, so
# /var/tmp and /usr are NOT usable for the test binary. Stage it under /var/lib.
```sh
# from laptop
ssh root@172.16.42.1 'mkdir -p /var/lib/a52q-test'
scp ~/linux-a52q/sensors/hexagonrpcd root@172.16.42.1:/var/lib/a52q-test/hexagonrpcd

# on phone (root): point the service's ExecStart at the test binary
chmod 0755 /var/lib/a52q-test/hexagonrpcd
mkdir -p /etc/systemd/system/hexagonrpcd.service.d
cat >/etc/systemd/system/hexagonrpcd.service.d/20-a52q-test.conf <<'EOF'
[Service]
ExecStart=
ExecStart=/var/lib/a52q-test/hexagonrpcd -f /dev/fastrpc-adsp -d adsp -s -R /var/lib/droid-juicer/sensors
EOF
# make sure the registry dir is empty + fastrpc-owned so the PD regenerates it
rm -f /var/lib/droid-juicer/sensors/sensors/registry/*
chown -R fastrpc:fastrpc /var/lib/droid-juicer/sensors/sensors
systemctl daemon-reload
reboot
```

After the reboot (~90 s to SSH):

```sh
journalctl -u hexagonrpcd -b | grep -iE 'sns_reg|directory'   # expect NO /../sns_reg_version, no ENOSYS
ls -l /var/lib/droid-juicer/sensors/sensors/registry/         # expect sns_reg_version + group files now present
monitor-sensor                                                # accel + light should appear
```

To revert: `rm /etc/systemd/system/hexagonrpcd.service.d/20-a52q-test.conf && reboot`.

### Recipe change (draft — do not commit yet)

Once verified, replace the shipped binary in place (same path the drop-in already
`ExecStart`s) and refresh the stale comment:

- `recipes/.../device-a52q/mkosi.extra/usr/lib/bengalos-a52q/hexagonrpcd`
  <- `~/linux-a52q/sensors/hexagonrpcd` (this rebuilt binary).
- `recipes/.../device-a52q/mkosi.extra/usr/lib/systemd/system/hexagonrpcd.service.d/10-a52q.conf`:
  update the `# Debian's hexagonrpcd 0.4.0 ...` comment to note the a52q
  root-relative registry + virt-dir-readdir + opendir-UAF-fix patches (patches
  live in the `hexagonrpc-fork` repo; fold them into its branch and rebuild from
  there).

No `samsung,a52q.toml` / tmpfiles change is needed — the registry dir is already
writable and `fastrpc`-owned.

## 2026-10-02: ssc_core sysfs nodes + crash triage (patch 0004)

With the **real** Samsung configs loaded, the ADSP crashes ~5 s after
hexagonrpcd attaches:
`EF:sensor_process:0x1:UTMR_CLNT_1:0xe4..e6:sns_thread_mana` → ADSP fatal →
whole-phone hard reset. `sns_thread_mana`/`UTMR_CLNT_1` is the SEE sensor
**thread-manager watchdog** ("exceeded processing time limit for library").
Empty configs → no crash because no sensor drivers load.

**Findings from this session:**

- **The `sns_*.so` are not shippable and not the cause.** `sns_bring_to_ear.so`
  and friends do **not** exist as files: I rebuilt `vendor.img` from the Lineage
  OTA (`vendor.new.dat.br` → ext4) and the only SSC objects present are AP-side
  ARM libs (`libssc.so`, `sensors.ssc.so`, `libsns_*_stub.so`, `*_skel.so`) — no
  DSP `sns_*.so` plugins anywhere. The known-working sunfish/sm7150 BengalOS
  ships none either (the `sns_*` strings in configs are algorithm *owner* names).
  These plugins are statically linked into the ADSP sensor firmware; the
  `Could not open sns_bring_to_ear.so` line is a benign dynamic-load
  probe-and-fallback that also appears on working devices. So the hexagonrpcd
  `-R` adsp lib dir (`root/dsp/adsp/`) is intentionally **not** populated.

- **ssc_core nodes (patch 0004).** Just before the crash the DSP polls
  `/sys/class/sensors/ssc_core/ssc_hw_rev` then `ssc_mode` ~10× each — Samsung's
  downstream `ssc_core` driver nodes, absent on mainline. `0004` serves both
  from shipped files (`root/sensors/ssc_core/{ssc_mode,ssc_hw_rev}`, mapped at
  the virtual sysfs paths, same mechanism as `/sys/devices/soc0`).
  - `ssc_mode` = `0\n`: per Samsung `drivers/adsp_factory/ssc_core.c` this is an
    MST/NFC magnetometer-antenna selector (`ANT_NFC_MST=0`), the neutral value
    for non-MST hardware — **not** a sensor enable gate.
  - `ssc_hw_rev` = `0\n`: the driver returns `sec_hw_rev()` ("%d\n"). `0` is a
    placeholder. **Tuning knob:** if a config group is keyed on hw_rev, edit the
    file on-device (no rebuild) until sensors appear.

- **Likely true root cause (kernel-side, OUT of this PC-side scope).** The
  watchdog signature matches the mainline Tab S8+ case where a sensor whose
  regulators/I2C the DT did not bring up made the SEE thread block on a dead bus
  until the watchdog fired (disappears with empty configs — same as here). The
  a52q DT must keep the LSM6DSO / STK31610 / AK991x regulators on and wire the
  correct I2C bus, or the crash persists regardless of hexagonrpcd. Patch 0004
  removes a confirmed error path but may not by itself stop the watchdog.

Rebuilt `hexagonrpcd` (aarch64, glibc ≤ 2.38) now carries patches 0001–0004.
Verified with a native harness: `/sys/class/sensors/ssc_core/ssc_mode` and
`ssc_hw_rev` resolve and read `0\n`; `/sys/devices/soc0` still resolves.

## SAFE on-device test plan (cannot boot-loop)

hexagonrpcd stays **MASKED** at boot, so it never autostarts. Run the binary
**manually, once**, in the foreground as user `fastrpc`, while watching dmesg.
If the ADSP still crashes, the phone resets **once** and comes back with
hexagonrpcd still masked → no loop.

```sh
# --- one-time: make sure it can't autostart ---
ssh root@172.16.42.1 'systemctl mask hexagonrpcd iio-sensor-proxy'

# --- from laptop: push the served tree (tar preserves the sns_reg.conf symlink) ---
tar -C ~/linux-a52q/sensors/root -cf - sensors | \
  ssh root@172.16.42.1 'tar -C /var/lib/droid-juicer/sensors -xf -'
ssh root@172.16.42.1 'mkdir -p /var/lib/a52q-test'
scp ~/linux-a52q/sensors/hexagonrpcd root@172.16.42.1:/var/lib/a52q-test/hexagonrpcd
```

On the phone (root):

```sh
chmod 0755 /var/lib/a52q-test/hexagonrpcd
ln -sfn /usr/share/bengalos-a52q/socinfo /var/lib/droid-juicer/sensors/socinfo  # if missing
rm -f /var/lib/droid-juicer/sensors/sensors/registry/*        # let the PD regenerate
chown -R fastrpc:fastrpc /var/lib/droid-juicer/sensors/sensors

# terminal A — watch the ADSP (leave running):
dmesg -w | grep --line-buffered -iE 'adsp|pdm|sensor_process|remoteproc|crash|SError'

# terminal B — run the daemon ONCE as fastrpc, foreground:
runuser -u fastrpc -- /var/lib/a52q-test/hexagonrpcd \
  -f /dev/fastrpc-adsp -d adsp -s -R /var/lib/droid-juicer/sensors
#   (no runuser? use: setpriv --reuid=fastrpc --regid=fastrpc --clear-groups -- <same>)
```

Watch ~15 s:
- **No `sensor_process crash` / ADSP fatal** and the `ssc_core` error spam is
  gone → it survived; verify sensors below.
- **ADSP crashes** → phone hard-resets once. Because hexagonrpcd is masked it
  will NOT run next boot (no loop). SSH back in (~90 s) and read
  `journalctl -k -b | grep -iE 'ssc_core|sns_reg|sensor_process|adsp|pdm'`.
  If the signature is still `UTMR_CLNT_1/sns_thread_mana`, it's the DT
  regulator/I2C issue above — hexagonrpcd changes won't fix it.

Verify sensors (while the manual hexagonrpcd is still running, in a 3rd shell):

```sh
runuser -u fastrpc -- /usr/libexec/iio-sensor-proxy -r   # foreground debug; or: systemctl start iio-sensor-proxy
monitor-sensor --accel                 # expect X/Y/Z updates (LSM6DSO)
monitor-sensor --light                 # expect light level (STK31610)
G_MESSAGES_DEBUG=all monitor-sensor    # verbose: lists every detected sensor
```

Unmask permanently once it works:

```sh
# make the rebuilt binary the real one first (see "Recipe change"), then:
systemctl unmask hexagonrpcd iio-sensor-proxy
systemctl enable --now hexagonrpcd iio-sensor-proxy
rm -rf /var/lib/a52q-test
```
