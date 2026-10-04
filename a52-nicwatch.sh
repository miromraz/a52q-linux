#!/bin/sh
# Keep the A52 USB-net NIC (pinned host MAC) in netns a52 at 172.16.42.2/24, every 2 s,
# so a netconsole listener keeps receiving across phone re-enumerations/hangs
# (ssh's a52-netns ProxyCommand only does this when an ssh session starts).
# Usage: a52-nicwatch.sh &   (stop with kill)
MAC=02:a5:2c:00:00:01
NS=a52
sudo ip netns add "$NS" 2>/dev/null
sudo ip -n "$NS" link set lo up 2>/dev/null
while :; do
	for d in /sys/class/net/*; do
		[ "$(cat "$d/address" 2>/dev/null)" = "$MAC" ] && sudo ip link set "${d##*/}" netns "$NS" 2>/dev/null
	done
	IF=$(sudo ip -n "$NS" -o link show 2>/dev/null | awk -F': ' -v m="$MAC" 'index(tolower($0), m) {print $2; exit}')
	IF=${IF%%@*}
	if [ -n "$IF" ]; then
		sudo ip -n "$NS" addr replace 172.16.42.2/24 dev "$IF" 2>/dev/null
		sudo ip -n "$NS" link set "$IF" up 2>/dev/null
	fi
	sleep 2
done
