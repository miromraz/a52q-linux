# Main S5KGW1P — agent report (2026-09-27)
Driver (in place): again 0x20-0x400 (x32 code), dgain 0x020E; exposure 4..VTS-4; pixel rate 1440 MP/s
confirmed by fps; H/V flip + bayer follows (stock stream-on cleared flip reg); new 2000x1128 4x4-binned
16:9 mode 30-120 fps (runs on 1 GHz link; stock 1.7 GHz refused by camss).
s5kgw1p.yaml: BL 64 (measured 63.96) + 6 stock CCMs.
AF: AK7374 @0x0c on i2c9 (disabled in mainline); lens range 301 (inf) .. 759 (macro) from EEPROM.
Verified via bit-banged i2c. Patches 0001 ak7375 driver + AK7374, 0002 DT i2c9 + lens-focus, 0003 defconfig.
OIS: STM32G @0x62 on i2c10 runs factory fw -> feasible, not done (held in reset).
Full 64 MP: needs proprietary remosaic + faster link; not worth it.
Blocked: AF kernel path needs DTB reboot; contrast AF needs Pixel 4a softisp AF patch; no LSC in 0.7.2
soft ISP (UW agent wrote one); real-scene check needs phone facing a scene (sh /var/tmp/camwork/main/ba.sh).
Incidents: reading /sys/kernel/debug/gpio preceded the 08:59 RCU-stall crash - avoid.
