# A52q (SM7125) upstream series — regeneration status (2026-10-03)

Regenerated after today's integ merges (tip 75e4cb4def35): the psy / usbflap /
nits / camfix2 / camlanes / camreset2 / qrtr topic work folded into the right
series and the standalone fixes split out. All patches re-checked with
`scripts/checkpatch.pl --strict` and `git am`-verified in a sparse scratch
worktree (`~/src/wt-upstream-amcheck`, built from the shared object store — root
disk had <1 GB free, so no full checkout and no local build this pass; the
underlying commits were W=1-clean when authored per DEBUG.md). `git am` of every
series was replayed onto its stated base and applied with zero rejects.
Signed-off-by: Miroslav Mráz <miroslav.mraz@techmania.cz> on all owner commits.
Nothing sent, nothing pushed.

## 1. power-supply-sm5714 (regenerated, psy folds)
- Base: v7.3-rc5 (72d3fcf802c4)
- Patches: 5 (+ cover). Folded in: monitored-battery -> 1/5 (fg binding);
  design charge/charge_now + charge_full -> 2/5 (fg driver); USB_TYPE prop ->
  4/5 (charger driver); 5/5 (named-BIT) rebased clean. The a52q DT battery node
  (32917e6) is device-specific and stays in the qcom-dt series, not here.
- checkpatch --strict: 0 errors / 0 checks. Warnings are the known cross-patch
  DT-compat + "MAINTAINERS needs updating?" false positives (binding lives in a
  sibling patch of the same series).
- Applies cleanly: yes, `git am` onto v7.3-rc5 (5/5).
- Recipients: Sebastian Reichel; linux-pm; Rob Herring, Krzysztof Kozlowski,
  Conor Dooley, devicetree; linux-kernel.

## 2. typec-sm5714 (regenerated, usbflap fold)
- Base: v7.3-rc5
- Patches: 4 (+ cover). Folded in: sm5714-cc host-mode (sink) attach debounce
  -> 2/4 (CC driver).
- checkpatch --strict: 0 errors / 0 checks (same benign DT-compat/MAINTAINERS
  warnings).
- Applies cleanly: yes, `git am` onto v7.3-rc5 (4/4).
- Recipients: Heikki Krogerus, Greg Kroah-Hartman; linux-usb; Rob Herring,
  Krzysztof Kozlowski, Conor Dooley, devicetree; linux-kernel.

## 3. drm-panel-s6e3fc3-backlight (new, 1 patch)
- Base: v7.3-rc5 + the drm-panel-s6e3fc3 series (the driver it fixes is added
  there, not yet in mainline).
- Patches: 1. "don't touch DSI from backlight ops while off". Added the missing
  Signed-off-by and rewrapped the commit body to <=75 cols.
- checkpatch --strict: clean (0/0/0).
- Applies cleanly: yes, `git am` onto v7.3-rc5 + drm-panel-s6e3fc3 (2 patches)
  then this one.
- Recipients: Neil Armstrong, Jessica Zhang, David Airlie, Simona Vetter,
  Maarten Lankhorst, Maxime Ripard, Thomas Zimmermann; dri-devel; linux-kernel.
- NOTE: since drm-panel-s6e3fc3 has not been sent, this one-liner could instead
  be folded into the driver patch (2/2 of that series). Kept standalone per the
  task; fold before send if the driver series is still unsent.

## 4. camss (new, 4 patches + cover)
- Base: NOT plain v7.3-rc5. Sits on the a52q camera stack =
  v7.3-rc5 + media-camss-cphy + media-camss-sc7180 +
  media-sensor-{gc5035,imx616,s5k3l6xx,s5kgw1p}. Verified against the integ
  commit 608f04bb7518 (the parent of the first camss fix), which carries that
  whole stack.
- Patches: 4 (+ cover), SoB added to all (the topic commits had none):
  1/4 reset output state + never arm WM without a buffer (camfix2 706d119);
  2/4 take CSIPHY/CSID lane count from the active sensor (camlanes ed05f7e);
  3/4 vfe-gen2 never arm WM with a zero pong (camreset2 6ca37d2);
  4/4 csiphy-3ph wait for revision id on cold power-up (camreset2 7d0278b).
- checkpatch --strict: all 4 clean (0/0/0).
- Applies cleanly: yes, `git am` onto 608f04bb7518 (4/4).
- Recipients: Bryan O'Donoghue, Robert Foss (camss), Loic Poulain,
  Vladimir Zapolskiy, Todor Tomov via list, Mauro Carvalho Chehab,
  Sakari Ailus; linux-media, linux-arm-msm; linux-kernel.
- Caveat: patch 2/4 depends on the four sensor drivers being upstream (it adds
  get_mbus_config to each); cannot go to mainline ahead of those media series.

## 5. qrtr (new, 1 patch)
- Base: v7.3-rc5
- Patches: 1. "net: qrtr: ns: retry service announcements on -EAGAIN".
- checkpatch --strict: clean (0/0/0).
- Applies cleanly: yes, `git am` onto v7.3-rc5.
- Recipients: Manivannan Sadhasivam; Jakub Kicinski, Paolo Abeni, Eric Dumazet,
  "David S. Miller", Simon Horman; netdev, linux-arm-msm; linux-kernel.
