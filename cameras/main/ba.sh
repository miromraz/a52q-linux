#!/bin/sh
# before/after soft-ISP captures: stock driver+uncalibrated, new driver+uncalibrated, new driver+s5kgw1p.yaml
W=/var/tmp/camwork/main; O=/tmp/mainba; rm -rf $O; mkdir -p $O
ID=/base/soc@0/cci@ac4a000/i2c-bus@0/camera@2d
echo 8 > /sys/class/leds/white:torch/brightness
rmmod s5kgw1p; modprobe s5kgw1p; sleep 1
timeout 40 python3 $W/gstcap.py $O/old 8 $ID > $O/old.log 2>&1
rmmod s5kgw1p; insmod $W/s5kgw1p.ko; sleep 1
timeout 40 python3 $W/gstcap.py $O/new 8 $ID > $O/new.log 2>&1
LIBCAMERA_IPA_CONFIG_PATH=$W/ipa timeout 40 python3 $W/gstcap.py $O/tuned 8 $ID > $O/tuned.log 2>&1
echo 0 > /sys/class/leds/white:torch/brightness
grep -h "tuning file\|falling back\|configuring streams\|Exposure\|frames:" $O/*.log
