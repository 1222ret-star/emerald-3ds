#!/usr/bin/env python3
"""Map every pret symbol of the clean BPEE ROM to the Korean ROM.

Inputs: pokeemerald.sym (pret `symbols` branch), the xdelta change map written by
`vcdiff.py map`, and both ROMs.

1. Locating. A rebuilt ROM moves code, so COPY records split at every BL and
   literal pool. Each symbol's new address is therefore voted for by
   - the pointers that reference it: a USA word holding the symbol's address is
     mapped to the Korean ROM by the COPY shift around it, and the Korean word
     found there names the new address;
   - the dominant COPY shift over the symbol's own bytes.
2. Comparing. The bytes are compared with BL pairs and ROM/RAM pointers masked
   out (both are expected to differ after relocation).

Status: same (unchanged, same address), moved (unchanged elsewhere),
modified (found, contents differ), unknown (no location found).
Korean bytes not explained by a source COPY are listed as new regions.

  python relocmap.py SYM MAP.json USA.gba KOR.gba OUTDIR [OVERRIDES.json]
"""
from __future__ import annotations

import bisect
import difflib
import itertools
import collections
import json
import os
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import script_cmds  # noqa: E402

ROM = 0x08000000
# pret tree for the script command layouts (asm/macros/event.inc).
SCRIPT_TREE = Path(__file__).resolve().parents[2] / "build/upstream"
CODE_END = 0x1DB67C  # end of .text in the USA ROM; data follows


def is_pointer(word: int) -> bool:
    return ROM <= word < ROM + 0x1000000 or 0x02000000 <= word < 0x02040000 or 0x03000000 <= word < 0x03008000


def masked(data: bytes, start: int, size: int, script: bool = False) -> bytes:
    """Bytes with Thumb BL pairs and aligned pointer words blanked."""
    out = bytearray(data[start:start + size])
    i = start - start % 2
    while i + 4 <= start + size:
        hi, lo = struct.unpack_from("<HH", data, i)
        if hi & 0xF800 == 0xF000 and lo & 0xF800 in (0xF800, 0xE800):
            for k in range(4):
                if 0 <= i + k - start < size:
                    out[i + k - start] = 0
            i += 4
            continue
        i += 2
    for i in range(start + (-start) % 4, start + size - 3, 4):
        if is_pointer(struct.unpack_from("<I", data, i)[0]):
            out[i - start:i - start + 4] = b"\0\0\0\0"
    if script:
        # Event scripts hold unaligned ROM pointers.
        for i in range(start, start + size - 3):
            if data[i + 3] in (0x08, 0x09):
                out[i - start:i - start + 4] = b"\0\0\0\0"
    return bytes(out)


def is_text(name: str) -> bool:
    return name.startswith(("gText_", "sText_")) or name.endswith("Text") or "_Text_" in name


def stale_vote(usa: bytes, kor: bytes, off: int, size: int, new: int) -> bool:
    """A vote for the symbol's own USA address whose bytes are not there in
    the Korean ROM: an unchanged word that only looks like a pointer (inside
    graphics, say), not a reference to a symbol that stayed put."""
    if new != off:
        return False
    script = off >= CODE_END
    return new + size > len(kor) or masked(usa, off, size, script) != masked(kor, new, size, script)


