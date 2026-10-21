#!/usr/bin/env python3
"""Encode Korean text into the game's codes, as C byte lists or .byte lines.

Hangul syllables take two bytes in KS X 1001 order (lead 0x37 + index // 239,
trail index % 239 + 1); other characters come from pret's charmap.txt.
Markup: {STR_VAR_1..3}, {PLAYER}, particles {은는} {이가} {을를} {으로} {이다}
{과와} {아야}, \\n \\l \\p, and a final $.

  python hangul_encode.py TREE "{STR_VAR_1}{을를} 하나 더 사용하겠습니까?$"
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

CODES = {
    "{STR_VAR_1}": [0xFD, 0x02], "{STR_VAR_2}": [0xFD, 0x03], "{STR_VAR_3}": [0xFD, 0x04],
    "{PLAYER}": [0xFD, 0x01],
    "{은는}": [0xFD, 0x10], "{이가}": [0xFD, 0x11], "{을를}": [0xFD, 0x12], "{으로}": [0xFD, 0x13],
    "{이다}": [0xFD, 0x14], "{과와}": [0xFD, 0x15], "{아야}": [0xFD, 0x16],
    "\\n": [0xFE], "\\l": [0xFA], "\\p": [0xFB], "$": [0xFF],
}


def charmap(tree: Path) -> dict[str, int]:
    chars = {}
    for line in (tree / "charmap.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^'(.)'\s*=\s*([0-9A-Fa-f]{2})\s*$", line)
        if m and m.group(1) not in chars:
            chars[m.group(1)] = int(m.group(2), 16)
    return chars


def encode(text: str, chars: dict) -> list[int]:
    out, i = [], 0
    while i < len(text):
        for code, value in CODES.items():
            if text.startswith(code, i):
                out += value
                i += len(code)
                break
        else:
            c = text[i]
            if "가" <= c <= "힣":
                euc = c.encode("euc-kr")  # KS X 1001: rows 0xB0-0xC8, columns 0xA1-0xFE
                index = (euc[0] - 0xB0) * 94 + euc[1] - 0xA1
                out += [0x37 + index // 239, index % 239 + 1]
            else:
                out.append(chars[c])
            i += 1
    return out


def c_bytes(values: list[int]) -> str:
    return "{" + ",".join("0x%02X" % v for v in values) + "}"


if __name__ == "__main__":
    tree, text = Path(sys.argv[1]), sys.argv[2]
    print(c_bytes(encode(text, charmap(tree))))
