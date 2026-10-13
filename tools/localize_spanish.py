#!/usr/bin/env python3
"""Stage the BPES localization from a user's clean Spanish ROM.

The checked-in manifest contains source positions and ROM offsets, never game
text or graphics. Run after bootstrap applies the pinned source patches.
The v0.1.2 Spanish build is user-tested on a physical 3DS. New integrations
require their own hardware play testing.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "builder"))
from emerald3ds_builder.rom import load_rom
from emerald3ds_builder.recipe import lz77_decompress


def encoded(data: bytes) -> str:
    return ",".join("0x%02X" % byte for byte in data)


def localize_port_battle_text(text: str) -> str:
    replacements = {
        "sText_PkmnTeamGainedEXP": r'_("¡El resto del equipo ganó\npuntos de experiencia!\p")',
        "sText_WildPkmnPrefix": '_("salvaje ")',
        "sText_FoePkmnPrefix": '_("enemigo ")',
        "sText_FoePkmnPrefix2": '_("enemigo ")',
        "sText_FoePkmnPrefix3": '_("enemigo ")',
        "sText_FoePkmnPrefix4": '_("enemigo ")',
    }
    for name, replacement in replacements.items():
        pattern = r"(static const u8 " + name + r"\[\] = )[^;]+;"
        matches = list(re.finditer(pattern, text))
        if name == "sText_PkmnTeamGainedEXP" and len(matches) == 2:
            prefix = text[:matches[0].start()].rstrip()
            between = text[matches[0].end():matches[1].start()].strip()
            if not prefix.endswith("#if defined(PORT_BRIDGE) && GAME_LANGUAGE == LANGUAGE_FRENCH") or between != "#else":
                raise ValueError("Missing or duplicate battle text: " + name)
            match = matches[1]
        elif len(matches) == 1:
            match = matches[0]
        else:
            raise ValueError("Missing or duplicate battle text: " + name)
        text = text[:match.start()] + match[1] + replacement + ";" + text[match.end():]
    return text


def stage(tree: Path, rom_path: Path) -> None:
    manifest = json.loads(gzip.decompress((ROOT / "tools/locales/spanish.json.gz").read_bytes()))
    rom = load_rom(rom_path)
    if rom.sha1 != manifest["rom_sha1"]:
        raise ValueError("This localization requires the clean Spanish BPES ROM")
    source = rom.data
    writes: dict[Path, bytes] = {}
    for relative, file in manifest["files"].items():
        path = tree / relative
        text = path.read_text(encoding="utf-8")
        if hashlib.sha256(text.encode()).hexdigest() != file["sha256"]:
            raise ValueError("Source differs from the pinned patched tree: " + relative)
        previous_end = 0
        for start, end, offset, size, kind in sorted(file["edits"]):
            if not previous_end <= start < end <= len(text) or not 0 <= offset < offset + size <= len(source):
                raise ValueError("Overlapping or out-of-range edit: " + relative)
            previous_end = end
        for start, end, offset, size, kind in sorted(file["edits"], reverse=True):
            data = source[offset:offset + size]
            if kind == "c":
                replacement = "{" + encoded(data) + "}"
            elif kind == "asm":
                replacement = "\n\t.byte " + encoded(data) + "\n"
            elif kind == "u32":
                replacement = str(struct.unpack("<I", data)[0])
            elif kind == "u16s":
                replacement = ",".join("0x%04X" % n for n in struct.unpack("<6H", data))
            elif kind == "u16array":
                replacement = ",".join("0x%04X" % n for n in struct.unpack("<%dH" % (size // 2), data))
            elif kind == "u8rows22":
                if size != 18 * 22:
                    raise ValueError("Invalid type name table dimensions")
                replacement = "{" + ",".join("{" + encoded(data[i:i + 22]) + "}"
                                              for i in range(0, size, 22)) + "}"
            elif kind == "u16rows10":
                if size % 20:
                    raise ValueError("Invalid mail word table dimensions")
                rows = [",".join("0x%04X" % n for n in struct.unpack_from("<10H", data, i))
                        for i in range(0, size, 20)]
                replacement = "{" + ",".join("{" + row + "}" for row in rows) + "}"
            elif kind == "bard":
                if size % 48:
                    raise ValueError("Invalid bard table dimensions")
                phonemes = []
                for index in range(0, size, 8):
                    if data[index + 6:index + 8] != b"\0\0":
                        raise ValueError("Unexpected bard record padding")
                    fields = struct.unpack_from("<BbHh", data, index)
                    phonemes.append("{" + ",".join(str(n) for n in fields) + "}")
                replacement = "{" + ",".join("{" + ",".join(phonemes[i:i + 6]) + "}"
                                              for i in range(0, len(phonemes), 6)) + "}"
            else:
                raise ValueError("Unknown edit kind: " + kind)
            text = text[:start] + replacement + text[end:]
        if relative == "src/battle_message.c":
            text = localize_port_battle_text(text)
        writes[path] = text.encode()

    for relative, offset, size in manifest["graphics"]:
        if not 0 <= offset < offset + size <= len(source):
            raise ValueError("Graphic outside ROM: " + relative)
        data = source[offset:offset + size]
        writes[tree / relative] = data
        if relative.endswith(".lz"):
            writes[tree / relative[:-3]] = lz77_decompress(source, offset)

    # The localized credits have 55 pages rather than the English 57 pages.
    entries = []
    for index in range(275):
        record = struct.unpack_from("<I", source, manifest["credits"] + index * 4)[0] - 0x08000000
        if not 0 <= record <= len(source) - 8:
            raise ValueError("Invalid credits record")
        raw = source[record:record + 8]
        offset = struct.unpack_from("<I", raw, 4)[0] - 0x08000000
        end = source.find(b"\xff", offset, offset + 200) if 0 <= offset < len(source) else -1
        if end < 0 or raw[0] > 40 or raw[1] not in (0, 1) or raw[2:4] != b"\0\0":
            raise ValueError("Invalid credits text")
        entries.append((record, offset, end + 1, raw[0], raw[1]))
    lines = ["enum { PAGE_COUNT = 55 };", "#define ENTRIES_PER_PAGE 5"]
    texts, records = {}, {}
    for record, offset, end, unknown, title in entries:
        if offset not in texts:
            texts[offset] = "sSpanishCreditsText_" + str(offset)
            lines.append("static const u8 " + texts[offset] + "[] = {" + encoded(source[offset:end]) + "};")
        if record not in records:
            records[record] = "sSpanishCreditsEntry_" + str(record)
            lines.append("static const struct CreditsEntry " + records[record] + " = {"
                         + str(unknown) + "," + str(title) + "," + texts[offset] + "};")
    lines.append("static const struct CreditsEntry *const sCreditsEntryPointerTable[PAGE_COUNT][ENTRIES_PER_PAGE] = {")
    for index in range(0, len(entries), 5):
        lines.append("{" + ",".join("&" + records[e[0]] for e in entries[index:index + 5]) + "},")
    lines.append("};")
    writes[tree / "src/data/credits.h"] = ("\n".join(lines) + "\n").encode()

    path = tree / "src/data/battle_frontier/trainer_hill.h"
    text = path.read_text(encoding="utf-8")
    for name, offset, size in manifest["floors"]:
        if size != 4 * 952 or not 0 <= offset < offset + size <= len(source):
            raise ValueError("Invalid Trainer Hill floor layout")
        match = re.search(r"static const struct TrainerHillFloor " + name + r"\[\]\s*=\s*\{", text)
        if match is None:
            raise ValueError("Missing floor definition: " + name)
        end, depth = match.end(), 1
        while depth:
            char = text[end]
            end += 1
            depth += (char == "{") - (char == "}")
        if text[end] != ";":
            raise ValueError("Invalid floor initializer")
        blob = "build/private_data/" + name + ".bin"
        writes[tree / blob] = source[offset:offset + size]
        assembly = ('.section .rodata.' + name + ',"a"\n.balign 4\n.global ' + name
                    + '\n.type ' + name + ', %object\n' + name + ':\n.incbin "' + blob
                    + '"\n.size ' + name + ', .-' + name + '\n')
        replacement = ("extern const struct TrainerHillFloor " + name + "[];\n"
                       '_Static_assert(sizeof(struct TrainerHillFloor) == 952, "TrainerHillFloor ABI differs");\n'
                       + "__asm__(" + json.dumps(assembly) + ");")
        text = text[:match.start()] + replacement + text[end + 1:]
    writes[path] = text.encode()
    path = tree / "include/constants/global.h"
    text = path.read_text(encoding="utf-8").replace("#define GAME_LANGUAGE (LANGUAGE_ENGLISH)",
                                    "#define GAME_LANGUAGE (LANGUAGE_SPANISH)")
    writes[path] = text.encode()
    writes[tree / "build/spanish-reference.s"] = gzip.decompress(
        (ROOT / "tools/locales/spanish-symbols.s.gz").read_bytes())
    # Validate all source and ROM references before modifying the staged tree.
    for path, data in writes.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (tree / ".emerald3ds-locale").write_text("BPES experimental\n")
    print("Spanish game data staged; console play testing is pending.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    args = parser.parse_args()
    stage(args.tree.resolve(), args.rom)


if __name__ == "__main__":
    main()
