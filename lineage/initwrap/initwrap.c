/*
 * initwrap - tiny PID1 shim prepended to the LineageOS boot image that lives
 * in the a52q (SM7125) `recovery` partition for dual-boot.
 *
 * Samsung ABL stores the "boot recovery" choice in the `param` partition as a
 * 32-bit little-endian word at offset 0: 1 = normal, 2 = recovery. ABL sets 2
 * to boot recovery; only Samsung's stock recovery clears it. Our recovery
 * partition holds LineageOS, so nothing clears it and every reboot returns
 * here instead of the `boot` partition (U-Boot). This shim resets 2 -> 1 once,
 * then hands off to the real Android first-stage init (renamed /init.real) so
 * LineageOS boots normally and the NEXT reboot goes to U-Boot.
 *
 * Safety: it writes ONLY when the word is exactly 02 00 00 00, and only ever
 * writes 01 00 00 00. Any failure is ignored and it always execs on.
 *
 * Build (real):  aarch64-linux-gnu-gcc -static -Os -o init initwrap.c
 * Build (test):  cc -DTEST_ROOT='"/tmp/x"' -Os -o initwrap_test initwrap.c
 *   In test mode nothing is mounted, the device is a plain file at
 *   TEST_ROOT/dev/<DEVNAME>, and it prints the exec target instead of execing.
 */
#define _GNU_SOURCE
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <dirent.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>

#ifdef TEST_ROOT
# define ROOT TEST_ROOT
# define IS_TEST 1
#else
# define ROOT ""
# define IS_TEST 0
#endif

#define BLOCKDIR ROOT "/sys/class/block"
#define TMPNODE  "/__initwrap_param"

static int mounted_sys = 0;

/* Mount sysfs on /sys only if /sys/class/block isn't already there. */
static void ensure_sys(void)
{
#if !IS_TEST
    if (access("/sys/class/block", F_OK) != 0) {
        mkdir("/sys", 0755);
        if (mount("sysfs", "/sys", "sysfs", 0, NULL) == 0)
            mounted_sys = 1;
    }
#endif
}

static void undo_sys(void)
{
#if !IS_TEST
    if (mounted_sys)
        umount("/sys");
#endif
}

/* Open the param block device R/W. Real: mknod a temp node from MAJOR/MINOR
 * (we don't mount /dev, to leave first-stage init's /dev untouched). Test:
 * open the stand-in regular file at TEST_ROOT/dev/<DEVNAME>. */
static int open_param(int major, int minor, const char *devname)
{
#if IS_TEST
    char path[512];
    (void)major; (void)minor;
    snprintf(path, sizeof path, ROOT "/dev/%s", devname);
    return open(path, O_RDWR);
#else
    (void)devname;
    unlink(TMPNODE);
    if (mknod(TMPNODE, S_IFBLK | 0600, makedev(major, minor)) != 0)
        return -1;
    return open(TMPNODE, O_RDWR | O_SYNC);
#endif
}

static void fix_param(void)
{
    DIR *d;
    struct dirent *e;
    char path[512], buf[1024];
    int major = -1, minor = -1, found = 0;
    char devname[128] = {0};

    ensure_sys();

    d = opendir(BLOCKDIR);
    if (!d) { undo_sys(); return; }

    while ((e = readdir(d))) {
        int mj = -1, mn = -1, is_param = 0;
        char dn[128] = {0};
        char *line;
        ssize_t n;
        int fd;

        if (e->d_name[0] == '.')
            continue;
        snprintf(path, sizeof path, "%s/%s/uevent", BLOCKDIR, e->d_name);
        fd = open(path, O_RDONLY);
        if (fd < 0)
            continue;
        n = read(fd, buf, sizeof buf - 1);
        close(fd);
        if (n <= 0)
            continue;
        buf[n] = 0;

        for (line = buf; line && *line; ) {
            char *nl = strchr(line, '\n');
            if (nl) *nl = 0;
            if (!strncmp(line, "MAJOR=", 6))
                mj = atoi(line + 6);
            else if (!strncmp(line, "MINOR=", 6))
                mn = atoi(line + 6);
            else if (!strncmp(line, "DEVNAME=", 8))
                snprintf(dn, sizeof dn, "%s", line + 8);
            else if (!strncmp(line, "PARTNAME=", 9) && !strcmp(line + 9, "param"))
                is_param = 1;
            if (!nl) break;
            line = nl + 1;
        }
        if (is_param && mj >= 0 && mn >= 0) {
            major = mj; minor = mn; found = 1;
            snprintf(devname, sizeof devname, "%s", dn);
            break;
        }
    }
    closedir(d);

    if (found) {
        int fd = open_param(major, minor, devname);
        if (fd >= 0) {
            unsigned char v[4];
            if (read(fd, v, 4) == 4 &&
                v[0] == 2 && v[1] == 0 && v[2] == 0 && v[3] == 0) {
                unsigned char one[4] = {1, 0, 0, 0};
                if (lseek(fd, 0, SEEK_SET) == 0 && write(fd, one, 4) == 4)
                    fsync(fd);
            }
            close(fd);
        }
#if !IS_TEST
        unlink(TMPNODE);
#endif
    }
    undo_sys();
}

int main(int argc, char **argv, char **envp)
{
    (void)argc;
    fix_param();
#if IS_TEST
    printf("EXEC /init.real\n");
    return 0;
#else
    execve("/init.real", argv, envp);
    execve("/system/bin/init", argv, envp);
    for (;;)
        pause();               /* PID1 must never return */
#endif
}
