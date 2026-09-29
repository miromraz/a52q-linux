# UW S5K3L6 — agent report (2026-09-27)
Stock tuning (tuned.lsi_s5k3l6.bin): BL 64@10b (dark 63.5-63.9), GRBG, LSC 17x13 mesh, corner gain 5.66
(~2.5 EV), LSC faded in low light; CCM diag 1.8-2.0; AEC max 100 ms, gain 16x A x 3.5x D. No module
LSC in OTP; uw_dual_calibration.bin has no distortion data.
Driver: PIXEL_RATE 477.87 MHz (frame time within 0.02%), crop rects, exposure 2..VTS-10, gain 1-16x,
new 2000x1500 2x2 binned mode (bars clean, 30/59.8 fps). Both modes 30 fps under libcamera.
libcamera 0.7.2: 0001 sensor helper (gain=reg/32) + properties; 0002 GPU soft-ISP LSC (CPU path
ignores); verified on solid-grey test pattern vs stock mesh (R/G 1-4%, B ~8% low).
s5k3l6xx.yaml generated from stock; Lsc block breaks unpatched libcamera.
Integrate: s5k3l6xx.ko, libcamera 0001+0002 (phone build /home/a52cam-uw/bld, podman 1.8 GB deletable).
Decision: binned mode chosen for viewfinder -> 3 MP stills unless 2nd mode entry removed.
Blocked: no real-scene check (phone face-up); stock gamma not ported; phone RCU-stall crash ~10 s
into torch capture (cause unknown).
