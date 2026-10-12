// JIT stress shaped like SpiderMonkey/V8 code allocation, to reproduce the Firefox first-run freeze
// (flight-recorder dumps end right after the dying thread's mprotect(PROT_READ|PROT_EXEC)):
// threads of ONE process share one big code region; each takes fresh pages from it,
// mprotect(RW) -> write functions -> mprotect(RX) -> flush like vixl/V8 (dc civac, dsb, ic ivau,
// dsb, isb) -> call them, re-patches older pages now and then, and decommits (MADV_DONTNEED) spans.
// Each thread patches only its own slice of the region; what they share is the address space
// (mmap lock, VMA splits/merges, TLB invalidation broadcasts while the others execute JIT code).
// Usage: jitstress2 SECONDS THREADS civac|cvau|none [REGION_MB]
// Build (laptop): aarch64-linux-gnu-gcc -O2 -static -pthread -o jitstress2 jitstress2.c
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>

#define PAGE 4096UL
static double secs;
static int flushmode;			/* 0 none, 1 cvau, 2 civac */
static char *region;
static size_t npages, slice_pages;
static atomic_long done_fns;

static void flush(char *start, char *end)
{
	if (!flushmode)
		return;
	for (char *p = start; p < end; p += 64) {
		if (flushmode == 2)
			__asm__ volatile("dc civac, %0" : : "r"(p) : "memory");
		else
			__asm__ volatile("dc cvau, %0" : : "r"(p) : "memory");
	}
	__asm__ volatile("dsb ish");
	for (char *p = start; p < end; p += 64)
		__asm__ volatile("ic ivau, %0" : : "r"(p) : "memory");
	__asm__ volatile("dsb ish\n isb");
}

static double now(void)
{
	struct timespec t;
	clock_gettime(CLOCK_MONOTONIC, &t);
	return t.tv_sec + t.tv_nsec / 1e9;
}

/* fill [p, p + n pages) with `mov w0, #imm; ret` pairs, the SpiderMonkey way */
static void emit(char *p, size_t n, uint32_t imm)
{
	mprotect(p, n * PAGE, PROT_READ | PROT_WRITE);
	for (uint32_t *c = (uint32_t *)p; (char *)c < p + n * PAGE; c += 2) {
		c[0] = 0x52800000 | (imm << 5);
		c[1] = 0xd65f03c0;
	}
	mprotect(p, n * PAGE, PROT_READ | PROT_EXEC);
	flush(p, p + n * PAGE);
}

static void *worker(void *arg)
{
	long id = (long)arg;
	unsigned seed = id * 7919 + 1;
	char *slice = region + id * slice_pages * PAGE;	/* only this thread patches its slice */
	size_t bump = 0;
	char *mine[64] = { 0 };		/* recent spans of this thread: re-patched and called */
	size_t len[64] = { 0 };
	double end = now() + secs;
	long n = 0;

	while (now() < end) {
		int s = rand_r(&seed) % 64;

		if (!mine[s] || rand_r(&seed) % 4) {		/* fresh span of 1-4 pages */
			if (mine[s] && rand_r(&seed) % 2)	/* decommit the old one first */
				madvise(mine[s], len[s] * PAGE, MADV_DONTNEED);
			if (bump + 4 > slice_pages) {		/* wrapped: forget spans about to be reused */
				memset(mine, 0, sizeof(mine));
				bump = 0;
			}
			len[s] = 1 + rand_r(&seed) % 4;
			mine[s] = slice + bump * PAGE;
			bump += len[s];
		}
		emit(mine[s], len[s], rand_r(&seed) & 0xffff);	/* fresh code, or a re-patch */
		for (int k = 0; k < 8; k++) {			/* run code from several of my spans */
			int j = rand_r(&seed) % 64;
			if (mine[j])
				((int (*)(void))(mine[j] + (rand_r(&seed) % (len[j] * PAGE / 8)) * 8))();
		}
		n++;
	}
	atomic_fetch_add(&done_fns, n);
	return NULL;
}

int main(int argc, char **argv)
{
	if (argc < 4) {
		fprintf(stderr, "usage: %s SECONDS THREADS civac|cvau|none [REGION_MB]\n", argv[0]);
		return 1;
	}
	secs = atof(argv[1]);
	int nt = atoi(argv[2]);
	flushmode = !strcmp(argv[3], "civac") ? 2 : !strcmp(argv[3], "cvau") ? 1 : 0;
	npages = (argc > 4 ? atol(argv[4]) : 256) * 256UL;
	/* reserve like a JIT: one big region, committed lazily, executable by default */
	region = mmap(NULL, npages * PAGE, PROT_READ | PROT_EXEC, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	if (region == MAP_FAILED) {
		perror("mmap");
		return 1;
	}
	pthread_t th[64];
	if (nt > 64)
		nt = 64;
	slice_pages = npages / nt;
	for (long i = 0; i < nt; i++)
		pthread_create(&th[i], NULL, worker, (void *)i);
	for (int i = 0; i < nt; i++)
		pthread_join(th[i], NULL);
	printf("%ld spans emitted\n", atomic_load(&done_fns));
	return 0;
}
