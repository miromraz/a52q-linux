#!/bin/bash
# Generate format-patch + to-cc.txt + checks.txt per series, from the main repo.
# Runs read-only on refs; swaps MAINTAINERS to base for get_maintainer, restores it.
set -u
REPO=/home/realni/src/linux-upstream
UP=/home/realni/linux-a52q/upstream
BASE=72d3fcf802c4
cd "$REPO" || exit 1

# name:base  (base BASE unless dependency)
series="
watchdog:$BASE
ath10k:$BASE
serial-geni:$BASE
regulator-s2mpb03:$BASE
power-supply-sm5714:$BASE
typec-sm5714:$BASE
nfc-s3fwrn5:$BASE
input-fts5cu56a:$BASE
drm-panel-s6e3fc3:$BASE
drm-msm-a618:$BASE
asoc-tas2562:$BASE
pinctrl-qcom-lpass:$BASE
soc-qcom-smp2p:$BASE
soc-qcom-pd-mapper:$BASE
firmware-qcom-tzmem:$BASE
media-ak7374:$BASE
media-ois-mcu:$BASE
media-sensor-imx616:$BASE
media-sensor-s5k3l6xx:$BASE
media-sensor-s5kgw1p:$BASE
media-sensor-gc5035:$BASE
media-camss-fixes:$BASE
media-camss-cphy:$BASE
media-camss-sc7180:up/media-camss-cphy
"

# 1) format-patch for every series (+ strip cherry-pick trailers)
for e in $series; do
  name=${e%%:*}; base=${e#*:}; br=up/$name; dir=$UP/$name
  git rev-parse -q --verify "$br" >/dev/null || { echo "MISSING $br"; continue; }
  rm -rf "$dir"; mkdir -p "$dir"
  n=$(git rev-list --count "$base..$br")
  cl=""; [ "$n" -gt 1 ] && cl="--cover-letter"
  git format-patch -q -v1 $cl --base="$base" -o "$dir" "$base..$br" >/dev/null
  # strip internal cherry-pick trailers
  sed -i '/^(cherry picked from commit [0-9a-f]\{40\})$/d' "$dir"/*.patch
  # also drop the now-empty trailing blank the strip may leave before ---? leave as-is
  echo "FMT $name: $n patch(es)"
done

# 2) get_maintainer with BASE MAINTAINERS (swap once)
cp MAINTAINERS /tmp/claude-1000/M.realbak
git show "$BASE":MAINTAINERS > MAINTAINERS
for e in $series; do
  name=${e%%:*}; dir=$UP/$name
  [ -d "$dir" ] || continue
  pats=$(ls "$dir"/[0-9]*.patch 2>/dev/null | grep -v '0000-cover')
  [ -z "$pats" ] && pats=$(ls "$dir"/*.patch)
  perl scripts/get_maintainer.pl --no-git --no-rolestats $pats 2>/dev/null | sort -u > "$dir/to-cc.txt"
done
git checkout -q -- MAINTAINERS
git diff --quiet -- MAINTAINERS && echo "MAINTAINERS restored OK" || echo "WARN MAINTAINERS dirty"

# 3) checkpatch --strict over whole series
for e in $series; do
  name=${e%%:*}; dir=$UP/$name
  [ -d "$dir" ] || continue
  pats=$(ls "$dir"/[0-9]*.patch 2>/dev/null | grep -v '0000-cover')
  [ -z "$pats" ] && pats=$(ls "$dir"/*.patch)
  { echo "# checkpatch.pl --strict  ($name)";
    perl scripts/checkpatch.pl --strict $pats 2>&1; } > "$dir/checks.txt"
  tot=$(grep -h '^total:' "$dir/checks.txt" | tail -1)
  errs=$(grep -hc '^ERROR' "$dir/checks.txt" 2>/dev/null || echo 0)
  printf 'CHK %-24s %s | ERRORs=%s\n' "$name" "${tot:-no-total}" "$errs"
done
echo DONE
