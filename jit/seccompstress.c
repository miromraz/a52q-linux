// Browser-sandbox-style seccomp churn: workers fork children that install a ~100-insn
// seccomp-bpf filter (kernel JITs it), make some syscalls through it, then exit.
// Usage: seccompstress SECONDS WORKERS
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static void child(void)
{
	struct sock_filter f[128]; int n = 0;
	f[n++] = (struct sock_filter)BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr));
	for (int nr = 400; nr < 460; nr++)	/* unused syscall numbers -> ERRNO, like a denylist */
		f[n++] = (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, nr, 0, 1),
		f[n++] = (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | 1);
	f[n++] = (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW);
	struct sock_fprog prog = { .len = n, .filter = f };
	if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) || syscall(SYS_seccomp, SECCOMP_SET_MODE_FILTER, 0, &prog)) _exit(3);
	for (int i = 0; i < 1000; i++) getppid();
	_exit(0);
}

int main(int argc, char **argv)
{
	double secs = atof(argv[1]); int nw = atoi(argv[2]);
	for (int w = 0; w < nw; w++) if (!fork()) {
		long n = 0; time_t end = time(NULL) + (time_t)secs;
		while (time(NULL) < end) {
			pid_t p = fork(); if (!p) child();
			int st; waitpid(p, &st, 0);
			if (!WIFEXITED(st) || WEXITSTATUS(st)) { fprintf(stderr, "child failed %d\n", st); exit(1); }
			n++;
		}
		printf("worker %d: %ld filtered children\n", w, n); exit(0);
	}
	while (wait(NULL) > 0) ;
	return 0;
}
