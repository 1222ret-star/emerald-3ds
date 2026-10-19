#!/usr/bin/env python3
"""Stage the Korean proof of concept from the player's Korean ROM.

The Korean ROM is the clean BPEE ROM with the fan translation
"20210221 Pokemon Emerald Version (E-K)" applied. Nothing from it is stored
in the repository: this script reads the player's ROM and writes into the
generated tree only.

What it stages:
  - the three Hangul glyph tables (graphics/fonts/hangul_*.hanfont in RomFS);
  - every string the manifest (tools/locales/korean.json.gz) maps: source
    positions of `_("...")` and `.string` definitions, with the offset and size
    of the Korean text in the ROM;
    (name tables included: species, moves, types, abilities, items, trainers,
    trainer classes, Pokedex categories, decorations);
  - GAME_LANGUAGE set to LANGUAGE_KOREAN, which turns on the Hangul text path.

Hangul text uses two-byte codes: a lead byte 0x37-0x41 and a trail byte,
KS X 1001 order (see docs/KOREAN.md).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path

KOREAN_SHA1 = "81b13f7931a85c18f08c6de3c0202ab47d6c8f37"
ROM_SIZE = 16 * 1024 * 1024
# Glyph tables in the Korean ROM: codes 0x3700-0x412F, 64 bytes each.
HANGUL_FONT_SIZE = (0x4130 - 0x3700) * 0x40
HANGUL_FONTS = {
    "hangul_small.hanfont": 0x65DDD8,   # FONT_SMALL, FONT_SMALL_NARROW (8x13)
    "hangul_normal.hanfont": 0x6AF5D8,  # FONT_SHORT, FONT_NORMAL (11 wide)
    "hangul_narrow.hanfont": 0x6D81D8,  # FONT_NARROW (8x15)
}
ROOT = Path(__file__).resolve().parents[1]


def encoded(data: bytes) -> str:
    return ",".join("0x%02X" % byte for byte in data)


def load_rom(path: Path) -> bytes:
    data = path.read_bytes()
    if len(data) < ROM_SIZE:
        data += b"\xff" * (ROM_SIZE - len(data))
    if hashlib.sha1(data).hexdigest() != KOREAN_SHA1:
        raise SystemExit("This localization requires the Korean ROM (BPEE + E-K 20210221), SHA-1 "
                         + KOREAN_SHA1)
    return data


def stage(tree: Path, rom_path: Path) -> None:
    rom = load_rom(rom_path)
    writes: dict[Path, bytes] = {}

    fonts = tree / "3ds_port/romfs/graphics/fonts"
    for name, offset in HANGUL_FONTS.items():
        writes[fonts / name] = rom[offset:offset + HANGUL_FONT_SIZE]

    manifest = json.loads(gzip.decompress((ROOT / "tools/locales/korean.json.gz").read_bytes()))
    if manifest["rom_sha1"] != KOREAN_SHA1:
        raise SystemExit("korean.json.gz was made for another ROM")
    for relative, file in manifest["files"].items():
        path = tree / relative
        text = writes[path].decode() if path in writes else path.read_text(encoding="utf-8")
        if path not in writes and hashlib.sha256(text.encode()).hexdigest() != file["sha256"]:
            raise SystemExit("Source differs from the pinned patched tree: " + relative)
        previous_end = 0
        for start, end, offset, size, kind in sorted(file["edits"]):
            if not previous_end <= start < end <= len(text) or not 0 <= offset < offset + size <= len(rom):
                raise SystemExit("Overlapping or out-of-range edit: " + relative)
            previous_end = end
        for start, end, offset, size, kind in sorted(file["edits"], reverse=True):
            data = rom[offset:offset + size]
            if kind == "c":
                replacement = "{" + encoded(data) + "}"
            elif kind == "asm":
                replacement = "\t.byte " + encoded(data)
            else:
                raise SystemExit("Unknown edit kind: " + kind)
            text = text[:start] + replacement + text[end:]
        writes[path] = text.encode()

    path = tree / "include/constants/global.h"
    text = path.read_text(encoding="utf-8")
    if "#define GAME_LANGUAGE (LANGUAGE_ENGLISH)" not in text:
        raise SystemExit("global.h: GAME_LANGUAGE is not the English default")
    writes[path] = text.replace("#define GAME_LANGUAGE (LANGUAGE_ENGLISH)",
                                "#define GAME_LANGUAGE (LANGUAGE_KOREAN)").encode()

    # Every check passed: write.
    for path, data in writes.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (tree / ".emerald3ds-locale").write_text("KOR proof of concept\n")
    print("Korean proof-of-concept data staged.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    args = parser.parse_args()
    stage(args.tree.resolve(), args.rom.resolve())


if __name__ == "__main__":
    main()
