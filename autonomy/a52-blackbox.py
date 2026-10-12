#!/usr/bin/env python3
# Flight recorder for the silent big-core freeze: one of cpu6/cpu7 stops executing without a kernel
# message while the other CPUs live on for ~25 s until the hardware watchdog bites. A second ftrace
# instance records dense events (scheduling, irqs, ipis, syscalls, every idle entry incl. WFI) for cpu6-7 into
# its ring buffer only; nothing is streamed, so it costs next to nothing. One liveness child per big
# core ticks a shared timestamp; when one goes stale the parent, on the little cores, sends the
# dead core's last events and some /proc state to dev over UDP and saves them to /var/log.
# Self-test of the whole path: systemctl kill -s USR1 --kill-whom=main a52-blackbox
# ponytail: timeout logic check: a52-blackbox.py --check
import glob, mmap, os, signal, socket, struct, sys, time

DST = ("192.168.100.105", 6669)
BB = "/sys/kernel/tracing/instances/bb"
BIG = (6, 7)
EVENTS = """sched:sched_switch sched:sched_wakeup irq:irq_handler_entry irq:irq_handler_exit
irq:softirq_entry irq:softirq_exit ipi:ipi_entry ipi:ipi_exit ipi:ipi_raise ipi:ipi_send_cpu
power:cpu_idle power:psci_domain_idle_enter power:psci_domain_idle_exit power:cpu_frequency
timer:hrtimer_expire_entry timer:tick_stop qcom_scm:scm_smc_request qcom_scm:scm_smc_done
rpmh:rpmh_send_msg rpmh:rpmh_tx_done raw_syscalls:sys_enter raw_syscalls:sys_exit
kprobes:bb_fault kprobes:bb_el0sys kprobes:bb_undef kprobes:bb_svc""".split()
# user-space PC at every fault, trapped system instruction, undefined instruction and syscall
# (pt_regs: regs[30] = lr at +240, pc at +256)
KPROBES = """p:bb_fault handle_mm_fault addr=$arg2:x64 flags=$arg3:x32 pc=+256($arg4):x64
p:bb_el0sys do_el0_sys esr=$arg1:x32 pc=+256($arg2):x64
p:bb_undef do_el0_undef pc=+256($arg1):x64 esr=$arg2:x32
p:bb_svc do_el0_svc pc=+256($arg1):x64 lr=+240($arg1):x64""".splitlines()


def rd(path):
    try:
        return open(path, errors="replace").read()
    except OSError as e:
        return f"<{path}: {e}>\n"


def wr(path, text):
    with open(path, "w") as f:
        f.write(text)


def step(fn, timeout):
    """Run fn in a child; give up on it after timeout s (it may hang on the dead CPU)."""
    pid = os.fork()
    if pid == 0:
        try:
            fn()
        finally:
            os._exit(0)
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if os.waitpid(pid, os.WNOHANG)[0]:
            return True
        time.sleep(0.05)
    os.kill(pid, signal.SIGKILL)
    return False


def section(text, start, stop):
    """Lines from the one starting with `start` up to the next one starting with `stop`."""
    out, on = [], False
    for line in text.splitlines():
        if line.startswith(start):
            on = True
        elif on and line.startswith(stop):
            break
        if on:
            out.append(line)
    return "\n".join(out) + "\n"


def sources(dead):
    """(name, timeout, reader) in the order they matter; each reader returns text."""
    other = BIG[0] if dead == BIG[1] else BIG[1]
    tail = lambda cpu, n: "".join(rd(f"{BB}/per_cpu/cpu{cpu}/trace").splitlines(True)[-n:])
    idle = lambda: "".join(f"{p} {rd(p)}" for p in sorted(
        glob.glob(f"/sys/devices/system/cpu/cpu{dead}/cpuidle/state*/[nutr]*")))
    freq = lambda: "".join(f"{p} {rd(p)}" for p in sorted(
        glob.glob("/sys/devices/system/cpu/cpufreq/policy*/scaling_cur_freq")))
    return [
        (f"trace-cpu{dead}", 12, lambda: tail(dead, 12000)),
        (f"trace-cpu{other}", 5, lambda: tail(other, 2000)),
        ("interrupts-1", 3, lambda: rd("/proc/interrupts")),
        ("interrupts-2", 4, lambda: (time.sleep(1), rd("/proc/interrupts"))[1]),
        ("softirqs", 3, lambda: rd("/proc/softirqs")),
        ("cpuidle", 3, idle),
        ("cpufreq", 3, freq),
        ("timer_list", 5, lambda: section(rd("/proc/timer_list"), f"cpu: {dead}", "cpu: ")),
        ("sched_debug", 5, lambda: section(rd("/sys/kernel/debug/sched/debug"), f"cpu#{dead}", "cpu#")),
    ]


