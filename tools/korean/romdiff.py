#!/usr/bin/env python3
"""Copy map between two ROMs, in the record format of `vcdiff.py map`.

For a target ROM rebuilt from the same sources (code moved, data inserted),
lists where each run of target bytes is found in the source ROM:
["copy", target offset, length, source offset]. relocmap.py needs this map;
it is what an xdelta from SOURCE to TARGET would record.

  python romdiff.py SOURCE.gba TARGET.gba OUT.json
"""
from __future__ import annotations

import json
import sys

KEY = 8          # bytes per index key
MIN_COPY = 16    # shorter runs are not recorded
RESYNC = 16      # bytes tried with the previous shift after a mismatch


def build_index(src: bytes) -> dict[bytes, int]:
    """KEY-byte keys at 4-aligned source offsets (first occurrence), skipping
    runs of one or two byte values (padding, fills)."""
    index: dict[bytes, int] = {}
    for s in range(0, len(src) - KEY, 4):
        key = src[s:s + KEY]
        if key in index or len(set(key)) < 3:
            continue
        index[key] = s
    return index


def extend(src: bytes, tgt: bytes, s: int, t: int) -> int:
    n = 0
    limit = min(len(src) - s, len(tgt) - t)
    while n + 64 <= limit and src[s + n:s + n + 64] == tgt[t + n:t + n + 64]:
        n += 64
    while n < limit and src[s + n] == tgt[t + n]:
        n += 1
    return n


def copy_map(src: bytes, tgt: bytes) -> list:
    index = build_index(src)
    records, t, shift = [], 0, None
    while t < len(tgt) - KEY:
        best = (0, 0)
        # The previous shift first: code keeps it across a changed pointer.
        if shift is not None:
            for d in range(RESYNC):
                s = t + d + shift
                if 0 <= s < len(src) and src[s] == tgt[t + d]:
                    n = extend(src, tgt, s, t + d)
                    if n >= MIN_COPY:
                        best = (n, d, s)
                        break
        if best[0] == 0:
            for d in range(4):
                s = index.get(tgt[t + d:t + d + KEY])
                if s is None:
                    continue
                n = extend(src, tgt, s, t + d)
                if n >= MIN_COPY and n > best[0]:
                    best = (n, d, s)
        if best[0] == 0:
            t += 4
            continue
        n, d, s = best
        records.append(["copy", t + d, n, s])
        shift = s - (t + d)
        t += d + n
    return records


def main() -> None:
    src_path, tgt_path, out = sys.argv[1:4]
    src, tgt = open(src_path, "rb").read(), open(tgt_path, "rb").read()
    records = copy_map(src, tgt)
    json.dump(records, open(out, "w"))
    print("copies:", len(records), "bytes:", sum(r[2] for r in records), "of", len(tgt))


if __name__ == "__main__":
    main()
