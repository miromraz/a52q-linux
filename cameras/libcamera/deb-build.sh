#!/bin/sh
# Build the Debian libcamera 0.7.2-1 binary packages with the a52q patch series,
# natively inside a Debian forky arm64 container (on the phone: podman container
# "lcb", /home/a52cam-uw mounted on /w). Expects libcamera_0.7.2-1.dsc + tarballs
# and the patches/ directory next to this script (WORK dir).
#   sh deb-build.sh /w/integ
set -eu
W=${1:-/w/integ}
PROFILES=nocheck,nodoc,pkg.libcamera.nopython,pkg.libcamera.noqt,pkg.libcamera.nosdl
export DEBIAN_FRONTEND=noninteractive LC_ALL=C.UTF-8
export DEBEMAIL=jarda.kotesovec@proton.me DEBFULLNAME="a52q camera integration"
cd $W
if [ ! -f /.a52q-deps-done ]; then
	apt-get -qq update
	apt-get -qq install -y --no-install-recommends devscripts quilt dpkg-dev \
		libegl-dev libgles-dev libgbm-dev
	apt-get -qq build-dep -y --build-profiles $PROFILES --no-install-recommends ./libcamera_0.7.2-1.dsc
	touch /.a52q-deps-done
fi
rm -rf deb && mkdir deb && cd deb
dpkg-source -x ../libcamera_0.7.2-1.dsc libcamera-0.7.2
cd libcamera-0.7.2
for p in ../../patches/*.patch; do
	cp $p debian/patches/
	basename $p >> debian/patches/series
done
QUILT_PATCHES=debian/patches quilt push -a -q
# The rules hardcode these on; the profiles only gate the build-deps. The GPU
# debayer (needed by the LSC stage) must not silently fall back to CPU-only.
sed -i 's/-Dpycamera=enabled/-Dpycamera=disabled/; s/-Dtest=true/-Dtest=false -Ddocumentation=disabled -Dsoftisp-gpu=enabled/; s/-Dqcam=$(QCAM)/-Dqcam=disabled -Dlc-compliance=disabled/' debian/rules
rm -f debian/python3-libcamera.install
dch -v 0.7.2-1+a52q2 "Galaxy A52 5G (a52q): sensor helpers, soft ISP lens shading, AGC frame-duration extension, AWB persistence, contrast AF, tuning files, aspect-matched sensor modes, centred GPU crop, 4-line padded GPU output buffers." -D forky --force-distribution
DEB_BUILD_OPTIONS="nocheck nodoc parallel=4" nice -n 10 dpkg-buildpackage -B -d -uc -us -P$PROFILES
ls -la ../*.deb
echo DEB_BUILD_DONE
