#!/bin/sh
# Churn the kernel objects browser sandboxes create: user/pid/net/ipc namespaces (+ loopback up)
# and seccomp filters, 4 parallel loops for $1 seconds. Run as root.
end=$(( $(date +%s) + $1 ))
loop() {
	n=0
	while [ $(date +%s) -lt $end ]; do
		unshare -Upnif --mount-proc -r sh -c 'ip link set lo up 2>/dev/null; true'
		n=$((n + 1))
	done
	echo "ns-loop $1: $n"
}
for i in 1 2 3 4; do loop $i & done
wait
