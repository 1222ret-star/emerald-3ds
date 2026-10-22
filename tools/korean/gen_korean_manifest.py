#!/usr/bin/env python3
"""Generate the Korean text manifest for Emerald 3DS.

Matches every string definition of the patched pret tree to the Korean ROM:
  - C:   `u8 NAME[] = _("...");`                      -> kind "c"
  - asm: `NAME:` / `NAME::` followed by `.string` lines -> kind "asm"
The Korean address of NAME comes from relocmap.py (symbols_kor.tsv), or from
texts_jk.json (follow_pointers.py) for strings relocmap.py could not place.
An asm string still unplaced that nothing references is left empty. The
manifest stores source positions, ROM offsets and sizes only: no text.

  python gen_korean_manifest.py TREE SYMBOLS_KOR.tsv USA.gba KOR.gba OUT.json.gz [REPORT.tsv]
"""
from __future__ import annotations

import collections
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

ROM = 0x08000000
KOREAN_SHA1 = "17cd49e1af1184cd29355c674bedee7f5b72b055"
USABLE = ("same", "moved", "paired", "modified")

C_STRING = re.compile(
    r'\bu8\s+(\w+)\s*\[\s*\]\s*=\s*(_\(\s*(?:"(?:[^"\\\n]|\\.)*"\s*)+\))\s*;')
ASM_LABEL = re.compile(r'^(\w+)::?[ \t]*\n((?:[ \t]*\.string[ \t]+"(?:[^"\\\n]|\\.)*"[ \t]*(?:@[^\n]*)?\n)+)',
                       re.M)


LITERAL = r'(_\(\s*"(?:[^"\\\n]|\\.)*"\s*\))'
# Name tables: (source file, row regex, block start or None, Korean table
# symbol, Korean stride, field offset, field size). Row i of the source is row
# i of the table; the Korean ROM lengthened some fields (see patch 0059).
TABLES = [
    ("src/data/text/species_names.h", r"\[SPECIES_\w+\]\s*=\s*" + LITERAL, None, "gSpeciesNames", 11, 0, 11),
    ("src/data/text/move_names.h", r"\[MOVE_\w+\]\s*=\s*" + LITERAL, None, "gMoveNames", 17, 0, 17),
    ("src/battle_main.c", r"\[TYPE_\w+\]\s*=\s*" + LITERAL, "gTypeNames[", "gTypeNames", 7, 0, 7),
    ("src/data/text/abilities.h", r"\[ABILITY_\w+\]\s*=\s*" + LITERAL, "gAbilityNames[", "gAbilityNames", 13, 0, 13),
    ("src/data/text/trainer_class_names.h", r"\[TRAINER_CLASS_\w+\]\s*=\s*" + LITERAL, None,
     "gTrainerClassNames", 16, 0, 16),
    ("src/data/items.h", r"\.name\s*=\s*" + LITERAL, None, "gItems", 48, 0, 18),
    ("src/data/trainers.h", r"\.trainerName\s*=\s*" + LITERAL, None, "gTrainers", 40, 4, 12),
    ("src/data/pokemon/pokedex_entries.h", r"\.categoryName\s*=\s*" + LITERAL, None, "gPokedexEntries", 36, 0, 16),
    ("src/data/decoration/header.h", r"\.name\s*=\s*" + LITERAL, None, "gDecorations", 32, 1, 16),
]


def table_edits(tree: Path, by_name: dict, kor: bytes, stats: collections.Counter) -> dict:
    """Edits for the name tables, by file: [start, end, offset, size, "c"]."""
    found = {}
    for relative, row, block, symbol, stride, field, size in TABLES:
        text = (tree / relative).read_text(encoding="utf-8")
        begin, end = 0, len(text)
        if block:
            begin = text.index(block)
            end = text.index("};", begin)
        entries = by_name.get(symbol, [])
        if len(entries) != 1 or entries[0][1] is None:
            raise SystemExit("table not located: " + symbol)
        base = entries[0][1]
        edits = []
        for index, match in enumerate(re.finditer(row, text[begin:end])):
            offset = base + index * stride + field
            cell = kor[offset:offset + size]
            length = cell.index(0xFF) + 1 if 0xFF in cell else size
            start, stop = match.span(1)
            edits.append([begin + start, begin + stop, offset, length, "c"])
        stats["table rows (%s)" % symbol] = len(edits)
        found[relative] = edits
    return found


