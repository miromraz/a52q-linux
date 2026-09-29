#!/bin/sh
# afsweep.sh OUTDIR POS... : park the AK7374 (10-bit DAC, reg0 = pos<<6) at each
# position and grab one raw frame. Sensor forced on so VAF stays up between grabs.
W=/var/tmp/camwork/main; O=$1; shift; mkdir -p $O
echo on > /sys/bus/i2c/devices/20-002d/power/control; sleep 0.2
echo 8 > /sys/class/leds/white:torch/brightness
python3 $W/i2cbb.py --bus 9 wr 0x0c 0x02 0x40
python3 $W/subctl.py s5kgw1p vblank=16500 exposure=20000 again=256
for p in "$@"; do
  v=$((p << 6))
  python3 $W/i2cbb.py --bus 9 wr 0x0c 0x00 $((v >> 8)) $((v & 255))
  python3 $W/i2cbb.py --bus 9 wr 0x0c 0x02 0x00
  echo "pos $p: $(python3 $W/i2cbb.py --bus 9 rd 0x0c 0x00 3)"
  python3 $W/camcap.py capture s5kgw1p msm_csid0 1 msm_vfe0_video0 $O/af_$p.raw 4 | grep saved
done
python3 $W/i2cbb.py --bus 9 wr 0x0c 0x02 0x40
python3 $W/subctl.py s5kgw1p vblank=16500 exposure=20000 again=256
echo 0 > /sys/class/leds/white:torch/brightness
python3 $W/subctl.py s5kgw1p vblank=44 exposure=3000 again=32
echo auto > /sys/bus/i2c/devices/20-002d/power/control
