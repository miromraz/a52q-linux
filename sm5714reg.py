#!/usr/bin/env python3
# Read/write one SM5714 charger register (i2c-4 addr 0x49) via i2c-dev (driver-bound, so
# I2C_SLAVE_FORCE). Only use registers the in-tree driver itself programs.
# Usage: sm5714reg.py REG [VALUE]   (hex ok)
import fcntl, os, sys
fd = os.open("/dev/i2c-4", os.O_RDWR); fcntl.ioctl(fd, 0x0706, 0x49)   # I2C_SLAVE_FORCE
reg = int(sys.argv[1], 0)
if len(sys.argv) > 2:
    os.write(fd, bytes([reg, int(sys.argv[2], 0)]))
os.write(fd, bytes([reg])); print(f"{reg:#04x} = {os.read(fd, 1)[0]:#04x}")
