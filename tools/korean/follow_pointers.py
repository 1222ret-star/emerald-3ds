#!/usr/bin/env python3
"""Find the Korean address of strings relocmap.py could not place, through
the pointers that reference them.

A string the translation rewrote has no bytes in common with the English one,
so nothing locates it but its references: a script's `msgbox`, a table's
`.text` field. Those references sit in code or data the copy map does place.
For every pointer to the English string, the copy record ending just before
it (or starting just after it) gives where the same pointer is in the Korean
ROM, and the word there is the Korean string. The answer is kept only when
the references that lead to text all agree.

The English address comes from symbols_kor.tsv, or for a local label (no
symbol) from the string itself, found once in the English ROM.

  python follow_pointers.py TREE SYMBOLS_KOR.tsv MAP.json USA.gba KOR.gba OUT.json NAME...

OUT.json maps each name placed to [english address, Korean address], the
format gen_korean_manifest.py reads as its extra symbols.
"""
from __future__ import annotations

import bisect
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hangul_encode import charmap, encode  # noqa: E402

ROM = 0x08000000
NEAR = 256  # how far the copy record giving the shift may be
NEAR_TABLE = 64  # how far a placed pointer of the same table may be
DEPTH = 3  # unplaced objects followed between a string and a placed one


def source_text(tree: Path, name: str) -> str | None:
    """The text of an asm label (its .string lines) or of a C string, joined."""
    label = re.compile(r"^" + re.escape(name) + r"::?[ \t]*\n((?:[ \t]*\.string[^\n]*\n)+)", re.M)
    for path in list((tree / "data").rglob("*.inc")) + list((tree / "data").rglob("*.s")):
        text = path.read_text(encoding="utf-8")
        if name not in text:
            continue
        match = label.search(text)
        if match:
            return "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', match.group(1)))
    # Or a C string: `u8 NAME[] = _("...");`
    c_string = re.compile(r"\b" + re.escape(name) + r"\s*\[\s*\]\s*=\s*_\(((?:\s*\"(?:[^\"\\\n]|\\.)*\")+)\s*\)")
    for path in list((tree / "src").rglob("*.c")) + list((tree / "src").rglob("*.h")):
        text = path.read_text(encoding="utf-8")
        if name not in text:
            continue
        match = c_string.search(text)
        if match:
            return "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', match.group(1)))
    return None


def english_address(tree: Path, name: str, symbols: dict, usa: bytes, chars: dict, named: dict) -> int | None:
    if name in symbols:
        return symbols[name]
    text = source_text(tree, name)
    if text is None:
        return None
    # The whole string, else the part before markup the encoder does not
    # know; it must be found once.
    for part in (text, re.split(r"[{]", text)[0]):
        try:
            key = b"".join(named[piece[1:-1]] if piece.startswith("{") else bytes(encode(piece, chars))
                           for piece in re.split(r"(\{[A-Z_0-9]+\})", part) if piece).rstrip(b"\xff")
        except Exception:  # noqa: BLE001 - markup the encoder does not know
            continue
        if len(key) >= 12 and usa.count(key) == 1:
            return usa.find(key)
    return None


def is_text(rom: bytes, offset: int) -> bool:
    """A terminated string within 1 KB, with Hangul in it."""
    end = rom.find(b"\xff", offset, offset + 1024)
    if end < 0:
        return False
    body = rom[offset:end]
    return any(0x37 <= body[i] <= 0x41 and 0x01 <= body[i + 1] <= 0xEF for i in range(len(body) - 1))