def dump(dead, tag):
    wr("/dev/kmsg", f"BLACKBOX cpu{dead} silent ({tag}) at {time.monotonic():.2f}\n")
    boot = rd("/proc/sys/kernel/random/boot_id")[:8]
    save = f"/var/log/a52-blackbox-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}.txt"

    def send(name, reader):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        pre = f"bb {boot} {tag} cpu{dead} {name}: ".encode()
        text = reader()
        try:
            for i, line in enumerate(text.encode().splitlines()):
                s.sendto((pre + line)[:1400] + b"\n", DST)
                if i % 20 == 19:
                    time.sleep(0.001)  # pace: Wi-Fi drops a burst of thousands of datagrams
        except OSError:
            pass  # no route (Wi-Fi gone): still write the local copy below
        with open(save, "a") as f:  # after the network copy: the disk may be the thing that hangs
            f.write(f"=== {name}\n{text}")
            f.flush()
            os.fsync(f.fileno())

    for name, timeout, reader in sources(dead):
        step(lambda: send(name, reader), timeout)
    # all-CPU backtrace into the kernel log (netconsole): shows whether the silent core answers
    step(lambda: wr("/proc/sysrq-trigger", "l"), 12)
    for old in sorted(glob.glob("/var/log/a52-blackbox-*.txt"))[:-5]:
        os.remove(old)


def recorder():
    os.makedirs(BB, exist_ok=True)
    wr(f"{BB}/tracing_on", "0")
    wr(f"{BB}/tracing_cpumask", "%x" % sum(1 << c for c in BIG))
    wr(f"{BB}/buffer_size_kb", "4096")
    for probe in KPROBES:
        try:  # raw O_APPEND write: open(..., "a") seeks, which tracefs refuses
            fd = os.open("/sys/kernel/tracing/kprobe_events", os.O_WRONLY | os.O_APPEND)
            os.write(fd, (probe + "\n").encode())
            os.close(fd)
        except OSError:
            pass  # already defined (service restart) or symbol not probeable: carry on without it
    have = set(rd("/sys/kernel/tracing/available_events").split())
    wr(f"{BB}/set_event", "\n".join(e for e in EVENTS if e in have) + "\n")
    wr(f"{BB}/tracing_on", "1")


def liveness(mm, slot, cpu):
    signal.signal(signal.SIGUSR1, signal.SIG_IGN)
    os.sched_setaffinity(0, {cpu})
    os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(1))  # ordinary load must not starve it
    while True:
        struct.pack_into("d", mm, slot * 8, time.monotonic())
        time.sleep(0.1)


def main():
    recorder()
    mm = mmap.mmap(-1, 8 * len(BIG))  # anonymous + shared: survives fork
    kids = []
    for slot, cpu in enumerate(BIG):
        struct.pack_into("d", mm, slot * 8, time.monotonic())
        pid = os.fork()
        if pid == 0:
            liveness(mm, slot, cpu)
        kids.append(pid)
    os.sched_setaffinity(0, {0, 1, 2, 3})
    selftest = []
    signal.signal(signal.SIGUSR1, lambda *_: selftest.append(1))
    age = lambda slot: time.monotonic() - struct.unpack_from("d", mm, slot * 8)[0]
    while True:
        time.sleep(0.5)
        if selftest:
            os.kill(kids[-1], signal.SIGSTOP)  # pretend the last big core died
        for slot, cpu in enumerate(BIG):
            if age(slot) > 2.0 and (time.sleep(0.5), age(slot))[1] > 2.5:
                dump(cpu, "selftest" if selftest else "dead")
                if not selftest:
                    signal.pause()  # one dump per boot; the watchdog takes it from here
                os.kill(kids[-1], signal.SIGCONT)
                selftest.clear()
                time.sleep(1)


def check():
    t = time.monotonic()
    assert step(lambda: time.sleep(30), 0.3) is False and time.monotonic() - t < 1, "timeout not enforced"
    assert step(lambda: None, 2) is True, "quick step not reported as done"
    assert section("cpu: 5\na\ncpu: 6\nb\nc\ncpu: 7\nd\n", "cpu: 6", "cpu: ") == "cpu: 6\nb\nc\n"
    print("ok")


if __name__ == "__main__":
    check() if sys.argv[1:] == ["--check"] else main()
