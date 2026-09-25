#!/bin/bash
# Self-test for the param-fixing logic. Builds the shim in TEST mode against a
# fake /sys + /dev tree and asserts the 2->1 reset, safety on other values,
# and no-crash when param is absent. Runs the real static aarch64 binary under
# qemu-aarch64-static when available, else a native build of the same source.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT

mkdir -p "$T/sys/class/block/sda17" "$T/sys/class/block/sda1" "$T/dev"
cat > "$T/sys/class/block/sda17/uevent" <<EOF
MAJOR=8
MINOR=17
DEVNAME=sda17
DEVTYPE=partition
PARTNAME=param
EOF
# a decoy non-param partition, to prove selection works
cat > "$T/sys/class/block/sda1/uevent" <<EOF
MAJOR=8
MINOR=1
DEVNAME=sda1
DEVTYPE=partition
PARTNAME=boot
EOF

# Build test binary: real aarch64 under qemu if present, else native.
BIN="$T/initwrap_test"
if command -v qemu-aarch64-static >/dev/null 2>&1; then
    aarch64-linux-gnu-gcc -static -Os -DTEST_ROOT="\"$T\"" -o "$BIN" "$HERE/initwrap.c"
    RUN=(qemu-aarch64-static "$BIN")
    echo "runner: qemu-aarch64-static (real static aarch64 binary)"
else
    cc -Os -DTEST_ROOT="\"$T\"" -o "$BIN" "$HERE/initwrap.c"
    RUN=("$BIN")
    echo "runner: native build (qemu-aarch64-static not found)"
fi

DEV="$T/dev/sda17"

# write a 4 KiB device with a given first word (4 little-endian bytes)
mkdev() { printf "$1" > "$DEV"; truncate -s 4096 "$DEV"; }
# read first byte as decimal
firstbyte() { od -An -tu1 -N1 "$DEV" | tr -d ' '; }

fail=0
check() { if [ "$2" = "$3" ]; then echo "PASS: $1"; else echo "FAIL: $1 (got '$2' want '$3')"; fail=1; fi; }

# 1) value 2 -> becomes 1
mkdev '\x02\x00\x00\x00'; out=$("${RUN[@]}"); check "value 2 -> 1" "$(firstbyte)" "1"
check "exec target printed" "$out" "EXEC /init.real"

# 2) value 1 -> unchanged
mkdev '\x01\x00\x00\x00'; "${RUN[@]}" >/dev/null; check "value 1 unchanged" "$(firstbyte)" "1"

# 3) value 7 -> unchanged
mkdev '\x07\x00\x00\x00'; "${RUN[@]}" >/dev/null; check "value 7 unchanged" "$(firstbyte)" "7"

# 4) missing param -> no crash, still execs
mv "$T/sys/class/block/sda17/uevent" "$T/sys/class/block/sda17/uevent.bak"
if out=$("${RUN[@]}"); then rc=0; else rc=$?; fi
check "missing param: exit 0" "$rc" "0"
check "missing param: still execs" "$out" "EXEC /init.real"
mv "$T/sys/class/block/sda17/uevent.bak" "$T/sys/class/block/sda17/uevent"

exit $fail
