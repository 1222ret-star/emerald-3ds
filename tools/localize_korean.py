#!/usr/bin/env python3
"""Stage the Korean build from the player's Korean ROM.

The Korean ROM is the Japanese ROM (BPEJ) with the final fan translation
"20260613 J-K" applied; the result is built from pret's English sources, so
its symbols map to ours. Nothing from it is stored
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
import sys
from pathlib import Path

KOREAN_SHA1 = "17cd49e1af1184cd29355c674bedee7f5b72b055"
ROM_SIZE = 16 * 1024 * 1024
# Glyph tables in the Korean ROM: codes 0x3700-0x412F, 64 bytes each.
HANGUL_FONT_SIZE = (0x4130 - 0x3700) * 0x40
HANGUL_FONTS = {
    "hangul_small.hanfont": 0x659DDC,   # FONT_SMALL (8x13)
    "hangul_normal.hanfont": 0x6AB5DC,  # 11 wide: the port's bottom screen and HD battle HUD
    "hangul_narrow.hanfont": 0x6D41DC,  # FONT_NARROW, FONT_NORMAL (8x15), FONT_SHORT (8x14)
    "hangul_small_narrow.hanfont": 0x6FCDDC,  # FONT_SMALL_NARROW (8x13)
}
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from locale_lists import stage_id_lists  # noqa: E402
sys.path.insert(0, str(ROOT / "builder"))
from emerald3ds_builder.recipe import lz77_decompress  # noqa: E402


def encoded(data: bytes) -> str:
    return ",".join("0x%02X" % byte for byte in data)


def load_rom(path: Path) -> bytes:
    data = path.read_bytes()
    if len(data) < ROM_SIZE:
        data += b"\xff" * (ROM_SIZE - len(data))
    if hashlib.sha1(data).hexdigest() != KOREAN_SHA1:
        raise SystemExit("This localization requires the Korean ROM (Japanese ROM + J-K 20260613 patch), SHA-1 "
                         + KOREAN_SHA1)
    return data


def stage_easy_chat_letters(tree: Path, rom: bytes, symbols_path: Path, writes: dict) -> None:
    """Easy Chat's word lists by first letter, as the Korean ROM groups them: Others
    and the 19 initial consonants (patch 0069 lays out the keyboard). Read from the
    player's ROM at the table the Korean symbols give; word IDs only."""
    import struct
    text = gzip.decompress(symbols_path.read_bytes()).decode()
    m = re.search(r"^\.equ gEasyChatWordsByLetterPointers, (\d+)$", text, re.M)
    if not m:
        raise SystemExit("Korean symbols lack gEasyChatWordsByLetterPointers")
    table = int(m.group(1)) - 0x08000000
    groups = []
    while len(groups) < 27:
        pointer, count = struct.unpack_from("<II", rom, table + 8 * len(groups))
        if not 0x08000000 <= pointer < 0x08000000 + len(rom) or not 0 < count < 1000:
            break
        words = struct.unpack_from("<%dH" % count, rom, pointer - 0x08000000)
        if any(w != 0xFFFF and (w >> 9) >= 22 and w > 64 for w in words):
            raise SystemExit("Easy Chat letter group %d holds no word IDs" % len(groups))
        groups.append(words)
    if len(groups) != 20:
        raise SystemExit("Expected 20 Easy Chat letter groups in the Korean ROM, found %d" % len(groups))
    out = ['#include "easy_chat.h"', "", "// Written by tools/localize_korean.py from the player's Korean ROM:",
           "// Others, then the 19 initial consonants.", ""]
    for i, words in enumerate(groups):
        out.append("static const u16 sKoreanWordsByLetter%d[] = {" % i)
        out += ["    0x%04X," % w for w in words]
        out += ["};", ""]
    out.append("const struct EasyChatWordsByLetter gEasyChatWordsByLetterPointers[EC_NUM_ALPHABET_GROUPS + 18] = {")
    out += ["    {sKoreanWordsByLetter%d, ARRAY_COUNT(sKoreanWordsByLetter%d)}," % (i, i) for i in range(len(groups))]
    out += ["};", ""]
    writes[tree / "src/data/easy_chat/easy_chat_words_by_letter.h"] = "\n".join(out).encode()


# The Korean ROM's own sentences for the facility trainers, three each (before
# the battle, after winning it, after losing it), where the English game joins
# six Easy Chat words in English order: pointer tables its added code reads,
# by facility. (table, trainers)
FRONTIER_SPEECH = {
    "sKoreanFrontierSpeech": (0x5C18E4, 300),
    "sKoreanSlateportTentSpeech": (0x5C2FB8, 30),
    "sKoreanVerdanturfTentSpeech": (0x5C39F8, 30),
    "sKoreanFallarborTentSpeech": (0x5C4430, 30),
}


def stage_frontier_speech(tree: Path, rom: bytes, writes: dict) -> None:
    """The facility trainers' Korean sentences (patch 0074 reads them), copied
    from the player's ROM into a header of the generated tree."""
    import struct
    out = ["// Written by tools/localize_korean.py from the player's Korean ROM: the",
           "// facility trainers' sentences, before / won / lost for each trainer.", ""]
    for name, (table, trainers) in FRONTIER_SPEECH.items():
        entries = []
        for i in range(trainers * 3):
            pointer = struct.unpack_from("<I", rom, table + 4 * i)[0] - 0x08000000
            end = rom.find(b"\xff", pointer, pointer + 256) if 0 <= pointer < len(rom) else -1
            if end < 0:
                raise SystemExit("%s: entry %d is no string" % (name, i))
            out.append("static const u8 %s_%d[] = {%s};" % (name, i, encoded(rom[pointer:end + 1])))
            entries.append("%s_%d" % (name, i))
        out.append("static const u8 *const %s[%d] = {" % (name, trainers * 3))
        out += ["    %s," % entry for entry in entries]
        out += ["};", ""]
    writes[tree / "src/data/battle_frontier/korean_trainer_speech.h"] = "\n".join(out).encode()


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
            elif kind == "u8":
                replacement = "%d" % data[0]
            elif kind == "u16":
                replacement = "0x%04X" % int.from_bytes(data, "little")
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

    # The Korean ROM's own graphics (title logo, menu tiles, ...).
    for relative, offset, size in manifest.get("graphics", []):
        if not 0 <= offset < offset + size <= len(rom):
            raise SystemExit("Graphic outside ROM: " + relative)
        writes[tree / relative] = rom[offset:offset + size]
        if relative.endswith(".lz"):
            writes[tree / relative[:-3]] = lz77_decompress(rom, offset)

    # The Korean game's symbol names and addresses, for the recipe's hints.
    symbols = ROOT / "tools/locales/korean-symbols.s.gz"
    writes[tree / "build/korean-reference.s"] = gzip.decompress(symbols.read_bytes())
    # Easy Chat's move and Pokemon lists in this ROM's order.
    stage_id_lists(tree, rom, symbols, writes)
    # Easy Chat's keyboard groups: Others and the initial consonants.
    stage_easy_chat_letters(tree, rom, symbols, writes)
    # The facility trainers' sentences.
    stage_frontier_speech(tree, rom, writes)

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
