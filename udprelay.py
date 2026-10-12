#!/usr/bin/env python3
# stdin -> UDP, one datagram per line, unbuffered, so the last lines before a hard freeze
# already left the phone. Usage: ... | udprelay.py HOST PORT
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); dst = (sys.argv[1], int(sys.argv[2]))
for line in sys.stdin.buffer:
    s.sendto(line[:1400], dst)
