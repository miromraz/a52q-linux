#!/bin/bash
# Camera regression test on the a52q: capture on every camera, kill a capture mid-stream,
# capture on every camera again, then report SMMU faults / camnoc WARNs. Runs on the phone
# via ssh as a single script so a dropped ssh session cannot kill a capture by accident.
H=${H:-a52r}
timeout 600 ssh $H 'bash -s' <<'EOF'
cd /var/tmp
n=$(cam -l 2>/dev/null | grep -c "^[0-9]*:")
round() {
	for c in $(seq 1 $n); do
		rm -f cs-*
		timeout 40 cam -c$c --capture=3 --file=cs-#.bin >/dev/null 2>&1
		printf "cam%s=%s " $c $(ls cs-* 2>/dev/null | wc -l)
	done
	rm -f cs-*; echo
}
dmesg -C
echo "cameras $n"; echo -n "before: "; round
cam -c1 --capture=200 --file=/dev/null >/dev/null 2>&1 & p=$!
sleep 3; kill -TERM $p; wait $p 2>/dev/null; echo "killed capture mid-stream"
echo -n "after:  "; round
echo "smmu_faults $(dmesg | grep -c 'context fault') camnoc_warn $(dmesg | grep -c 'stuck at .on')"
EOF
