#!/bin/bash
# Build U-Boot for samsung-a52q and package it as an Odin-flashable AP tar
# (boot.img + empty dtbo.img). Header params from pmaports device-samsung-a52q deviceinfo.
set -e
cd "$(dirname "$0")"
OUT=out; mkdir -p $OUT

[ -f u-boot/.output/.config ] || make -C u-boot O=.output qcom_a52q_defconfig qcom-phone.config a52q.config
( cd u-boot && make O=.output CROSS_COMPILE=aarch64-linux-gnu- -j"$(nproc)" 2>&1 | tail -3 )
NODTB=u-boot/.output/u-boot-nodtb.bin
DTB=u-boot/.output/dts/upstream/src/arm64/qcom/sm7125-samsung-a52q.dtb

# qcom U-Boot reads its control DTB appended after the gzip stream (Image.gz-dtb style);
# ABL also picks this DTB by its qcom,msm-id / qcom,board-id.
gzip -9 -n -c "$NODTB" > $OUT/kpayload.bin
cat "$DTB" >> $OUT/kpayload.bin

# ABL wants a ramdisk; U-Boot ignores it.
echo | cpio -o -H newc 2>/dev/null | gzip -9 -n > $OUT/ramdisk.gz

mkbootimg --kernel $OUT/kpayload.bin --ramdisk $OUT/ramdisk.gz \
	--base 0x0 --kernel_offset 0x8000 --ramdisk_offset 0x2000000 \
	--second_offset 0x0 --tags_offset 0x1e00000 \
	--pagesize 4096 --header_version 0 \
	-o $OUT/boot.img

# DTBO with INVALID magic: ABL then skips overlays and boots the appended DTB alone.
# A valid header with 0 entries does NOT work - ABL fails "Board Dtbo blob not found"
# and drops to Download Mode (tested 2026-09-24; velvet-os emptyDTBO.img is also bad-magic).
head -c 4096 /dev/zero > $OUT/dtbo.img

tar -C $OUT -H ustar -cf $OUT/AP-uboot-a52q.tar boot.img dtbo.img
ls -la $OUT/boot.img $OUT/dtbo.img $OUT/AP-uboot-a52q.tar
