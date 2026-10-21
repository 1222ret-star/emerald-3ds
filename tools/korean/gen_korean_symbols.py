#!/usr/bin/env python3
"""Write tools/locales/korean-symbols.s.gz: the pret symbols at their Korean ROM
addresses (from relocmap.py's symbols_kor.tsv), in the format of the other
languages' reference symbols. Names, addresses and sizes only.

  python gen_korean_symbols.py SYMBOLS_KOR.tsv OUT.s.gz
"""
import gzip
import sys

CODE_END = 0x081DB67C  # USA .text end: what lies below is code

rows = [line.rstrip("\n").split("\t") for line in open(sys.argv[1], encoding="utf-8")][1:]
seen = set()
out = [".syntax unified"]
for name, kind, size, usa, kor, status in sorted(rows, key=lambda r: r[0]):
    if not kor or status == "unknown" or name in seen or not name.replace("_", "a").replace(".", "a").isalnum():
        continue
    seen.add(name)
    function = int(usa, 16) < CODE_END
    out += [".global %s" % name,
            ".type %s, %s" % (name, "%function" if function else "%object"),
            ".equ %s, %d" % (name, int(kor, 16)),
            ".size %s, %d" % (name, int(size))]
open(sys.argv[2], "wb").write(gzip.compress(("\n".join(out) + "\n").encode(), 9))
print(len(seen), "symbols")