# Struct arrays holding names inline (`.trainerName = _("...")`): each literal
# is found in the USA object by its encoded bytes, in source order, and takes
# the Korean bytes at the same place (the Korean ROM keeps these layouts).
INLINE_TABLES = [
    ("src/data/battle_frontier/battle_frontier_trainers.h", "gBattleFrontierTrainers"),
    ("src/data/battle_frontier/battle_tent.h", "gSlateportBattleTentTrainers"),
    ("src/data/battle_frontier/battle_tent.h", "gVerdanturfBattleTentTrainers"),
    ("src/data/battle_frontier/battle_tent.h", "gFallarborBattleTentTrainers"),
    ("src/data/contest_opponents.h", "gContestOpponents"),
    ("src/data/battle_frontier/apprentice.h", "gApprentices"),
    ("src/data/battle_frontier/trainer_hill.h", "sFloors_Normal"),
    ("src/data/battle_frontier/trainer_hill.h", "sFloors_Variety"),
    ("src/data/battle_frontier/trainer_hill.h", "sFloors_Unique"),
    ("src/data/battle_frontier/trainer_hill.h", "sFloors_Expert"),
    ("src/berry.c", "gBerries"),
    ("src/battle_message.c", "sATypeMove_Table"),
]
LITERAL_IN_BLOCK = re.compile(r'(?<![\w_])_\(\s*"((?:[^"\\\n]|\\.)*)"\s*\)')


def load_charmap(tree: Path) -> dict[str, int]:
    chars = {}
    for line in (tree / "charmap.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^'(.)'\s*=\s*([0-9A-Fa-f]{2})\s*$", line)
        if m and m.group(1) not in chars:
            chars[m.group(1)] = int(m.group(2), 16)
    return chars


def encode_literal(text: str, chars: dict) -> bytes | None:
    try:
        return bytes(chars[c] for c in text) + b"\xff"
    except KeyError:
        return None  # escapes, control codes: not a plain name


def block_of(text: str, symbol: str) -> tuple[int, int]:
    begin = re.search(r"\b%s\s*\[[^\]]*\](?:\[[^\]]*\])*\s*=" % re.escape(symbol), text).end()
    depth, i = 0, text.index("{", begin)
    while True:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return begin, i + 1
        i += 1


def inline_edits(tree: Path, by_name: dict, usa: bytes, kor: bytes, stats: collections.Counter) -> dict:
    chars, found = load_charmap(tree), collections.defaultdict(list)
    for relative, symbol in INLINE_TABLES:
        entries = by_name.get(symbol, [])
        if len(entries) != 1 or entries[0][1] is None or entries[0][2] not in ("same", "moved", "paired"):
            stats["inline: table not located (%s)" % symbol] += 1
            continue
        usa_off, kor_off, _status = entries[0]
        text = (tree / relative).read_text(encoding="utf-8")
        begin, end = block_of(text, symbol)
        size = SYMBOL_SIZES[symbol]
        cursor = 0
        for m in LITERAL_IN_BLOCK.finditer(text, begin, end):
            data = encode_literal(m.group(1), chars)
            if data is None:
                continue
            at = usa.find(data, usa_off + cursor, usa_off + size)
            if at < 0:
                stats["inline: literal not in object"] += 1
                continue
            cursor = at - usa_off + len(data)
            k = kor_off + (at - usa_off)
            k_end = kor.find(b"\xff", k, k + 64)
            if k_end < 0 or kor[k:k_end + 1] == data:
                continue
            found[relative].append([m.start(), m.end(), k, k_end + 1 - k, "c"])
            stats["inline names (%s)" % symbol] += 1
    return found


