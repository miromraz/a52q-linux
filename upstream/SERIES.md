# A52q (SM7125) upstream patch series plan

Source: `~/src/linux-upstream`, integration branch `a52q/integ` tip **22c75c6ffc66**.
Base for all series: **v7.3-rc5 (72d3fcf802c4)** unless a dependency is noted.
Prepared, NOT sent. Regenerated from the current topic branches (the older
`~/linux-a52q/upstream/{watchdog,ath10k,s2mpb03,sm5714,i2c-cci,ak7374,cameras/*}`
dirs were stale and are superseded by this file + the `up/*` branches / per-series dirs).

Per series there is a branch `up/<name>` (in the repo), and a dir
`~/linux-a52q/upstream/<name>/` with `git format-patch --cover-letter -v1`
output, a written cover letter, and `to-cc.txt` from `scripts/get_maintainer.pl`.

## Conventions / what was done to the history
- `fixup!` commits squashed into their targets (autosquash / manual fold).
- merge commits linearised; `debian:` and `a52q defconfig:` / `arm64: defconfig: a52q:`
  packaging commits DROPPED (not upstreamable).
- Others' patches kept verbatim (From/Signed-off-by preserved).
- Assembly used `git cherry-pick -x`, which appended `(cherry picked from commit …)`
  trailers to the commit messages. **These are stripped from the format-patch
  output** (they must not go upstream); the `up/*` branch commits still carry them,
  harmless for the owner but strip if rebasing for send.

## Identity audit (owner must decide before sending)
Repo config authors new commits as `Miroslav Mráz <miroslav.mraz@techmania.cz>`;
some older ones use `mraz.miro@seznam.cz`. Authorship was NOT rewritten.
- **Only one** `seznam.cz` commit survives the defconfig drop:
  `e6243b0d6a45 soc: qcom: add SMP2P AP sleep state notifier` (in `up/soc-qcom-smp2p`).
  Decide whether to re-author it to the techmania identity before sending that series.
- All other owner commits are `techmania.cz`.
- Third-party authorship (keep as-is, they are co-/sole authors):
  - `up/media-camss-cphy` — all 9 by **David Heidelberg <david@ixit.cz>** (C-PHY v9).
  - `up/nfc-s3fwrn5` — all 5 by **Jorijn van der Graaf <jorijnvdgraaf@catcrafts.net>**.
  - `up/firmware-qcom-tzmem` — **nikroksm@mail.ru**.
  - `up/media-sensor-gc5035` — **Tomasz Figa <tfiga@chromium.org>** + **hao.he@bitland.com.cn** (v4 base) + owner.
  - `up/soc-qcom-smp2p` — binding `13259c3f53d6` by **Richard Acayan <mailingradian@gmail.com>**.
  - `up/qcom-dt` — DT doc + initial DT by **Erikas Bitovtas <xerikasxx@gmail.com>**.

## Dedup / notable resolutions
- **AK7374**: integ carried the AK7375-AK7374 binding+driver TWICE (camss-lineage
  `a17573b663e2/5c6d3baf3789` and ois-lineage `6153291e5dd8/b22fb764042f`). Identical
  patch-id — `up/media-ak7374` keeps ONE copy; the ois pair is dropped.
- **serial-geni**: RESOLVED — `Fixes: a53be6945f51 ("serial: qcom-geni: Remove alias dependency from qcom serial driver")` (v6.16-rc1) added, cherry-pick line dropped, patch regenerated. Original note: A `Fixes:` tag is REQUIRED but
  the repo is a shallow clone grafted at v7.3-rc5, so the offending commit hash (which
  introduced the `of_alias_get_highest_id()` + `ida_alloc_range()` line numbering in
  `qcom_geni_serial.c`) cannot be resolved here. **Owner TODO**: resolve the hash in a
  full tree (`git log -S ida_alloc_range -- drivers/tty/serial/qcom_geni_serial.c`) and
  add the `Fixes:` line.