def main() -> None:
    tree, symbols_path, map_path, usa_path, kor_path, out_path = map(Path, sys.argv[1:7])
    names = sys.argv[7:]
    usa, kor = usa_path.read_bytes(), kor_path.read_bytes()
    chars = charmap(tree)
    named = {}  # {PLAYER}, {KUN}, ...: charmap.txt's named codes
    for line in (tree / "charmap.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Z_0-9]+)\s*=\s*((?:[0-9A-F]{2}\s*)*)$", line)
        if m:
            named.setdefault(m.group(1), bytes.fromhex(m.group(2)))
    symbols, placed, objects = {}, [], {}
    for line in symbols_path.read_text(encoding="utf-8").splitlines()[1:]:
        name, _kind, size, usa_a, kor_a, status = line.split("\t")
        symbols.setdefault(name, int(usa_a, 16) - ROM)
        if kor_a and status in ("same", "moved", "paired") and int(size) > 4:
            placed.append((int(usa_a, 16) - ROM, int(size), int(kor_a, 16) - ROM))
        elif int(size) >= 4 and int(usa_a, 16) >= ROM:
            objects.setdefault(int(usa_a, 16) - ROM, int(size))
    placed.sort()
    placed_starts = [p[0] for p in placed]
    unplaced = sorted(objects.items())
    unplaced_starts = [u[0] for u in unplaced]
    records = sorted((src, tgt, length) for _op, tgt, length, src in json.loads(map_path.read_text()))
    starts = [r[0] for r in records]

    def references(address: int) -> list:
        word, sites = (ROM + address).to_bytes(4, "little"), []
        at = usa.find(word)
        while at >= 0:
            sites.append(at)
            at = usa.find(word, at + 1)
        return sites

    def same_fields(address: int, size: int, korean: int) -> bool:
        """The object's words that are not pointers are the same in both ROMs
        (a landmark's flag, a struct's numbers)."""
        for i in range(0, min(size, 64) - 3, 4):
            word = int.from_bytes(usa[address + i:address + i + 4], "little")
            if ROM <= word < ROM + len(usa):
                continue
            if usa[address + i:address + i + 4] != kor[korean + i:korean + i + 4]:
                return False
        return True

    memo = {}

    def korean_of(address: int, size: int, depth: int) -> set:
        """Where an object relocmap.py did not place is in the Korean ROM,
        through the pointers to it (a struct of the name, the list of the
        struct, ...)."""
        if depth == 0:
            return set()
        if (address, depth) not in memo:
            memo[(address, depth)] = set()
            found = set()
            for site in references(address):
                for k in to_korean(site, depth - 1):
                    if 0 <= k <= len(kor) - 4:
                        target = int.from_bytes(kor[k:k + 4], "little") - ROM
                        if 0 <= target <= len(kor) - size and same_fields(address, size, target):
                            found.add(target)
            memo[(address, depth)] = found if len(found) <= 4 else set()
        return memo[(address, depth)]

    def to_korean(site: int, depth: int = DEPTH) -> set:
        """Where the pointer at USA offset `site` is in the Korean ROM: by the
        shift of the nearest copy record before it and of the nearest after it
        (translated text around a script moves only what follows it)."""
        found = set()
        i = bisect.bisect_right(starts, site) - 1
        if i >= 0 and site - (records[i][0] + records[i][2]) < NEAR:
            found.add(site - records[i][0] + records[i][1])
        i = bisect.bisect_left(starts, site + 4)
        if i < len(records) and records[i][0] - (site + 4) < NEAR:
            found.add(site - records[i][0] + records[i][1])
        # A table of pointers has no copied bytes near: the table's own symbol.
        i = bisect.bisect_right(placed_starts, site) - 1
        if i >= 0 and site + 4 <= placed[i][0] + placed[i][1]:
            found.add(site - placed[i][0] + placed[i][2])
        # A pointer inside an object that is itself unplaced: where that object is.
        i = bisect.bisect_right(unplaced_starts, site) - 1
        if i >= 0 and site + 4 <= unplaced[i][0] + unplaced[i][1]:
            for korean in korean_of(unplaced[i][0], unplaced[i][1], depth):
                found.add(korean + site - unplaced[i][0])
        # Or a neighbour in the same table that a previous answer placed.
        for other, korean in resolved.items():
            if abs(other - site) <= NEAR_TABLE and (other - site) % 4 == 0:
                found.add(korean + site - other)
        return found

    out = json.loads(out_path.read_text()) if out_path.exists() else {}
    resolved = {}  # USA pointer site -> Korean pointer site, of the answers so far
    report = {}
    for _pass in range(3):  # answers place their tables' neighbours
        for name in names:
            if name in report and report[name][0]:
                continue
            address = english_address(tree, name, symbols, usa, chars, named)
            if address is None:
                report[name] = (False, "no English address")
                continue
            word = (ROM + address).to_bytes(4, "little")
            sites, at = [], usa.find(word)
            while at >= 0:
                sites.append(at)
                at = usa.find(word, at + 1)
            answers, leads = set(), {}
            for site in sites:
                for k in to_korean(site):
                    if 0 <= k <= len(kor) - 4:
                        target = int.from_bytes(kor[k:k + 4], "little") - ROM
                        if 0 <= target < len(kor) and is_text(kor, target):
                            answers.add(target)
                            leads[site] = k
            if len(answers) == 1:
                target = answers.pop()
                out[name] = ["0x%08X" % (ROM + address), "0x%08X" % (ROM + target)]
                resolved.update(leads)
                report[name] = (True, "0x%08X -> 0x%08X (%d refs)" % (ROM + address, ROM + target, len(sites)))
            else:
                report[name] = (False, "%d refs, answers %s" % (
                    len(sites), sorted("0x%X" % (ROM + a) for a in answers)))
    for name in names:
        print("%-50s %s" % (name, report[name][1]))
    out_path.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
