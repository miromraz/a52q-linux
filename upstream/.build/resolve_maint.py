#!/usr/bin/env python3
# Resolve a MAINTAINERS cherry-pick conflict: take the 'theirs' additions but
# keep only stanzas whose header line contains one of the KEEP substrings
# (drops phantom sibling stanzas that belong to other series).
import re, sys
keeps = sys.argv[1:]
f = 'MAINTAINERS'; s = open(f).read()
m = re.search(r'<<<<<<< HEAD\n(.*?)=======\n(.*?)>>>>>>> [^\n]*\n', s, re.S)
if not m:
    print("no conflict"); sys.exit(1)
ours, theirs = m.group(1), m.group(2)
# split theirs into stanzas separated by blank lines; keep wanted ones
out = []
for stanza in re.split(r'\n\n', theirs):
    hdr = stanza.strip().split('\n', 1)[0] if stanza.strip() else ''
    if not stanza.strip():
        continue
    if any(k in hdr for k in keeps):
        out.append(stanza.rstrip('\n'))
rep = ours
if out:
    rep += '\n'.join(out) + '\n'
s = s[:m.start()] + rep + s[m.end():]
open(f, 'w').write(s)
print("kept:", keeps)
