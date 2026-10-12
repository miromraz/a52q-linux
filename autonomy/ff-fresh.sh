#!/bin/sh
# Firefox with a brand-new profile and HOME on tmpfs: first-run work on every launch (the freeze
# reproducer). Optional variant as $1: little | swgl | nojit | warmcache.
d=$(mktemp -d /tmp/ffhome.XXXXXX); export HOME=$d
p=$d/prof; mkdir -p $p
case "$1" in
little) exec taskset -c 0-5 firefox-esr --profile $p ;;
swgl) echo "user_pref(\"gfx.webrender.software\", true);" > $p/user.js
	LIBGL_ALWAYS_SOFTWARE=1 exec firefox-esr --profile $p ;;
nojit) for k in baselinejit ion blinterp wasm native_regexp; do
		echo "user_pref(\"javascript.options.$k\", false);"; done > $p/user.js
	exec firefox-esr --profile $p ;;
warmcache) export XDG_CACHE_HOME=/var/tmp/ffcache; mkdir -p $XDG_CACHE_HOME
	exec firefox-esr --profile $p ;;
*) exec firefox-esr --profile $p ;;
esac