# u16 arrays the Korean ROM changed (Easy Chat sentences, the alphabetical
# Pokedex order): every element takes the Korean value.
U16_ARRAY = re.compile(r"\bconst\s+u16\s+(\w+)\s*(?:\[[^\]]*\])+\s*=\s*\{")


def u16_edits(tree: Path, by_name: dict, usa: bytes, kor: bytes, stats: collections.Counter, taken: dict) -> dict:
    found = collections.defaultdict(list)
    for path in sorted((tree / "src").rglob("*.[ch]")):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(tree).as_posix()
        for m in U16_ARRAY.finditer(text):
            symbol = m.group(1)
            entries = by_name.get(symbol, [])
            if len(entries) != 1 or entries[0][1] is None or entries[0][2] not in ("same", "moved", "paired"):
                continue
            usa_off, kor_off, _status = entries[0]
            size = SYMBOL_SIZES.get(symbol, 0)
            if not size or usa[usa_off:usa_off + size] == kor[kor_off:kor_off + size]:
                continue
            begin, end = block_of(text, symbol)
            body = text[begin:end]
            if re.search(r"\[[^\]]*\]\s*=", body):
                stats["u16: designated initializers (%s)" % symbol] += 1
                continue
            # Elements: what lies between braces and commas (macros keep their parentheses).
            elements, depth, seg = [], 0, None
            for i, c in enumerate(body):
                if depth == 0 and c in "{},":
                    if seg is not None and body[seg:i].strip():
                        part = body[seg:i]
                        lead = len(part) - len(part.lstrip())
                        elements.append((begin + seg + lead, begin + seg + len(part.rstrip())))
                    seg = None
                    continue
                depth += {"(": 1, ")": -1}.get(c, 0)
                if seg is None:
                    seg = i
            if len(elements) * 2 != size:
                stats["u16: element count differs (%s)" % symbol] += 1
                continue
            if any(s < e2 and s2 < e for s2, e2, *_ in taken.get(relative, []) for s, e in elements):
                continue
            for index, (s, e) in enumerate(elements):
                offset = kor_off + 2 * index
                if usa[usa_off + 2 * index:usa_off + 2 * index + 2] != kor[offset:offset + 2]:
                    found[relative].append([s, e, offset, 2, "u16"])
            stats["u16 arrays"] += 1
    return found


# Window templates the Korean ROM re-laid out for Hangul (summary screen, Bag,
# party menu, battle windows, ...): each field takes the Korean value. Only
# blocks the port's patches left as in pret, and only where every literal
# field matches the USA ROM, so the entries line up.
WINDOW_TEMPLATE = re.compile(r"\bstruct\s+(WindowTemplate|SlidingWindow|TilemapCtrl)\s+(\w+)\s*(\[[^\]]*\])?\s*=\s*\{")
# struct: (size, {field: (offset, width), or None to leave alone}, positional order)
LAYOUT_STRUCTS = {
    "WindowTemplate": (8, {"bg": (0, 1), "tilemapLeft": (1, 1), "tilemapTop": (2, 1), "width": (3, 1),
                           "height": (4, 1), "paletteNum": (5, 1), "baseBlock": (6, 2)},
                       ["bg", "tilemapLeft", "tilemapTop", "width", "height", "paletteNum", "baseBlock"]),
    # The summary screen's sliding status and move effect windows.
    "SlidingWindow": (12, {"gfx": None, "defaultTile": (4, 2), "width": (6, 1), "height": (7, 1),
                           "left": (8, 1), "top": (9, 1)},
                      ["gfx", "defaultTile", "width", "height", "left", "top"]),
}
# The pinned pret source names it TilemapCtrl, the symbols SlidingWindow.
LAYOUT_STRUCTS["TilemapCtrl"] = LAYOUT_STRUCTS["SlidingWindow"]
# Source names whose symbols (pret's newer symbols branch) were renamed.
# Layouts kept as in pret, by symbol: None for all its entries, else the
# entry indices. The Korean dialogue boxes use the 11-wide font (patch 0066)
# in the English width; the summary's species line keeps the English width,
# where the port's code draws the gender symbol; the move Effect windows keep
# the port's height (patch 0065 builds the Category version).
WINDOW_KEEP = {"sNewGameBirchSpeechTextWindows": {0}, "sSummaryTemplate": {19},
               "sBattleMoveTilemapCtrl": None, "sContestMoveTilemapCtrl": None}