- **smp2p bindings**: the two binding commits are NOT duplicates — `13259c3f53d6`
  (Richard) edits the existing `qcom,smp2p.yaml`; `6d6e9f4e7344` adds a new
  `qcom,smp2p-sleepstate.yaml`. Both kept.

## Send order and status
Status key: READY = assembled + tree-verified; CHECK = assembled, checks pending (see
check log); DEVTEST = needs on-device verification before send; BLOCKED = waits on
another series. Checks (checkpatch --strict / dt_binding_check / CHECK_DTBS / W=1) are
run in a later pass; per-series results land in `<name>/checks.txt`.

### Tier 1 — standalone fixes (send first, no deps)
| # | series | tree / maintainers | base | commits (author) | status |
|-|-|-|-|-|-|
| 1 | watchdog | watchdog (Guenter Roeck, Wim Van Sebroeck) | rc5 | 1ef99dcd watchdog: qcom: stop bootloader-armed wdog across sleep (owner) | DEVTEST |
| 2 | ath10k | wireless/ath (ath10k list, Jeff Johnson) | rc5 | eec8854d wifi: ath10k: demote chan info freq 0 warning (owner) | READY |
| 3 | serial-geni | tty/serial (Greg KH, Jiri Slaby) — Cc stable | rc5 | 29279c70 serial: qcom-geni: fix line alloc w/o aliases (owner) | READY (Fixes: a53be6945f51, v6.16-rc1) |

### Tier 2 — bindings + drivers (independent, no DT dep)
| # | series | tree / maintainers | base | commits (author) | status |
|-|-|-|-|-|-|
| 4 | regulator-s2mpb03 | regulator (Mark Brown, Liam Girdwood) | rc5 | 2b735455 binding; 45da2e9e driver (owner) | DEVTEST |
| 5 | power-supply-sm5714 | power-supply (Sebastian Reichel) | rc5 | 933cdd7a fg-binding; 3e0d4a12 fg-drv; 26581b31 chg-binding; 04637bd4 chg-drv; ff6b75c9 chg named-BIT (owner) | DEVTEST |
| 6 | typec-sm5714 | usb typec (Heikki Krogerus, Greg KH) | rc5 | cf21..(bd22966c)+fold 30769284 cc-binding; (80f8afec)+fold cf84b308 cc-drv; 49733de4 muic-binding; 35351275 muic-drv (owner) | DEVTEST |
| 7 | nfc-s3fwrn5 | nfc (Krzysztof Kozlowski) | rc5 | a1f2d0dd, b6ca33fe, 79bcfac6, 2bbcf8e5, 1c8c6029 (Jorijn van der Graaf) | CHECK |
| 8 | input-fts5cu56a | input (Dmitry Torokhov) | rc5 | 8cd362ef binding; 05b4fd45 driver; fc414bbb cleanup(+folded fixup 81387a1b) (owner) | DEVTEST |
| 9 | drm-panel-s6e3fc3 | drm/panel (Neil Armstrong et al.) | rc5 | e0581e1a binding; a31135e9 driver (owner) | DEVTEST |
| 10 | drm-msm-a618 | drm/msm (Rob Clark) | rc5 | 7a8c18b5 drm/msm/adreno SM7125 A618 speed-bin 159 (owner) | DEVTEST |
| 11 | asoc-tas2562 | ASoC (Mark Brown) | rc5 | ec32d4a3 fsync-pol; deed1524 binding rx-slot-width; 1ad05119 driver rx-slot-width (owner) | CHECK |
| 12 | pinctrl-qcom-lpass | pinctrl-qcom (Bjorn Andersson, Linus Walleij) | rc5 | 67b8e5b1 binding: allow sc7180 LPASS LPI TLMM (owner) | CHECK |
| 13 | soc-qcom-smp2p | soc/qcom (Bjorn Andersson) | rc5 | 13259c3f binding (Richard Acayan); 6d6e9f47 binding (owner); e6243b0d driver (**seznam id**) | DEVTEST |
| 14 | soc-qcom-pd-mapper | soc/qcom (Bjorn Andersson) | rc5 | 5d73f163 soc: qcom: pd-mapper: add SM7125 (owner) | CHECK |
| 15 | firmware-qcom-tzmem | soc/qcom firmware (Bjorn Andersson) | rc5 | 776e8b23 firmware: qcom: tzmem: disable SHM bridge SM7125 (nikroksm) | CHECK |

