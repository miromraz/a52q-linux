#!/bin/bash
# CHECK_DTBS (a52q dtb) + W=1 build of every touched C file.
# Runs in the tmpfs build worktree (checked out at a52q/integ == the up/* trees),
# out dir on tmpfs, serialised with flock. Rebuildable; safe to lose on reboot.
set -u
WT=/tmp/claude-1000/wt-build
O=/tmp/claude-1000/out
LOG=/home/realni/linux-a52q/upstream/.build/build_checks.log
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
SYMS="REGULATOR_S2MPB03 BATTERY_SM5714 CHARGER_SM5714 TYPEC_SM5714_CC TYPEC_MUX_SM5714 \
TOUCHSCREEN_STMFTS_FTS5CU56A DRM_PANEL_SAMSUNG_S6E3FC3 QCOM_SMP2P_SLEEPSTATE \
VIDEO_GC5035 VIDEO_IMX616 VIDEO_S5K3L6XX VIDEO_S5KGW1P VIDEO_SAMSUNG_OIS_MCU VIDEO_AK7375 \
VIDEO_QCOM_CAMSS SND_SOC_TAS2562 NFC_S3FWRN5_I2C NFC_S3FWRN5_UART ATH10K_PCI \
DRM_MSM SERIAL_QCOM_GENI QCOM_WDT I2C_QCOM_CCI QCOM_TZMEM QCOM_PD_MAPPER REGULATOR TYPEC NFC"
OBJS="drivers/firmware/qcom/qcom_tzmem.o drivers/gpu/drm/msm/adreno/a6xx_catalog.o \
drivers/gpu/drm/panel/panel-samsung-s6e3fc3.o drivers/i2c/busses/i2c-qcom-cci.o \
drivers/input/touchscreen/stmfts_fts5cu56a.o drivers/media/i2c/ak7375.o \
drivers/media/i2c/gc5035.o drivers/media/i2c/imx616.o drivers/media/i2c/s5k3l6xx.o \
drivers/media/i2c/s5kgw1p.o drivers/media/i2c/samsung-ois-mcu.o \
drivers/media/platform/qcom/camss/ drivers/net/wireless/ath/ath10k/wmi.o \
drivers/nfc/s3fwrn5/ drivers/power/supply/sm5714-charger.o drivers/power/supply/sm5714-fg.o \
drivers/regulator/s2mpb03-regulator.o drivers/soc/qcom/qcom_pd_mapper.o \
drivers/soc/qcom/smp2p_sleepstate.o drivers/tty/serial/qcom_geni_serial.o \
drivers/usb/typec/mux/sm5714-muic.o drivers/usb/typec/sm5714-cc.o \
drivers/watchdog/qcom-wdt.o sound/soc/codecs/tas2562.o"

run() {
  cd "$WT" || exit 1
  : > "$LOG"
  echo "== defconfig ==" | tee -a "$LOG"
  make -s O="$O" defconfig >>"$LOG" 2>&1
  for s in $SYMS; do ./scripts/config --file "$O/.config" -m "$s" 2>/dev/null; done
  make -s O="$O" olddefconfig >>"$LOG" 2>&1
  echo "== CHECK_DTBS: sm7125-samsung-a52q.dtb ==" | tee -a "$LOG"
  make O="$O" CHECK_DTBS=y qcom/sm7125-samsung-a52q.dtb >>"$LOG" 2>&1
  echo "rc_dtbs=$?" | tee -a "$LOG"
  echo "== W=1 objects ==" | tee -a "$LOG"
  make -k O="$O" W=1 $OBJS >>"$LOG" 2>&1
  echo "rc_w1=$?" | tee -a "$LOG"
  echo "== summary ==" | tee -a "$LOG"
  grep -iE 'warning:|error:|\.dtb' "$LOG" | grep -vE 'Documentation/devicetree/bindings/(example|dtschema)' | tail -60
}
flock /tmp/claude-1000/a52build.lock bash -c "$(declare -f run); run"