SYMBOL_ALIASES = {
    "sStatusTilemapCtrl1": "sStatusSlidingWindow1", "sStatusTilemapCtrl2": "sStatusSlidingWindow2",
    "sBattleMoveTilemapCtrl": "sPowerAccSlidingWindow", "sContestMoveTilemapCtrl": "sAppealJamSlidingWindow",
}


def top_level_parts(body: str, begin: int, separators: str = ",") -> list[tuple[int, int]]:
    """Spans of the comma-separated parts of a braced body, at depth 1."""
    parts, depth, seg = [], 0, None
    for i, c in enumerate(body):
        if c in "{(":
            depth += 1
            if depth == 1:
                seg = i + 1
                continue
        if c in "})":
            depth -= 1
        if depth == 1 and c in separators or depth == 0 and c == "}":
            if seg is not None and body[seg:i].strip():
                part = body[seg:i]
                lead = len(part) - len(part.lstrip())
                parts.append((begin + seg + lead, begin + seg + len(part.rstrip())))
            seg = i + 1
            if depth == 0:
                break
    return parts


def window_edits(tree: Path, by_name: dict, usa: bytes, kor: bytes, stats: collections.Counter, taken: dict) -> dict:
    import subprocess
    found = collections.defaultdict(list)
    for path in sorted((tree / "src").rglob("*.[ch]")):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(tree).as_posix()
        pristine = None
        for m in WINDOW_TEMPLATE.finditer(text):
            struct_name, symbol, is_array = m.group(1), m.group(2), m.group(3) is not None
            keep = WINDOW_KEEP.get(symbol, set())
            if keep is None:
                continue
            stride, field_table, field_order = LAYOUT_STRUCTS[struct_name]
            entries = by_name.get(SYMBOL_ALIASES.get(symbol, symbol), [])
            if len(entries) != 1 or entries[0][1] is None or entries[0][2] not in ("same", "moved", "paired", "modified"):
                continue
            usa_off, kor_off, status = entries[0]
            size = SYMBOL_SIZES.get(SYMBOL_ALIASES.get(symbol, symbol), 0)
            if not size or usa[usa_off:usa_off + size] == kor[kor_off:kor_off + size]:
                continue
            # A guessed place must still look like these templates (mostly the same values).
            same = sum(a == b for a, b in zip(usa[usa_off:usa_off + size], kor[kor_off:kor_off + size]))
            if status == "modified" and same < 0.7 * size:
                stats["windows: guessed place differs (%s)" % symbol] += 1
                continue
            begin = m.end() - 1
            end = block_of(text, symbol)[1] if is_array else text.index("};", begin) + 1
            if pristine is None:
                pristine = subprocess.run(["git", "show", "HEAD:" + relative], cwd=tree,
                                          capture_output=True).stdout.decode("utf-8", "replace")
            body = text[begin:end]
            entries_spans = top_level_parts(body, begin) if is_array else [(begin + 1, end - 1)]
            edits, ok = [], True
            for index, (s, e) in enumerate(entries_spans):
                if index in keep:
                    continue
                entry = text[s:e]
                # TilemapCtrl: renamed by the port (0005), pret's values; the
                # literal check below lines it up with the USA ROM.
                if entry not in pristine and struct_name != "TilemapCtrl":
                    # This entry was changed by a port patch: keep it as it is.
                    stats["windows: entry changed by the port (%s)" % symbol] += 1
                    continue
                entry = re.sub(r"^\[[^\]]*\]\s*=\s*", "", entry)
                if entry.startswith("DUMMY_WIN_TEMPLATE"):
                    continue
                base = stride * index
                inner_start = text.index("{", s, e) + 1 if is_array else s
                inner_end = text.rindex("}", s, e) if is_array else e
                fields = list(re.finditer(r"\.(\w+)\s*=\s*([^,}\n]+?)\s*(?=[,}\n])", text[inner_start:inner_end]))
                if fields:
                    items = [(f.group(1), inner_start + f.start(2), inner_start + f.end(2)) for f in fields]
                else:
                    values = top_level_parts("{" + text[inner_start:inner_end] + "}", inner_start - 1)
                    items = [(name, a, b) for name, (a, b) in zip(field_order, values)]
                for name, a, b in items:
                    if name not in field_table:
                        ok = False
                        break
                    if field_table[name] is None:
                        continue
                    offset, width = field_table[name]
                    u = int.from_bytes(usa[usa_off + base + offset:usa_off + base + offset + width], "little")
                    k = int.from_bytes(kor[kor_off + base + offset:kor_off + base + offset + width], "little")
                    try:
                        if int(text[a:b], 0) != u:
                            ok = False
                            break
                    except ValueError:
                        pass  # a macro or expression: not checked
                    if u != k:
                        edits.append([a, b, kor_off + base + offset, width, "u8" if width == 1 else "u16"])
                if not ok:
                    break
            if not ok:
                stats["windows: entries do not line up (%s)" % symbol] += 1
                continue
            if any(s < e2 and s2 < e for s2, e2, *_ in taken.get(relative, []) for s, e, *_r in edits):
                continue
            found[relative] += edits
            stats["windows re-laid out"] += 1
    return found