def main() -> None:
    sym_path, map_path, usa_path, kor_path, out = sys.argv[1:6]
    # Optional: {symbol: Korean address} for what matching cannot find; the
    # pairing passes then follow the pointers these hold.
    overrides = json.load(open(sys.argv[6])) if len(sys.argv) > 6 else {}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    usa, kor = Path(usa_path).read_bytes(), Path(kor_path).read_bytes()
    records = json.load(open(map_path))
    copies = sorted((r[3], r[2], r[1] - r[3]) for r in records if r[0] == "copy")
    starts = [c[0] for c in copies]

    def shift_near(off: int) -> int | None:
        """COPY shift of the copy covering off, else of the closest one before it (64 bytes)."""
        i = bisect.bisect_right(starts, off) - 1
        while i >= 0:
            src, n, shift = copies[i]
            if src + n > off - 64:
                if src <= off < src + n or src + n <= off:
                    return shift
            if src + n <= off - 64:
                break
            i -= 1
        return None

    symbols = []
    for line in open(sym_path):
        addr, kind, size, name = line.split()[:4]
        addr, size = int(addr, 16), int(size, 16)
        if ROM <= addr < ROM + len(usa):
            symbols.append((addr - ROM, size, kind, name))
    symbols.sort()
    # Assembly labels (scripts, map texts) have no size: they run to the next symbol.
    addresses = sorted({s[0] for s in symbols})
    for n, (off, size, kind, name) in enumerate(symbols):
        if size == 0:
            i = bisect.bisect_right(addresses, off)
            end = addresses[i] if i < len(addresses) else len(usa)
            symbols[n] = (off, max(1, min(end - off, 0x4000)), kind, name)
    by_addr = {}
    for n, (off, *_rest) in enumerate(symbols):
        by_addr.setdefault(off, n)
    # RELOC_TRACE=name1,name2: print where each pass leaves these symbols.
    traced = [n for n, s in enumerate(symbols) if s[3] in os.environ.get("RELOC_TRACE", "").split(",")]

    def trace(stage: str) -> None:
        for n in traced:
            print("trace %-10s %s %s %s" % (stage, symbols[n][3], states[n],
                                             "-" if locs[n] is None else "0x%08X" % (locs[n] + ROM)))

    votes = [collections.Counter() for _ in symbols]
    # Pointer votes. Every byte offset: event scripts hold unaligned pointers.
    words = memoryview(usa)
    for p in range(0, len(usa) - 3):
        if words[p + 3] != 0x08:
            continue
        word = struct.unpack_from("<I", usa, p)[0]
        thumb = 0
        n = by_addr.get(word - ROM)
        if n is None and word & 1:
            n, thumb = by_addr.get(word - 1 - ROM), 1  # Thumb function pointer
        if n is None:
            continue
        shift = shift_near(p)
        if shift is None or not 0 <= p + shift <= len(kor) - 4:
            continue
        new = struct.unpack_from("<I", kor, p + shift)[0] - thumb
        if ROM <= new < ROM + len(kor):
            votes[n][new - ROM] += 4
    # Own-bytes votes.
    for n, (off, size, kind, name) in enumerate(symbols):
        i = max(0, bisect.bisect_right(starts, off) - 1)
        while i < len(copies) and copies[i][0] < off + size:
            src, length, shift = copies[i]
            overlap = min(src + length, off + size) - max(src, off)
            if overlap >= 8:
                votes[n][off + shift] += overlap // 8
            i += 1

    locs: list[int | None] = []
    states: list[str] = []
    for n, (off, size, kind, name) in enumerate(symbols):
        align = 4 if off % 4 == 0 else 2 if off % 2 == 0 else 1
        candidates = [a for a, _ in votes[n].most_common(8)
                      if a % align == 0 and 0 <= a <= len(kor) - size]
        want = masked(usa, off, size, off >= CODE_END)
        new = next((a for a in candidates if masked(kor, a, size, off >= CODE_END) == want), None)
        if new is None and size >= 24 and len(set(usa[off:off + size])) > 4:
            # Unreferenced data: look for the identical bytes.
            hit = kor.find(usa[off:off + size])
            if hit >= 0 and hit % align == 0 and kor.find(usa[off:off + size], hit + 1) < 0:
                new = hit
        if new is not None:
            status = "same" if new == off else "moved"
        elif candidates:
            new, status = candidates[0], "modified"
        else:
            new, status = None, "unknown"
        locs.append(new)
        states.append(status)

    for n, (off, size, kind, name) in enumerate(symbols):
        if name in overrides:
            new = int(overrides[name], 16) - ROM
            locs[n] = new
            same_bytes = masked(usa, off, size, off >= CODE_END) == masked(kor, new, size, off >= CODE_END)
            states[n] = ("same" if new == off else "moved") if same_bytes else "paired"

    trace("votes")
    # Pointer pairing: a symbol found with identical (pointer-masked) contents
    # holds the same pointers at the same offsets, so each USA pointer in it
    # names the Korean address of its target. Repeat while new symbols match.
    frontier = [n for n, s in enumerate(states) if s in ("same", "moved")]
    for _ in range(6):
        paired = collections.defaultdict(collections.Counter)
        for n in frontier:
            off, size = symbols[n][0], symbols[n][1]
            base = locs[n]
            for i in range(size - 3):
                if usa[off + i + 3] not in (0x08, 0x09):
                    continue
                word = struct.unpack_from("<I", usa, off + i)[0]
                thumb = 0
                target = by_addr.get(word - ROM)
                if target is None and word & 1:
                    target, thumb = by_addr.get(word - 1 - ROM), 1
                if target is None:
                    continue
                new = struct.unpack_from("<I", kor, base + i)[0] - thumb - ROM
                if 0 <= new < len(kor):
                    if not stale_vote(usa, kor, symbols[target][0], symbols[target][1], new):
                        paired[target][new] += 1
        frontier = []
        for target, counter in paired.items():
            new, count = counter.most_common(1)[0]
            if count * 2 <= sum(counter.values()):
                continue  # no clear majority
            if new == locs[target] and states[target] in ("same", "moved", "paired"):
                continue  # already known
            # Pairing outranks a content match: the patched ROM keeps unused
            # copies of original data (English texts) next to the ones it uses.
            off, size = symbols[target][0], symbols[target][1]
            locs[target] = new
            if new + size <= len(kor) and masked(usa, off, size, off >= CODE_END) == masked(kor, new, size, off >= CODE_END):
                states[target] = "same" if new == off else "moved"
                frontier.append(target)
            else:
                states[target] = "paired"
        if not frontier:
            break

    trace("pairing")
    # Ordered pairing: a container whose contents changed (a re-laid-out
    # table, a rewritten function, an edited script) still lists its pointers
    # in the same order. Pair the n-th USA pointer with the n-th Korean one when
    # both lists are as long and every pointer whose target is already located
    # agrees.
    def pointers(data: bytes, start: int, size: int, script: bool) -> list[int]:
        found = []
        if script:
            i = start
            while i < start + size - 3:
                if data[i + 3] in (0x08, 0x09):
                    found.append(struct.unpack_from("<I", data, i)[0])
                    i += 4
                else:
                    i += 1
        else:
            for i in range(start + (-start) % 4, start + size - 3, 4):
                word = struct.unpack_from("<I", data, i)[0]
                if ROM <= word < ROM + len(data):
                    found.append(word)
        return found

    def target_of(word: int) -> tuple[int | None, int]:
        n = by_addr.get(word - ROM)
        if n is None and word & 1:
            return by_addr.get(word - 1 - ROM), 1
        return n, 0

    # Tables of structs the Korean ROM re-laid out: pair pointers row by row.
    # (symbol, USA stride, Korean stride). Only at a confirmed table address:
    # rows read from a guessed one pair every pointer with a wrong target.
    relaid = [("gPokedexEntries", 32, 36), ("gItems", 44, 48), ("gDecorations", 32, 32), ("gEasyChatGroups", 8, 8),
              ("gBerries", 28, 28)]
    # Easy Chat word groups ({text, sort index, enabled}): translated words
    # move away from their table, which then has nothing left to match.
    relaid += [(s[3], 12, 12) for s in symbols if s[3].startswith("gEasyChatGroup_") and s[1] % 12 == 0
               and ROM <= struct.unpack_from("<I", usa, s[0])[0] < ROM + len(usa)]

    def pair_relaid() -> None:
        for table, usa_stride, kor_stride in relaid:
            n = next(i for i, s in enumerate(symbols) if s[3] == table)
            off, size = symbols[n][0], symbols[n][1]
            if locs[n] is None or states[n] not in ("same", "moved", "paired"):
                continue
            rowwise = collections.defaultdict(collections.Counter)
            for row in range(size // usa_stride):
                usa_ptrs = pointers(usa, off + row * usa_stride, usa_stride, False)
                kor_ptrs = pointers(kor, locs[n] + row * kor_stride, kor_stride, False)
                if len(usa_ptrs) != len(kor_ptrs):
                    continue
                for usa_word, kor_word in zip(usa_ptrs, kor_ptrs):
                    target, thumb = target_of(usa_word)
                    if target is not None:
                        rowwise[target][kor_word - thumb - ROM] += 1
            for target, counter in rowwise.items():
                new, count = counter.most_common(1)[0]
                if count * 2 <= sum(counter.values()) or locs[target] == new:
                    continue
                t_off, t_size = symbols[target][0], symbols[target][1]
                locs[target] = new
                same_bytes = masked(usa, t_off, t_size, t_off >= CODE_END) == masked(kor, new, t_size, t_off >= CODE_END)
                states[target] = ("same" if new == t_off else "moved") if same_bytes else "paired"

    pair_relaid()
    trace("rowwise")
    for _ in range(4):
        kor_starts = sorted({a for a, s in zip(locs, states) if a is not None and s != "unknown"})
        ordered = collections.defaultdict(collections.Counter)
        for n, (off, size, kind, name) in enumerate(symbols):
            if states[n] not in ("paired", "modified") or locs[n] is None:
                continue
            script = off >= CODE_END
            usa_ptrs = pointers(usa, off, size, script)
            if not usa_ptrs:
                continue
            base = locs[n]
            j = bisect.bisect_right(kor_starts, base)
            kor_end = min(kor_starts[j] if j < len(kor_starts) else len(kor), base + 4 * size + 64)
            kor_ptrs = pointers(kor, base, kor_end - base, script)
            # Tokens: the Korean address a USA pointer must have where its
            # target is already located (an anchor), else a unique marker.
            usa_tokens, usa_info = [], []
            for index, usa_word in enumerate(usa_ptrs):
                target, thumb = target_of(usa_word)
                known = (target is not None and states[target] in ("same", "moved", "paired")
                         and locs[target] is not None)
                usa_tokens.append(locs[target] + thumb + ROM if known else ("?", index))
                usa_info.append((target, thumb, known))
            matcher = difflib.SequenceMatcher(None, usa_tokens, kor_ptrs, autojunk=False)
            blocks = matcher.get_matching_blocks()
            anchors = sum(b.size for b in blocks)
            if anchors == 0 and (len(kor_ptrs) != len(usa_ptrs) or len(usa_ptrs) < 3):
                continue
            # Every located target must line up: one that does not means the
            # container itself is misplaced.
            if anchors != sum(1 for _target, _thumb, known in usa_info if known):
                continue
            # Between two runs of anchors, gaps of the same length pair up in order.
            previous_a = previous_b = 0
            for block in blocks:
                gap_a = block.a - previous_a
                gap_b = block.b - previous_b
                if gap_a == gap_b:
                    for i in range(gap_a):
                        target, thumb, known = usa_info[previous_a + i]
                        # A partial match only fills symbols with no location:
                        # it must not overrule an earlier vote.
                        # Texts only: they hold no pointers, so a wrong guess
                        # cannot spread to what they would point to.
                        if target is not None and not known and (
                                len(kor_ptrs) == len(usa_ptrs)
                                or (states[target] == "unknown" and is_text(symbols[target][3]))):
                            ordered[target][kor_ptrs[previous_b + i] - thumb - ROM] += 1
                previous_a = block.a + block.size
                previous_b = block.b + block.size
        changed = False
        for target, counter in ordered.items():
            new, count = counter.most_common(1)[0]
            if count * 2 <= sum(counter.values()) or not 0 <= new < len(kor):
                continue
            off, size = symbols[target][0], symbols[target][1]
            locs[target] = new
            if new + size <= len(kor) and masked(usa, off, size, off >= CODE_END) == masked(kor, new, size, off >= CODE_END):
                states[target] = "same" if new == off else "moved"
            else:
                states[target] = "paired"
            changed = True
        if not changed:
            break

    pair_relaid()  # tables the ordered pairing confirmed
    trace("ordered")
    # Script alignment: decode a located event script in both ROMs, align the
    # commands (opcode and plain arguments) and pair the pointer arguments of
    # aligned commands. A script whose located targets do not all agree is
    # skipped. Only symbols with no confirmed location are filled; each newly
    # found script is decoded in the next round.
    commands = script_cmds.load(SCRIPT_TREE) if SCRIPT_TREE.is_dir() else None

    def decode_tokens(data: bytes, start: int, limit: int, stop_after: int):
        tokens, ptrs = [], []
        for op, args in script_cmds.decode(data, start, commands, limit, stop_after):
            plain = tuple(v for _at, size, v in args if not (size == 4 and ROM <= v < ROM + len(data)))
            tokens.append((op, plain))
            ptrs.append([v for _at, size, v in args if size == 4 and ROM <= v < ROM + len(data)])
        return tokens, ptrs

    def search_script(n: int) -> int | None:
        """The Korean copy of an unlocated script: its bytes with the pointer
        arguments as wildcards, found once in the Korean ROM's data, where every
        pointer to a located target agrees (or the pattern is long)."""
        off, size = symbols[n][0], symbols[n][1]
        ops = script_cmds.decode(usa, off, commands, size, 10 ** 6)
        if not ops or commands[ops[-1][0]][0] not in script_cmds.TERMINATORS:
            return None
        end = script_cmds.end_of(ops, off)
        if end - off < 8:
            return None
        pattern, checks, pos = b"", [], off
        for op, args in ops:
            pattern += re.escape(bytes([op]))
            for at, width, value in args:
                if width == 4 and ROM <= value < ROM + len(usa):
                    pattern += b"[\\x00-\\xff]{3}[\\x08\\x09]"
                    checks.append((at - off, value))
                else:
                    pattern += re.escape(usa[at:at + width])
        hits = [m.start() for m in re.finditer(pattern, kor[CODE_END:], re.S)][:2]
        if len(hits) != 1:
            return None
        new = CODE_END + hits[0]
        anchors = 0
        for rel, usa_word in checks:
            target, thumb = target_of(usa_word)
            if target is None or states[target] not in ("same", "moved", "paired") or locs[target] is None:
                continue
            if struct.unpack_from("<I", kor, new + rel)[0] - thumb - ROM != locs[target]:
                return None
            anchors += 1
        return new if anchors or end - off >= 16 else None

    aligned_total = searched_total = 0
    for _ in range(8 if commands else 0):
        searched = 0
        for n, (off, size, kind, name) in enumerate(symbols):
            if off >= CODE_END and states[n] == "unknown" and "Script" in name:
                new = search_script(n)
                if new is not None:
                    locs[n] = new
                    same_bytes = masked(usa, off, size, True) == masked(kor, new, size, True)
                    states[n] = ("same" if new == off else "moved") if same_bytes else "paired"
                    searched += 1
        searched_total += searched
        kor_starts = sorted({a for a, s in zip(locs, states) if a is not None and s != "unknown"})
        votes_s = collections.defaultdict(collections.Counter)
        for n, (off, size, kind, name) in enumerate(symbols):
            # Confirmed scripts only: a "modified" place is a guess.
            if off < CODE_END or locs[n] is None or states[n] not in ("same", "moved", "paired") or "Script" not in name:
                continue
            ops = script_cmds.decode(usa, off, commands, size, 10 ** 6)
            if not ops:
                continue
            used = script_cmds.end_of(ops, off) - off
            if used != size and not (used < size and commands[ops[-1][0]][0] in script_cmds.TERMINATORS):
                continue  # not (only) a script
            terminators = sum(1 for op, _a in ops if commands[op][0] in script_cmds.TERMINATORS)
            usa_tokens, usa_ptrs = decode_tokens(usa, off, used, 10 ** 6)
            base = locs[n]
            j = bisect.bisect_right(kor_starts, base)
            kor_limit = min((kor_starts[j] if j < len(kor_starts) else len(kor)) - base, 4 * size + 64)
            kor_tokens, kor_ptrs = decode_tokens(kor, base, max(kor_limit, 1), max(terminators, 1))
            if not kor_tokens or kor_tokens[0][0] != usa_tokens[0][0]:
                continue
            matcher = difflib.SequenceMatcher(None, usa_tokens, kor_tokens, autojunk=False)
            pairs, conflict = [], False
            for block in matcher.get_matching_blocks():
                for i in range(block.size):
                    ua, ka = usa_ptrs[block.a + i], kor_ptrs[block.b + i]
                    if len(ua) != len(ka):
                        conflict = True
                    pairs += zip(ua, ka)
            # Every located target of the script must line up.
            fills = []
            for usa_word, kor_word in pairs:
                target, thumb = target_of(usa_word)
                if target is None:
                    continue
                if states[target] in ("same", "moved", "paired") and locs[target] is not None:
                    if locs[target] != kor_word - thumb - ROM:
                        conflict = True
                else:
                    fills.append((target, kor_word - thumb - ROM))
            if conflict:
                continue
            for target, new in fills:
                votes_s[target][new] += 1
        changed = 0
        for target, counter in votes_s.items():
            new, count = counter.most_common(1)[0]
            if count * 2 <= sum(counter.values()) or not 0 <= new < len(kor):
                continue
            off, size = symbols[target][0], symbols[target][1]
            locs[target] = new
            same_bytes = new + size <= len(kor) and masked(usa, off, size, True) == masked(kor, new, size, True)
            states[target] = ("same" if new == off else "moved") if same_bytes else "paired"
            changed += 1
        aligned_total += changed
        if not changed and not searched:
            break
    print("script alignment located", aligned_total, "symbols; script search", searched_total)

    trace("scripts")
    # Call pairing: an unchanged function makes its calls (Thumb BL pairs) at
    # the same offsets, so each callee's Korean address is the Korean BL's
    # target. Functions reached only by calls get no pointer votes otherwise.
    def bl_target(data: bytes, at: int) -> int | None:
        hi, lo = struct.unpack_from("<HH", data, at)
        if hi & 0xF800 != 0xF000 or lo & 0xF800 != 0xF800:
            return None
        offset = (hi & 0x7FF) << 12 | (lo & 0x7FF) << 1
        if offset & 0x400000:
            offset -= 0x800000
        return at + 4 + offset

    called_total = 0
    for _ in range(8):
        calls = collections.defaultdict(collections.Counter)
        for n, (off, size, kind, name) in enumerate(symbols):
            if off >= CODE_END or states[n] not in ("same", "moved") or locs[n] is None:
                continue
            for i in range(0, size - 3, 2):
                usa_to = bl_target(usa, off + i)
                if usa_to is None:
                    continue
                kor_to = bl_target(kor, locs[n] + i)
                target = by_addr.get(usa_to)
                if target is not None and kor_to is not None and target != n:
                    calls[target][kor_to] += 1
        changed = 0
        for target, counter in calls.items():
            new, count = counter.most_common(1)[0]
            if count * 2 <= sum(counter.values()) or states[target] in ("same", "moved") or locs[target] == new:
                continue
            off, size = symbols[target][0], symbols[target][1]
            locs[target] = new
            same_bytes = new + size <= len(kor) and masked(usa, off, size) == masked(kor, new, size)
            states[target] = ("same" if new == off else "moved") if same_bytes else "paired"
            changed += 1
        called_total += changed
        if not changed:
            break
    print("call pairing located", called_total, "functions")
    trace("calls")

    # Direct references: read the Korean word at the same offset of every
    # located container that points to a data symbol. When all the references
    # agree (at least two, or one from an unchanged container), that word is
    # the symbol's Korean address, whatever an earlier vote said.
    container_starts = [s[0] for s in symbols]
    direct = collections.defaultdict(collections.Counter)
    exact_refs = collections.defaultdict(int)
    # Code counts too: the literal pool of a function whose bytes are
    # unchanged sits at the same offset (C strings referenced from code).
    for p in itertools.chain(range(0, CODE_END - 3, 4), range(CODE_END, len(usa) - 3)):
        if usa[p + 3] not in (0x08, 0x09):
            continue
        word = struct.unpack_from("<I", usa, p)[0]
        target = by_addr.get(word - ROM)
        if target is None or symbols[target][0] < CODE_END:
            continue
        c = bisect.bisect_right(container_starts, p) - 1
        while c >= 0 and symbols[c][0] + symbols[c][1] <= p:
            c -= 1
        if c < 0 or c == target or locs[c] is None or states[c] == "unknown":
            continue
        if p < CODE_END and states[c] not in ("same", "moved"):
            continue
        kp = locs[c] + p - symbols[c][0]
        if not 0 <= kp <= len(kor) - 4:
            continue
        kor_word = struct.unpack_from("<I", kor, kp)[0]
        if not ROM <= kor_word < ROM + len(kor):
            continue
        if stale_vote(usa, kor, symbols[target][0], symbols[target][1], kor_word - ROM):
            continue
        direct[target][kor_word - ROM] += 1
        if states[c] in ("same", "moved"):
            exact_refs[target] += 1
    overridden = 0
    for target, counter in direct.items():
        if len(counter) != 1:
            continue
        new, count = next(iter(counter.items()))
        if new == locs[target] or (count < 2 and not exact_refs[target]):
            continue
        t_off, t_size = symbols[target][0], symbols[target][1]
        locs[target] = new
        same_bytes = masked(usa, t_off, t_size, True) == masked(kor, new, t_size, True)
        states[target] = ("same" if new == t_off else "moved") if same_bytes else "paired"
        overridden += 1
    print("direct references overrode", overridden, "locations")

    trace("direct")
    # String runs: texts laid out one after another (strings.c) keep their
    # order. Unlocated texts between two located ones take, in order, the
    # Korean strings between those two, when there are exactly as many.
    def string_len(data: bytes, at: int) -> int:
        end = data.find(b"\xff", at, at + 0x1000)
        return -1 if end < 0 else end + 1 - at

    run_total = 0
    order = sorted(range(len(symbols)), key=lambda n: symbols[n][0])
    i = 0
    while i < len(order):
        n = order[i]
        if states[n] == "unknown" or locs[n] is None or not is_text(symbols[n][3]) or symbols[n][0] < CODE_END:
            i += 1
            continue
        j = i + 1
        run = []
        while j < len(order) and states[order[j]] == "unknown" and is_text(symbols[order[j]][3]):
            run.append(order[j])
            j += 1
        if not run or j >= len(order) or states[order[j]] == "unknown" or not is_text(symbols[order[j]][3]):
            i = max(j, i + 1)
            continue
        # The USA layout: each string followed by padding up to the next one.
        chain = [n] + run + [order[j]]
        usa_ok = all(0 <= symbols[b][0] - (symbols[a][0] + max(string_len(usa, symbols[a][0]), 0)) <= 3
                     for a, b in zip(chain, chain[1:]))
        k_len = string_len(kor, locs[n])
        if not usa_ok or k_len < 0 or locs[order[j]] is None:
            i = j
            continue
        pos, starts = locs[n] + k_len, []
        while pos < locs[order[j]] and len(starts) <= len(run):
            while pos < locs[order[j]] and kor[pos] == 0x00 and (pos % 4):
                pos += 1  # alignment padding
            if pos >= locs[order[j]]:
                break
            length = string_len(kor, pos)
            if length < 0 or pos + length > locs[order[j]]:
                starts = []
                break
            starts.append(pos)
            pos += length
        if len(starts) == len(run):
            for target, new in zip(run, starts):
                locs[target] = new
                states[target] = "moved" if kor[new:new + symbols[target][1]] == usa[symbols[target][0]:symbols[target][0] + symbols[target][1]] else "paired"
                run_total += 1
        i = j
    print("string runs located", run_total, "texts")
    trace("runs")

    rows, counts = [], collections.Counter()
    for n, (off, size, kind, name) in enumerate(symbols):
        new, status = locs[n], states[n]
        counts[(kind.lower(), status)] += 1
        rows.append((name, kind, size, off + ROM, None if new is None else new + ROM, status))

    with open(out / "symbols_kor.tsv", "w", encoding="utf-8") as f:
        f.write("name\ttype\tsize\tusa\tkor\tstatus\n")
        for name, kind, size, usa_a, kor_a, status in rows:
            f.write("%s\t%s\t%d\t0x%08X\t%s\t%s\n" % (
                name, kind, size, usa_a, "" if kor_a is None else "0x%08X" % kor_a, status))

    explained = bytearray(len(kor))
    for src, n, shift in copies:
        explained[src + shift:src + shift + n] = b"\1" * n
    regions, start = [], None
    for pos in range(len(kor) + 1):
        new = pos < len(kor) and not explained[pos] and kor[pos] != 0xFF
        if new and start is None:
            start = pos
        elif not new and start is not None:
            if pos - start >= 16:
                regions.append((start, pos - start))
            start = None
    with open(out / "new_regions_kor.tsv", "w") as f:
        f.write("kor\tsize\n")
        for s, n in regions:
            f.write("0x%08X\t%d\n" % (s + ROM, n))

    print("symbols:", len(rows))
    for key in sorted(counts):
        print("  %-6s %-9s %d" % (key[0], key[1], counts[key]))
    print("new regions:", len(regions), "bytes:", sum(n for _, n in regions))


if __name__ == "__main__":
    main()
