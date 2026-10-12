#!/bin/sh
# Keep the phone reachable on Wi-Fi: reconnect after 2 min without the gateway, reboot after 10.
# Needs /etc/protocols (ping fails with "unknown protocol icmp" without it).
sleep 180	# let NetworkManager bring Wi-Fi up after boot
fail=0
while :; do
	gw=$(ip -4 route show default dev wld0 2>/dev/null | awk '{print $3; exit}')
	if [ -n "$gw" ] && ping -c2 -W3 "$gw" >/dev/null 2>&1; then fail=0; else fail=$((fail + 1)); fi
	case $fail in
	4|8|12) echo "wifiwatch: no gateway for $((fail * 30)) s, reconnecting"
		nmcli device connect wld0 ;;
	20) echo "wifiwatch: no gateway for 10 min, rebooting"; systemctl reboot ;;
	esac
	sleep 30
done
