#!/bin/bash
# Resumable branch assembler. Creates up/<name> from manifest in $WT.
# Skips a series whose branch already exists (reboot-safe).
set -u
REPO=/home/realni/src/linux-upstream
WT=/home/realni/src/wt-up
BASE=72d3fcf802c4
MAN=/home/realni/linux-a52q/upstream/.build/series.manifest
cd "$WT" || exit 1
git -C "$REPO" rev-parse --verify -q "$BASE" >/dev/null || { echo "no BASE"; exit 1; }

fail=0
while IFS='|' read -r name base commits; do
  name="${name// /}"; [ -z "$name" ] && continue; [ "${name:0:1}" = "#" ] && continue
  base="${base// /}"; [ "$base" = "BASE" ] && base="$BASE"
  br="up/$name"
  if git -C "$REPO" rev-parse --verify -q "$br" >/dev/null; then
    echo "SKIP $br (exists)"; continue
  fi
  echo "=== $br  base=$base ==="
  git checkout -q -B "$br" "$base" || { echo "FAIL checkout $br"; fail=1; continue; }
  ok=1
  for tok in $commits; do
    h="${tok%%^*}"; rest="${tok#"$h"}"
    if ! git cherry-pick -x "$h" >/tmp/cp.log 2>&1; then
      echo "FAIL cherry-pick $h into $br:"; sed 's/^/    /' /tmp/cp.log | head; git cherry-pick --abort 2>/dev/null; ok=0; break
    fi
    # fold fixups: rest like ^aaa^bbb
    while [ -n "$rest" ]; do
      rest="${rest#^}"; fx="${rest%%^*}"; rest="${rest#"$fx"}"
      [ -z "$fx" ] && break
      if ! git cherry-pick -n "$fx" >/tmp/fx.log 2>&1; then
        echo "FAIL fold $fx into $h ($br):"; sed 's/^/    /' /tmp/fx.log|head; git cherry-pick --abort 2>/dev/null; git reset -q --hard; ok=0; break
      fi
      git commit -q --amend --no-edit || { ok=0; break; }
    done
    [ "$ok" = 0 ] && break
  done
  if [ "$ok" = 1 ]; then
    n=$(git -C "$REPO" rev-list --count "$base..$br")
    echo "OK $br : $n commits"
  else
    git branch -D "$br" 2>/dev/null; fail=1
  fi
done < "$MAN"
exit $fail
