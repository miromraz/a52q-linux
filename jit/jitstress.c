// JIT-style stress: each thread repeatedly writes a tiny function into executable memory,
// flushes D/I caches for it (DC CVAU + IC IVAU via __builtin___clear_cache) and calls it.
// Mode "rwx": one RWX mapping. Mode "wx": V8/SpiderMonkey-style W^X, mprotect RW<->RX per write.
// Usage: jitstress SECONDS THREADS rwx|wx
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>

static double secs; static int wx;

static void *worker(void *arg)
{
	long id = (long)arg, n = 0;
	size_t sz = 1 << 16;
	uint32_t *code = mmap(NULL, sz, PROT_READ | PROT_WRITE | (wx ? 0 : PROT_EXEC),
			      MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	if (code == MAP_FAILED) { perror("mmap"); return NULL; }
	struct timespec t0, t; clock_gettime(CLOCK_MONOTONIC, &t0);
	for (;;) {
		size_t slot = (n * 16) % (sz / 4 - 16);	/* walk the page range like a code allocator */
		if (wx) mprotect(code, sz, PROT_READ | PROT_WRITE);
		uint32_t imm = n & 0xffff;
		code[slot] = 0x52800000 | (imm << 5);	/* mov w0, #imm */
		code[slot + 1] = 0xd65f03c0;		/* ret */
		__builtin___clear_cache((char *)&code[slot], (char *)&code[slot + 2]);
		if (wx) mprotect(code, sz, PROT_READ | PROT_EXEC);
		int r = ((int (*)(void))&code[slot])();
		if (r != (int)imm) { fprintf(stderr, "thread %ld: stale code %d != %u at %ld\n", id, r, imm, n); exit(2); }
		if (!(++n & 0xfff)) {
			clock_gettime(CLOCK_MONOTONIC, &t);
			if (t.tv_sec - t0.tv_sec + (t.tv_nsec - t0.tv_nsec) / 1e9 > secs) break;
		}
	}
	printf("thread %ld: %ld functions\n", id, n);
	return NULL;
}

int main(int argc, char **argv)
{
	if (argc < 4) { fprintf(stderr, "usage: %s SECONDS THREADS rwx|wx\n", argv[0]); return 1; }
	secs = atof(argv[1]); int nt = atoi(argv[2]); wx = !strcmp(argv[3], "wx");
	pthread_t th[64];
	for (long i = 0; i < nt && i < 64; i++) pthread_create(&th[i], NULL, worker, (void *)i);
	for (int i = 0; i < nt && i < 64; i++) pthread_join(th[i], NULL);
	return 0;
}
