# Depth GC5035 — agent report (2026-09-27)
Main bug: digital gain ctrl defaulted ~16x and libcamera never touched it -> noisy image. Removed; analogue
gain = total gain /256 (1-48x), split into 16-step table + fine pre-gain like stock .so.
Binned 1296x972/1280x720 had wrong line length (1460/1896 -> 2920 measured); 720p is 30 fps not 60.
Mode switch resets vblank (full-res ran 18.6 fps after 720p). get_selection added. OTP DPC load ok (3 defects).
Evidence: gain regs read back; dark noise 0.87@1x 2.2@3.9x 23@48x, BL 64; gain delay 2 frames;
cam depth 20.1 -> 30.0 fps; dark noise 7.5 -> 1.5, column banding 4.1 -> 0.2; macro still works.
Stock tuning: depth CCM = identity, BL 64, LSC corners 4.5x (gc5035_depth-lsc.yaml), AEC 41.7ms@1x ->15x ->66.7ms ->48x.
Integrate: kernel tree, libcamera-0.7.2-gc5035.patch, gc5035.yaml (uses macro CCMs; depth+macro share model name).
macro agent's macrocap.py needs update for removed digital gain ctrl.
Unverified: real scene colour/AE, bayer order by eye, exposure delay (set 2).
