uptime
# watchdog mode that is known to reset a dead kernel (kernel-petting mode does not)
cp /etc/systemd/zz-a52-wdog.conf.off /etc/systemd/system.conf.d/zz-a52-wdog.conf 2>/dev/null
systemctl daemon-reexec; systemctl show -p RuntimeWatchdogUSec
grep -E 'Broadcast device|^Clock Event Device|event_handler|mode:' /proc/timer_list | head -20
grep -iE 'arch_mem|arch_timer|timer' /proc/interrupts | head
dmesg | grep -iE 'arch_timer|clocksource|broadcast|mmio timer|psci' | head -20
cat /sys/devices/system/clocksource/clocksource0/current_clocksource