SYMBOL_SIZES: dict[str, int] = {}


INCBIN = re.compile(r'(\w+)\s*\[\s*\]\s*=\s*INCBIN_\w+\(\s*"((?:graphics|data)/[^"]+)"\s*\)')


def lz77_length(rom: bytes, offset: int) -> tuple[int, int]:
    """(compressed length, decompressed size) of GBA LZ77 data at offset."""
    if rom[offset] != 0x10:
        raise ValueError("no LZ77 header")
    size = rom[offset + 1] | rom[offset + 2] << 8 | rom[offset + 3] << 16
    pos, done = offset + 4, 0
    while done < size:
        flags = rom[pos]
        pos += 1
        for bit in range(8):
            if done >= size:
                break
            if flags & (0x80 >> bit):
                done += (rom[pos] >> 4) + 3
                pos += 2
            else:
                done += 1
                pos += 1
    return pos - offset, size


# INCBIN of several files: `NAME[]... = INCBIN_U16("a", "b", ...);`
INCBIN_MULTI = re.compile(r'(\w+)\s*(?:\[[^\]]*\])+\s*=\s*INCBIN_\w+\(((?:\s*"[^"]+"\s*,?)+)\)')


# Graphics of another size in the Korean ROM, with the code that loads them
# changed by a patch: symbol -> (file, Korean size).
GRAPHICS_RESIZED = {
    # Title version banner: 144 colors (patch 0062), not 16.
    "gTitleScreenEmeraldVersionPal": ("graphics/title_screen/emerald_version.gbapal", 144 * 2),
}


