#!/usr/bin/env python3
# Resolve conflicts in the given file by keeping BOTH sides (union of insertions).
# Correct only for independent-insertion conflicts; verified afterwards by a
# tree-diff against the source branch.
import re, sys
f = sys.argv[1]
s = open(f).read()
n = 0
def repl(m):
    global n; n += 1
    return m.group(1) + m.group(2)
s = re.sub(r'<<<<<<< HEAD\n(.*?)=======\n(.*?)>>>>>>> [^\n]*\n', repl, s, flags=re.S)
open(f, 'w').write(s)
print(f"union-resolved {n} hunk(s) in {f}")
sys.exit(0 if n else 2)
