# Macro GC5035 — agent report (2026-09-27)
Variant: hw_2 (adds 1.2V DVDD; rev>=r02); streams with AVDD gpio64 + DVDD L4 as our DT has.
Same regs/mode as depth (2576x1932 RAW10, 2 lanes 876 Mbps, 24 MHz MCLK, 0x17=0x80).
OTP (otp-22-003f.bin): module A52_QCR3 V701V001, WB R/G 0.615 B/G 0.546.
Chromatix: BL 64@10b, 3 lux-range CCMs, AWB refs, bright gamma + low AE target (28/255), 17x13 LSC (R corner 3.8x).
Old driver gain bugs (codes 21-31 -> 1x, 4-7 repeat 8-11, dgain 16x) fixed by depth agent's gc5035.c.
Macro vs depth: DT `label` -> sensor name "gc5035_macro" -> libcamera loads gc5035_macro.yaml (verified with forced name).
Integrate: gc5035-macro.patch (driver reads label), dts-macro-label.patch, libcamera-0.7.2-gc5035-macro.patch
(on top of depth's gc5035 patch, uncompiled), gc5035_macro.yaml. LSC in gc5035_macro-lsc.yaml.
CT keys remapped to libcamera's estimate scale (inferred). depth yaml CCMs ~1 step too warm.
Issues: video-mux can stick on macro with both links disabled -> UW "busy"; `macrocap.py restore` recovers.
pipeline_pm_power_one warning on each link change.
