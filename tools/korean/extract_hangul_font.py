#!/usr/bin/env python3
"""Dump the Hangul fonts of a Korean fan-translated Pokemon Emerald ROM to PNG sheets.

Format (both known patches), found by disassembling the DecompressGlyph_* functions:
  - char code: 2 bytes, lead 0x37-0x41 + trail; IsHangul checks lead-0x37 <= 10
  - syllables: KS X 1001 order, index = (lead-0x37)*239 + trail-1  (trail 0x01-0xEF, 2350 syllables)
  - lead 0x41: extra glyphs (compatibility jamo, 0x4101-0x4128)
  - glyph: 64 bytes at table + (code-0x3700)*64, four 2bpp 8x8 tiles TL,TR,BL,BR,
    16 bytes each (2 bytes per row, pixel n = (byte >> 2*(n%4)) & 3, low byte first)
  - pixel values: 0 = padding, 1 = shadow, 2 = foreground, 3 = background
  - each table covers codes 0x3700-0x412F (0x28C00 bytes)

Only reads the ROM; needs no third-party packages.  Usage:
  python extract_hangul_font.py ROM.gba OUTDIR
"""
from __future__ import annotations

import hashlib
import struct
import sys
import zlib
from pathlib import Path

# SHA-1 -> (name, [(ROM offset, readers, tiles used, cell width, cell height)])
PROFILES = {
    # 20210221 Pokemon Emerald Version (E-K).xdelta applied to clean BPEE
    "81b13f7931a85c18f08c6de3c0202ab47d6c8f37": ("E-K 20210221", [
        (0x65DDD8, "DecompressGlyph @0x080064F0, @0x08006768", "TL+BL", 8, 13),
        (0x686DD8, "(not referenced)", "?", 0, 0),
        (0x6AF5D8, "DecompressGlyph @0x080068C4, @0x08006A24", "TL+TR+BL+BR", 11, 14),
        (0x6D81D8, "DecompressGlyph @0x0800662C", "TL+BL", 8, 15),
    ]),
    # 20260613 J-K applied to the Japanese ROM (BPEJ): the Korean build's base
    "17cd49e1af1184cd29355c674bedee7f5b72b055": ("J-K 20260613", [
        (0x659DDC, "DecompressGlyph @0x08006544", "TL+BL", 8, 13),
        (0x6829DC, "DecompressGlyph @0x08006A94", "TL+TR+BL+BR", 11, 0),
        (0x6AB5DC, "DecompressGlyph @0x08006914", "TL+TR+BL+BR", 11, 0),
        (0x6D41DC, "DecompressGlyph @0x08006680/0x08006C14/0x08006D80", "TL+BL", 8, 15),
        (0x6FCDDC, "DecompressGlyph @0x080067BC", "TL+TR+BL+BR", 9, 13),
    ]),
}
SYLLABLES = [bytes([b0, b1]).decode("euc-kr") for b0 in range(0xB0, 0xC9) for b1 in range(0xA1, 0xFF)]
EXTRA = range(0x4101, 0x4130)
SHADES = {0: 200, 1: 150, 2: 0, 3: 255}


def code_of(index: int) -> int:
    return ((0x37 + index // 239) << 8) | (index % 239 + 1)


def glyph_pixels(rom: bytes, table: int, code: int) -> list[list[int]]:
    base = table + (code - 0x3700) * 64
    rows = [[0] * 16 for _ in range(16)]
    for tile in range(4):
        tx, ty = tile % 2, tile // 2
        for y in range(8):
            for x in range(8):
                byte = rom[base + tile * 16 + y * 2 + x // 4]
                rows[ty * 8 + y][tx * 8 + x] = (byte >> (2 * (x % 4))) & 3
    return rows


def write_png(path: Path, image: list[list[int]]) -> None:
    height, width = len(image), len(image[0])
    raw = b"".join(b"\0" + bytes(row) for row in image)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def sheet(rom: bytes, table: int, codes: list[int], columns: int = 50, scale: int = 2) -> list[list[int]]:
    cell = 17
    rows = (len(codes) + columns - 1) // columns
    image = [[120] * (columns * cell * scale) for _ in range(rows * cell * scale)]
    for n, code in enumerate(codes):
        gx, gy = (n % columns) * cell, (n // columns) * cell
        for y, line in enumerate(glyph_pixels(rom, table, code)):
            for x, value in enumerate(line):
                for dy in range(scale):
                    row = image[(gy + y) * scale + dy]
                    for dx in range(scale):
                        row[(gx + x) * scale + dx] = SHADES[value]
    return image


def main() -> None:
    rom_path, out = Path(sys.argv[1]), Path(sys.argv[2])
    rom = rom_path.read_bytes()
    sha1 = hashlib.sha1(rom).hexdigest()
    if sha1 not in PROFILES:
        raise SystemExit("unknown ROM (SHA-1 %s); known: %s" % (sha1, ", ".join(PROFILES)))
    name, tables = PROFILES[sha1]
    print("ROM:", name)
    out.mkdir(parents=True, exist_ok=True)
    syllables = [code_of(i) for i in range(len(SYLLABLES))]
    for table, readers, tiles, width, height in tables:
        stem = "hangul_%06X" % table
        write_png(out / (stem + ".png"), sheet(rom, table, syllables))
        write_png(out / (stem + "_extra.png"), sheet(rom, table, list(EXTRA), columns=len(EXTRA), scale=4))
        print("%s  %s  tiles %s  %sx%s  -> %s.png" % (hex(table), readers, tiles, width or "?", height or "?", stem))
    (out / "syllable_order.txt").write_text(
        "".join(SYLLABLES[i] + ("\n" if i % 50 == 49 else "") for i in range(len(SYLLABLES))), encoding="utf-8")


if __name__ == "__main__":
    main()