def source_size(tree: Path, relative: str) -> int | None:
    """Size of a built graphic from its source, so the pristine tree (nothing
    built yet) is enough: .gbapal <- JASC .pal, .4bpp/.8bpp/.1bpp <- .png."""
    path = tree / relative
    if path.is_file():
        return path.stat().st_size
    stem, ext = relative.rsplit(".", 1)
    if ext == "gbapal" and (tree / (stem + ".pal")).is_file():
        lines = (tree / (stem + ".pal")).read_text(encoding="utf-8", errors="replace").split()
        if lines[:1] != ["JASC-PAL"]:
            return None
        # A rule may keep fewer colors: `DIR/x.gbapal: %.gbapal: %.pal` + `-num_colors N`.
        directory, file = relative.rsplit("/", 1)
        rules = (tree / "graphics_file_rules.mk").read_text(encoding="utf-8")
        rules = re.sub(r"\$\((\w+)\)", lambda m: dict(re.findall(r"^(\w+)\s*:=\s*(\S+)", rules, re.M)).get(
            m.group(1), m.group(0)), rules)
        rule = re.search(r"^%s/%s:[^\n]*\n\t[^\n]*-num_colors\s+(\d+)" % (re.escape(directory), re.escape(file)),
                         rules, re.M)
        return int(rule.group(1) if rule else lines[2]) * 2
    if ext == "gbapal" and (tree / (stem + ".png")).is_file():
        # The palette of an indexed PNG: its PLTE chunk, 3 bytes per color.
        png = (tree / (stem + ".png")).read_bytes()
        at = png.find(b"PLTE")
        return int.from_bytes(png[at - 4:at], "big") // 3 * 2 if at >= 4 else None
    if ext in ("1bpp", "4bpp", "8bpp") and (tree / (stem + ".png")).is_file():
        head = (tree / (stem + ".png")).read_bytes()[:24]
        width, height = int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
        return width * height * int(ext[0]) // 8
    return None


def graphics_edits(tree: Path, by_name: dict, sizes: dict, usa: bytes, kor: bytes,
                   stats: collections.Counter) -> list:
    """[relative, offset, size] for every INCBIN graphic the Korean ROM changed
    (its Korean version: title logo, menu tiles, palettes, ...). The localize
    step writes the file, and the uncompressed one beside a .lz. A symbol made
    of several files is split by their sizes."""
    found = {}
    for name, (relative, size) in GRAPHICS_RESIZED.items():
        usa_off, kor_off, status = by_name[name][0]
        if kor_off is None or status != "paired":
            raise SystemExit("not located: " + name)
        found[relative] = [relative, kor_off, size]
        stats["graphics (resized)"] += 1
    for path in sorted((tree / "src").rglob("*.[ch]")):
        text = re.sub(r"//[^\n]*", "", path.read_text(encoding="utf-8", errors="replace"))
        for name, args in INCBIN_MULTI.findall(text):
            parts = re.findall(r'"([^"]+)"', args)
            if not all(p.startswith(("graphics/", "data/")) for p in parts):
                continue
            entries = by_name.get(name, [])
            if len(entries) != 1 or parts[0] in found:
                continue
            usa_off, kor_off, status = entries[0]
            if kor_off is None or status not in ("paired", "modified"):
                continue
            try:
                if len(parts) == 1 and parts[0].endswith(".lz"):
                    usa_len, usa_size = lz77_length(usa, usa_off)
                    kor_len, kor_size = lz77_length(kor, kor_off)
                    if usa_size != kor_size:
                        stats["graphics: other size"] += 1
                        continue
                    if kor[kor_off:kor_off + kor_len] == usa[usa_off:usa_off + usa_len]:
                        continue  # unchanged
                    found[parts[0]] = [parts[0], kor_off, kor_len]
                    stats["graphics (%s)" % status] += 1
                    continue
                if any(p.endswith(".lz") for p in parts):
                    continue
                # Raw data cannot be checked: a confirmed place only (paired,
                # or where the Korean ROM kept the USA address), and the parts
                # must add up to the symbol.
                if status != "paired" and kor_off != usa_off:
                    continue
                part_sizes = [source_size(tree, p) for p in parts]
                if None in part_sizes or sum(part_sizes) != sizes.get(name, sum(part_sizes)):
                    stats["graphics: unknown part sizes (%s)" % name] += 1
                    continue
                ku, kk = usa_off, kor_off
                for part, size in zip(parts, part_sizes):
                    if kor[kk:kk + size] != usa[ku:ku + size]:
                        found[part] = [part, kk, size]
                        stats["graphics (%s)" % status] += 1
                    ku += size
                    kk += size
            except (ValueError, IndexError):
                stats["graphics: not LZ77 in the Korean ROM"] += 1
    return sorted(found.values())


