#!/usr/bin/env python3
# Fill format-patch cover-letter templates with a real subject + blurb per series.
import os, re, glob, subprocess
UP = '/home/realni/linux-a52q/upstream'
# name -> (short subject, blurb body)
S = {
 'regulator-s2mpb03': ("regulator: add Samsung S2MPB03 camera PMIC",
   "Add a binding and driver for the Samsung S2MPB03, a small I2C PMIC that\nsupplies the rear camera rails (four LDOs + one buck) on the Samsung\nGalaxy A52 4G (a52q, SM7125)."),
 'power-supply-sm5714': ("power: supply: add Silicon Mitus SM5714 fuel gauge and charger",
   "Add bindings and drivers for the fuel-gauge and switching-charger blocks\nof the Silicon Mitus SM5714 PMIC used on the Samsung Galaxy A52 4G\n(a52q, SM7125). The Type-C CC and MUIC blocks of the same chip are sent\nas a separate series to the USB/typec tree."),
 'typec-sm5714': ("usb: typec: add Silicon Mitus SM5714 CC and MUIC drivers",
   "Add bindings and drivers for the Type-C CC detection block and the MUIC\ndata-role switch of the Silicon Mitus SM5714 PMIC (Samsung Galaxy A52 4G,\na52q, SM7125). The fuel-gauge and charger blocks of the same chip are\nsent separately to the power-supply tree."),
 'nfc-s3fwrn5': ("nfc: s3fwrn5: support the Samsung S3NRN4V variant",
   "Add support for the S3NRN4V NFC controller variant and its PVDD supply,\nplus two small cleanups, for the Samsung Galaxy A52 4G (a52q)."),
 'input-fts5cu56a': ("Input: add STMicroelectronics FTS5CU56A touchscreen driver",
   "Add a binding and driver for the STMicroelectronics FTS5CU56A touch\ncontroller used on the Samsung Galaxy A52 4G (a52q, SM7125)."),
 'drm-panel-s6e3fc3': ("drm/panel: add Samsung S6E3FC3 (AMS646YD04)",
   "Add a binding and driver for the Samsung S6E3FC3 command-mode DSI panel\n(AMS646YD04 module) used on the Samsung Galaxy A52 4G (a52q)."),
 'asoc-tas2562': ("ASoC: tas2562: frame-sync polarity and RX slot width",
   "Two small tas2562 extensions needed by the Samsung Galaxy A52 4G (a52q):\nframe-sync polarity inversion and a device-tree-pinned RX slot width."),
 'soc-qcom-smp2p': ("soc: qcom: add SMP2P AP sleep state notifier",
   "Add the SMP2P-based AP sleep-state notifier (and its binding) that the\nADSP sensor framework (SEE) requires to avoid faulting on system suspend,\nas used on the Samsung Galaxy A52 4G (a52q, SM7125)."),
 'media-ak7374': ("media: i2c: ak7375: add support for AK7374",
   "Add AK7374 support to the ak7375 VCM driver (and binding), as used on\nthe Samsung Galaxy A52 4G (a52q) rear camera."),
 'media-ois-mcu': ("media: add Samsung camera OIS MCU driver",
   "Add a binding and driver for the Samsung camera OIS MCU used on the\nGalaxy A52 4G (a52q)."),
 'media-sensor-imx616': ("media: add Sony IMX616 sensor driver",
   "Add a binding and driver for the Sony IMX616 image sensor (front camera\nof the Samsung Galaxy A52 4G, a52q)."),
 'media-sensor-s5k3l6xx': ("media: add Samsung S5K3L6XX sensor driver",
   "Add a binding and driver for the Samsung S5K3L6XX image sensor used on\nthe Samsung Galaxy A52 4G (a52q)."),
 'media-sensor-s5kgw1p': ("media: add Samsung S5KGW1P sensor driver",
   "Add a binding and driver for the Samsung S5KGW1P main image sensor used\non the Samsung Galaxy A52 4G (a52q)."),
 'media-sensor-gc5035': ("media: i2c: add Galaxycore GC5035 sensor driver",
   "Bring in Tomasz Figa's GC5035 driver (v4), add OTP handling, modernise\nit and add Samsung Galaxy A52 4G (a52q) depth/macro camera support.\nOriginal authorship of the imported patches is preserved."),
 'media-camss-fixes': ("media: qcom: camss: two subdev/link fixes",
   "Two camss fixes found while bringing up the Samsung Galaxy A52 4G (a52q):\navoid calling s_stream twice through a forwarding subdev, and follow the\nenabled link when finding the sensor."),
 'media-camss-cphy': ("media: qcom: camss: MIPI CSI-2 C-PHY support",
   "David Heidelberg's C-PHY support series (v9) for qcom camss, carried here\nunchanged as a dependency of the SC7180/SM7125 camss enablement. All\npatches retain their original authorship and trailers."),
 'media-camss-sc7180': ("media: qcom: camss: add SC7180 (SM7125) support",
   "Add SC7180/SM7125 camss support: CCI and CAMSS bindings, the VFE-170\nbased CAMSS_7180 version, CSIPHY D-PHY/C-PHY lane settings. Based on the\nC-PHY series. NOTE: these commits currently lack Signed-off-by lines --\nthe author must add them before this series is sent."),
}

def fill(name, subj, blurb):
    cov = glob.glob(f'{UP}/{name}/*0000-cover-letter.patch')
    if not cov: return False
    f = cov[0]; t = open(f).read()
    n = len(glob.glob(f'{UP}/{name}/v1-0*.patch')) - 1
    t = t.replace('*** SUBJECT HERE ***', subj)
    body = blurb + ("\n\nBased on v7.3-rc5. Not independently tested on hardware by the\n"
                    "submitter tooling; on-device verification pending.")
    t = t.replace('*** BLURB HERE ***', body)
    open(f,'w').write(t)
    return True

for name,(subj,blurb) in S.items():
    print(("OK " if fill(name,subj,blurb) else "SKIP ")+name)
