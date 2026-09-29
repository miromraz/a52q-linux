# Front IMX616 — agent report (2026-09-27)
Root bug: driver reported GRBG, sensor is RGGB (test-pattern decode) -> magenta/green cast. Fixed.
Gain = 1024/(1024-reg), reg 112..960 (1.12-16x); measured ratios 1.782/3.583/7.203 vs model 1.781/3.562/7.125.
Exposure min 16, max VTS-48 (stock). BL 64@10b. New 1632x1224 mode (30 fps default, clean at 118 fps).
Two stock modes with 516 MHz link, per-mode pixel rate/blanking, h/v flip, pixel-array selections.
Stock CCM/AWB/LSC/gamma decoded; LSC mesh imx616-lsc-mesh.yaml (corners 4.3-4.8x).
Full 32 MP needs software remosaic (~12 fps) - not done.
EEPROM 0x51 on i2c9 (gpio46/47), bus disabled in mainline -> dts patch enables it + AT24.
Integrate: imx616.yaml, libcamera-imx616-sensor-helper.patch (uncompiled), dts-front-rotation-eeprom.patch
(front rotation 90, derived not eye-checked).
Unverified: processed after-shot (camera saw black since ~09:20), CCM on colour target, rotation by eye.
Note: select cameras by id, cam -c N index shifts after module reloads.
