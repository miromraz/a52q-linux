#!/bin/bash
# Synchronized all-core bursts: 8 openssl workers (NEON/crypto) start together for 1 s,
# then a random idle gap, repeated for $1 s. Max current step on all 8 cores at once.
end=$(( $(date +%s) + $1 )); n=0
while [ $(date +%s) -lt $end ]; do
	openssl speed -multi 8 -seconds 1 -evp aes-128-gcm >/dev/null 2>&1
	sleep 0.$(( RANDOM % 9 + 1 )); n=$((n + 1))
done
echo "bursts $n"
