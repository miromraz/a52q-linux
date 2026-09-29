#!/bin/sh
# Soft-ISP capture of the macro camera with libcamera `cam`, torch on.
# usage (on the phone, takes the camera lock itself):
#   shoot.sh OUT.ppm [TUNING] [WxH] [FRAMES]
# TUNING (a yaml file) is exported as LIBCAMERA_SIMPLE_TUNING_FILE.
D=$(dirname "$(readlink -f "$0")")
OUT=$1; T=$2; WH=${3:-1296x972}; N=${4:-40}
[ -n "$T" ] && export LIBCAMERA_SIMPLE_TUNING_FILE=$T
exec flock /run/a52cam.lock sh -c "
  echo \${TORCH:-4} > /sys/class/leds/white:torch/brightness
  F=/dev/shm/macrocam; rm -rf \$F; mkdir -p \$F
  $D/cam.sh -c ${CAMIDX:-4} -C$N --metadata \
    -s width=${WH%x*},height=${WH#*x},pixelformat=BGR888 -F\$F/#.ppm > $D/cam.log 2>&1
  echo 0 > /sys/class/leds/white:torch/brightness
  python3 $D/macrocap.py restore
  mv \$(ls \$F/*.ppm | sort | tail -1) $OUT; rm -rf \$F
  grep -E 'tuning|Tuning|ERROR' $D/cam.log | head -5
  grep -E 'AnalogueGain|ExposureTime|ColourGains|ColourTemperature' $D/cam.log | tail -4"