def string_end(rom: bytes, offset: int) -> int:
    end = rom.find(b"\xff", offset, offset + 0x2000)
    return -1 if end < 0 else end + 1


def placeholders(rom: bytes, offset: int, end: int) -> collections.Counter:
    """Placeholder ids ({FD xx}) of a string: a cheap sanity check across languages."""
    found, i = collections.Counter(), offset
    while i < end - 1:
        if rom[i] == 0xFD:
            found[rom[i + 1]] += 1
            i += 2
        elif rom[i] == 0xFC:
            i += 2
        elif 0x37 <= rom[i] <= 0x41:
            i += 2  # Hangul pair: its trail byte may look like anything
        else:
            i += 1
    return found


# Strings relocmap.py could not place, found through the pointers that
# reference them (follow_pointers.py): name -> [English, Korean address].
EXTRA_TEXTS = Path(__file__).resolve().parent / "texts_jk.json"
# Event-distribution scripts the 3DS never receives; their text is left
# empty rather than English (it would be English text in the recipe).
BLANK_ALSO = {"sText_MysteryGiftAlteringCave"}


def referenced(sources: list, texts: dict) -> collections.Counter:
    """How often each identifier appears in the tree's sources."""
    words = collections.Counter()
    for path in sources:
        words.update(re.findall(r"[A-Za-z_]\w*", texts[path]))
    return words