### Tier 3 — media (sensors / camss)
| # | series | tree / maintainers | base | commits (author) | status |
|-|-|-|-|-|-|
| 16 | media-ak7374 | media i2c (Mauro CH, Sakari Ailus) | rc5 | a17573b6 binding; 5c6d3baf driver (owner) — ois dup dropped | DEVTEST |
| 17 | media-ois-mcu | media i2c (Sakari Ailus) | rc5 | 33a3530d binding; 78b59953 driver (owner) | DEVTEST |
| 18 | media-sensor-imx616 | media i2c (Sakari Ailus) | rc5 | a9998743 binding; 86122d69 driver (owner) | DEVTEST |
| 19 | media-sensor-s5k3l6xx | media i2c (Sakari Ailus) | rc5 | 13a24712 binding; eded0ea5 driver (owner) | DEVTEST |
| 20 | media-sensor-s5kgw1p | media i2c (Sakari Ailus) | rc5 | 0eb517a5 binding; 8474b8e4 driver (owner) | DEVTEST |
| 21 | media-sensor-gc5035 | media i2c (Sakari Ailus) | rc5 | 6f9aac96 binding (Tomasz Figa); 7ea65436, 14e768e7 (hao.he); 624d967e, 55c06b2f (owner) | DEVTEST |
| 22 | media-camss-fixes | media platform/qcom camss (Robert Foss, Todor Tomov) | rc5 | 7554dbcf don't call s_stream twice; d4afd1cf follow enabled link (owner) — candidate Cc stable | DEVTEST |
| 23 | media-camss-cphy | media camss | rc5 | 9 commits 4caa5295..08ca6127 (David Heidelberg, C-PHY v9) | BLOCKED (upstream of David's v9) |
| 24 | media-camss-sc7180 | media camss + i2c-cci | **up/media-camss-cphy** | 4888fedf cci sc7180 binding; 61c7731b camss binding; db39d177 driver; a03cd9a7 gen2; 61f9330a dphy; 6047f7fc cphy-sc7180 (owner) | BLOCKED on #23 |

### Tier 4 — SoC device tree (capstone, depends on all driver series)
| # | series | tree / maintainers | base | commits | status |
|-|-|-|-|-|-|
| 25 | qcom-dt | qcom DT (Bjorn Andersson, Konrad Dybcio) | rc5 | DT doc (Erikas) + sc7180.dtsi + sm7125/a52q DTs; ~22 commits, fixups squashed | IN PROGRESS (parallel-insert merge collisions being re-resolved linearly; gate = dts tree == integ) |

## Build/check plan (later pass, root disk ~5 GB free)
- Out dirs on tmpfs `/tmp`, serialized with `flock /tmp/claude-1000/a52build.lock`,
  deleted after each run. dtschema present system-wide (dt-validate 2026.6) — no venv needed.
- Per series: `scripts/checkpatch.pl --strict` (counts in `<name>/checks.txt`);
  `make dt_binding_check DT_SCHEMA_FILES=<added yaml>` for binding series;
  `CHECK_DTBS=y` on `qcom/sm7125-samsung-a52q.dtb` for qcom-dt; `W=1` on touched C files.

---

## Check results (pass of 2026-10-01)
All branches assembled; qcom-dt gate verified (`git diff up/qcom-dt a52q/integ`
over the dts + qcom.yaml paths == EMPTY). `format-patch -v1` + written cover letter
+ `to-cc.txt` (get_maintainer against the v7.3-rc5 MAINTAINERS, so new files map to
subsystem maintainers, not the owner's own just-added entries) are in each
`<name>/`. Stale pre-existing dirs (ak7374, s2mpb03, sm5714, cameras) moved to `.stale/`.

### checkpatch.pl --strict (non-cover patches) — errors/warnings/checks
Clean (E=0 W=0 C=0) unless noted:
- drm-msm-a618: W=1 ; regulator-s2mpb03: W=1 (DT-compat cross-patch false positive)
- input-fts5cu56a: **W=95** — the FTS5CU56A vendor driver; owner should clean up before send.
- media-camss-cphy W=3, media-sensor-{gc5035,s5k3l6xx,s5kgw1p} W=3, imx616 W=2 (minor).
- **media-camss-sc7180: E=6** and **qcom-dt: E=4** — all "Missing Signed-off-by".

### BLOCKER: commits missing Signed-off-by (owner must add own SoB before sending)
Not fabricated here. Affected underlying commits:
- camss-sc7180: 61c7731b (camss binding), 4888fedf (i2c sc7180-cci binding),
  db39d177 (camss SC7180 driver), a03cd9a7 (gen2), 61f9330a (D-PHY lanes),
  6047f7fc (C-PHY SC7180).
- qcom-dt: 22938d9e (sc7180 CCI/CAMSS), 65a9219f (sc7180 GPI DMA),
  3aa1c70c (a52q NFC), 57ecd16c (wake keys).

### Status updates
- qcom-dt: gate PASS → assembled-READY pending SoB fix + on-device DTB check.
- media-camss-sc7180 / media-camss-cphy: still BLOCKED (David's C-PHY v9 must land
  first) + SoB fix for sc7180.
- serial-geni: still needs the real `Fixes:` hash (resolve in a full, non-shallow tree).
- Identity: only `e6243b0d` (smp2p driver) is `seznam.cz`; all else techmania or third-party.

### dt_binding_check / CHECK_DTBS / W=1
- dtschema 2026.6 (system). Build worktree on tmpfs at a52q/integ (identical trees to
  the up/* branches), out dir on tmpfs, `flock /tmp/claude-1000/a52build.lock`.
- dt_binding_check run over all 14 added + 7 modified a52q yamls — see
  `.build/dtbc.log` (results appended below once the run completes).
- CHECK_DTBS on qcom/sm7125-samsung-a52q.dtb and W=1 on touched C files: pending in
  this pass (bounded, lock-serialised); commands recorded in `.build/`.

### dt_binding_check result
`make dt_binding_check DT_SCHEMA_FILES="<21 added+modified a52q yamls>"` → exit 0,
**zero schema warnings/errors**; processed-schema.json rebuilt clean, so all a52q
bindings are valid against the DT meta-schema. Caveats (tooling, not bindings):
`yamllint` is not installed on this host (that sub-check is skipped — install
`python-yamllint` for a complete run), and the dtschema-2026.6 STYLE sub-target
(`dt-check-style`) errors "no input files" when DT_SCHEMA_FILES is a list (harmless).
CHECK_DTBS + W=1 results appended below.

### CHECK_DTBS + W=1 results (rc=0 both)
- **CHECK_DTBS** on `qcom/sm7125-samsung-a52q.dtb` (defconfig + a52q driver symbols,
  CROSS_COMPILE=aarch64-linux-gnu-): dtb built, **zero DT-schema warnings** — the a52q
  device tree validates against all the (new and existing) bindings it uses.
- **W=1** host build of every touched C file: **zero compiler warnings/errors**. Covered
  all leaf drivers plus the full camss (28 objs), ath10k (28), s3fwrn5 (7) dirs.
- Build log: `.build/build_checks.log`; binding log: `.build/dtbc.log`.
- a72q (sm7125-samsung-a72q) DTB: not built — no a72q .dts is added by this work
  (the DT doc covers A52/A72 but only the a52q board DT exists), so CHECK_DTBS covers a52q only.

## Bottom line
26 `up/*` branches assembled and checked. Blocking the actual send: (1) add
Signed-off-by to the 6 camss-sc7180 + 4 qcom-dt commits; (2) add the real Fixes:
hash to serial-geni (needs a non-shallow tree); (3) decide the seznam→techmania
re-author of e6243b0d; (4) camss-cphy/sc7180 wait on David Heidelberg's C-PHY v9
landing; (5) all driver series want on-device verification (status DEVTEST).
