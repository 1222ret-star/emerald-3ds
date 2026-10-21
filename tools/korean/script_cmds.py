"""Gen 3 event script commands: opcode -> argument layout, read from pret's
asm/macros/event.inc and data/script_cmd_table.inc, and a decoder.

A layout is a list of argument sizes in bytes (1, 2, 4); trainerbattle's
depends on its type and is handled in decode().
"""
from __future__ import annotations

import re
from pathlib import Path

SIZES = {".byte": 1, ".2byte": 2, ".hword": 2, ".short": 2, ".4byte": 4, ".int": 4, ".word": 4}
# Commands after which execution does not fall through.
TERMINATORS = {"SCR_OP_END", "SCR_OP_RETURN", "SCR_OP_GOTO", "SCR_OP_GOTO_STD", "SCR_OP_RETURN_RAM",
               "SCR_OP_GOTO_IF_UNLOCKED"}
# Layouts the macros build from helper macros (formatwarp, map, stringvar).
MANUAL = {
    "SCR_OP_SETVAR": [2, 2], "SCR_OP_APPLYMOVEMENT": [2, 4], "SCR_OP_APPLYMOVEMENTAT": [2, 4, 1, 1],
    "SCR_OP_WAITMOVEMENT": [2], "SCR_OP_WAITMOVEMENTAT": [2, 1, 1], "SCR_OP_REMOVEOBJECT": [2],
    "SCR_OP_REMOVEOBJECTAT": [2, 1, 1], "SCR_OP_ADDOBJECT": [2], "SCR_OP_ADDOBJECTAT": [2, 1, 1],
    "SCR_OP_SHOWOBJECTAT": [2, 1, 1], "SCR_OP_HIDEOBJECTAT": [2, 1, 1],
    "SCR_OP_SETOBJECTSUBPRIORITY": [2, 1, 1, 1], "SCR_OP_RESETOBJECTSUBPRIORITY": [2, 1, 1],
    "SCR_OP_BUFFERLEADMONSPECIESNAME": [1], "SCR_OP_BUFFERSTRING": [1, 4], "SCR_OP_VBUFFERSTRING": [1, 4],
    "SCR_OP_BUFFERITEMNAMEPLURAL": [1, 2, 2],
}
WARP = [1, 1, 1, 2, 2]  # map group, map num, warp id, x, y
TRAINERBATTLE_POINTERS = {0: 2, 1: 3, 2: 3, 3: 1, 4: 3, 5: 2, 6: 4, 7: 3, 8: 4, 9: 2, 10: 2, 11: 2, 12: 2}


def load(tree: Path) -> dict[int, tuple[str, list | None]]:
    table = (tree / "data/script_cmd_table.inc").read_text(encoding="utf-8")
    names = re.findall(r"^\s*script_cmd_table_entry\s+(SCR_OP_\w+)", table, re.M)
    opcodes = {name: index for index, name in enumerate(names)}
    text = (tree / "asm/macros/event.inc").read_text(encoding="utf-8")
    commands: dict[int, tuple[str, list | None]] = {}
    for m in re.finditer(r"^\s*\.macro\s+(\w+)[^\n]*\n(.*?)^\s*\.endm", text, re.M | re.S):
        lines = [l.split("@")[0].split("/*")[0].strip() for l in m.group(2).splitlines()]
        lines = [l for l in lines if l]
        if not lines or not lines[0].startswith(".byte SCR_OP_"):
            continue
        name = lines[0].split()[1]
        if name not in opcodes or opcodes[name] in commands:
            continue
        layout: list | None = []
        for line in lines[1:]:
            word = line.split()[0]
            if word in SIZES:
                layout.append(SIZES[word])
            elif word == "formatwarp":
                layout += WARP
            elif word == "map":
                layout += [1, 1]
            elif word == "stringvar":
                layout.append(1)
            else:
                layout = None
                break
        commands[opcodes[name]] = (name, layout)
    for name, layout in MANUAL.items():
        if name in opcodes:
            commands[opcodes[name]] = (name, layout)
    return commands


def decode(rom: bytes, offset: int, commands: dict, limit: int, stop_after: int = 1):
    """Commands from offset: [(opcode, [(arg offset, size, value)])], up to the
    stop_after-th terminator, limit bytes, or an unknown opcode."""
    out, pos, terminators = [], offset, 0
    while pos < offset + limit and pos < len(rom):
        op = rom[pos]
        entry = commands.get(op)
        if entry is None:
            break
        name, layout = entry
        if layout is None:
            if name != "SCR_OP_TRAINERBATTLE":
                break
            kind = rom[pos + 1]
            if kind not in TRAINERBATTLE_POINTERS:
                break
            layout = [1, 2, 2] + [4] * TRAINERBATTLE_POINTERS[kind]
        args, at = [], pos + 1
        for size in layout:
            args.append((at, size, int.from_bytes(rom[at:at + size], "little")))
            at += size
        out.append((op, args))
        pos = at
        if name in TERMINATORS:
            terminators += 1
            if terminators >= stop_after:
                break
    return out


def end_of(ops, start: int) -> int:
    """Offset just past the decoded commands."""
    pos = start
    for _op, args in ops:
        pos = args[-1][0] + args[-1][1] if args else pos + 1
    return pos