def main() -> None:
    tree, symbols_path, usa_path, kor_path, out = map(Path, sys.argv[1:6])
    report_path = Path(sys.argv[6]) if len(sys.argv) > 6 else None
    usa, kor = usa_path.read_bytes(), kor_path.read_bytes()
    if hashlib.sha1(kor).hexdigest() != KOREAN_SHA1:
        raise SystemExit("not the Korean ROM")

    by_name = collections.defaultdict(list)
    sizes = {}
    for line in open(symbols_path, encoding="utf-8").read().splitlines()[1:]:
        name, kind, size, usa_a, kor_a, status = line.split("\t")
        by_name[name].append((int(usa_a, 16) - ROM, int(kor_a, 16) - ROM if kor_a else None, status))
        sizes[name] = int(size)
    if EXTRA_TEXTS.exists():
        for name, (usa_a, kor_a) in json.loads(EXTRA_TEXTS.read_text(encoding="utf-8")).items():
            by_name[name] = [(int(usa_a, 16) - ROM, int(kor_a, 16) - ROM, "paired")]
    blank = kor.index(b"\xff")  # an empty string: just the terminator

    files: dict[str, dict] = {}
    report = []
    stats = collections.Counter()
    sources = sorted(list((tree / "src").rglob("*.c")) + list((tree / "src").rglob("*.h")) + list((tree / "data").rglob("*.inc"))
                     + list((tree / "data").rglob("*.s")))
    texts = {path: path.read_text(encoding="utf-8") for path in sources}
    uses = referenced(sources, texts)
    for path in sources:
        text = texts[path]
        relative = path.relative_to(tree).as_posix()
        kind = "c" if path.suffix in (".c", ".h") else "asm"
        pattern = C_STRING if kind == "c" else ASM_LABEL
        edits = []
        for match in pattern.finditer(text):
            name = match.group(1)
            stats["definitions"] += 1
            entries = by_name.get(name, [])
            usa_off, kor_off, status = entries[0] if len(entries) == 1 else (None, None, "")
            if len(entries) != 1 or kor_off is None or status not in USABLE:
                problem = "not located" if len(entries) == 1 else "ambiguous" if entries else "no symbol"
                # A string nothing uses (a leftover of Ruby/Sapphire) is
                # left empty rather than English.
                if kind == "asm" and (uses[name] == 1 or name in BLANK_ALSO):
                    start, end = match.span(2)
                    edits.append([start, end - 1, blank, 1, kind])
                    stats["blank (unused)"] += 1
                    report.append((relative, name, problem + ", left empty", status))
                    continue
                stats[problem] += 1
                report.append((relative, name, problem, status))
                continue
            usa_end, kor_end = string_end(usa, usa_off), string_end(kor, kor_off)
            if usa_end < 0 or kor_end < 0:
                stats["no terminator"] += 1
                report.append((relative, name, "no terminator", status))
                continue
            if usa[usa_off:usa_end] == kor[kor_off:kor_end]:
                stats["unchanged"] += 1
                continue
            if placeholders(usa, usa_off, usa_end) != placeholders(kor, kor_off, kor_end):
                stats["placeholder mismatch (%s)" % status] += 1
                report.append((relative, name, "placeholder mismatch", status))
                if status == "modified":
                    continue  # unconfirmed location: drop it
            start, end = match.span(2)
            if kind == "asm":
                end -= 1  # keep the label's final newline
            edits.append([start, end, kor_off, kor_end - kor_off, kind])
            stats["edits (%s)" % status] += 1
        if edits:
            files[relative] = {"sha256": hashlib.sha256(text.encode()).hexdigest(), "edits": edits}

    for relative, edits in table_edits(tree, by_name, kor, stats).items():
        text = (tree / relative).read_text(encoding="utf-8")
        entry = files.setdefault(relative, {"sha256": hashlib.sha256(text.encode()).hexdigest(), "edits": []})
        taken = [(s, e) for s, e, *_rest in entry["edits"]]
        for edit in edits:
            if any(s < edit[1] and edit[0] < e for s, e in taken):
                raise SystemExit("table edit overlaps a string edit in " + relative)
        entry["edits"] = sorted(entry["edits"] + edits)

    SYMBOL_SIZES.update(sizes)
    for extra in (inline_edits(tree, by_name, usa, kor, stats),):
        for relative, edits in extra.items():
            text = (tree / relative).read_text(encoding="utf-8")
            entry = files.setdefault(relative, {"sha256": hashlib.sha256(text.encode()).hexdigest(), "edits": []})
            taken = [(s, e) for s, e, *_rest in entry["edits"]]
            edits = [x for x in edits if not any(s < x[1] and x[0] < e for s, e in taken)]
            entry["edits"] = sorted(entry["edits"] + edits)
    taken = {relative: entry["edits"] for relative, entry in files.items()}
    for producer in (u16_edits, window_edits):
        taken = {relative: entry["edits"] for relative, entry in files.items()}
        for relative, edits in producer(tree, by_name, usa, kor, stats, taken).items():
            text = (tree / relative).read_text(encoding="utf-8")
            entry = files.setdefault(relative, {"sha256": hashlib.sha256(text.encode()).hexdigest(), "edits": []})
            entry["edits"] = sorted(entry["edits"] + edits)

    manifest = {"rom_sha1": KOREAN_SHA1, "files": files,
                "graphics": graphics_edits(tree, by_name, sizes, usa, kor, stats)}
    out.write_bytes(gzip.compress(json.dumps(manifest, separators=(",", ":")).encode(), 9))
    if report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("file\tname\tproblem\tstatus\n")
            for row in report:
                f.write("\t".join(row) + "\n")
    for key, value in sorted(stats.items()):
        print("%-34s %d" % (key, value))
    print("files with edits:", len(files))


if __name__ == "__main__":
    main()
