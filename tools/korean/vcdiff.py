#!/usr/bin/env python3
"""Minimal VCDIFF (RFC 3284) decoder for xdelta3 patches without secondary compression.

Besides applying a patch it can report each window's instructions, so the patch
doubles as a change map: ADD/RUN bytes are new data, COPY from the source segment
shows where original data was kept or moved.

  python vcdiff.py apply SOURCE PATCH OUT
  python vcdiff.py map SOURCE PATCH OUT.json
"""
from __future__ import annotations

import json
import sys
import zlib

VCD_SOURCE, VCD_TARGET, VCD_ADLER32 = 0x01, 0x02, 0x04
NOOP, ADD, RUN, COPY = 0, 1, 2, 3


def default_code_table():
    """RFC 3284 section 5.6."""
    table = [(RUN, 0, 0, NOOP, 0, 0)]
    table += [(ADD, size, 0, NOOP, 0, 0) for size in range(0, 18)]
    for mode in range(9):
        table.append((COPY, 0, mode, NOOP, 0, 0))
        table += [(COPY, size, mode, NOOP, 0, 0) for size in range(4, 19)]
    for mode in range(6):
        for add in range(1, 5):
            table += [(ADD, add, 0, COPY, size, mode) for size in range(4, 7)]
    for mode in range(6, 9):
        for add in range(1, 5):
            table.append((ADD, add, 0, COPY, 4, mode))
    for mode in range(9):
        table.append((COPY, 4, mode, ADD, 1, 0))
    assert len(table) == 256
    return table


class Reader:
    def __init__(self, data: bytes, pos: int = 0, end: int | None = None):
        self.data, self.pos, self.end = data, pos, len(data) if end is None else end

    def byte(self) -> int:
        value = self.data[self.pos]
        self.pos += 1
        return value

    def integer(self) -> int:
        value = 0
        while True:
            byte = self.byte()
            value = (value << 7) | (byte & 0x7F)
            if not byte & 0x80:
                return value

    def take(self, size: int) -> bytes:
        chunk = self.data[self.pos:self.pos + size]
        if len(chunk) != size:
            raise ValueError("truncated patch")
        self.pos += size
        return chunk


def decode(source: bytes, patch: bytes, record: list | None = None) -> bytes:
    if patch[:3] != b"\xd6\xc3\xc4":
        raise ValueError("not a VCDIFF file")
    r = Reader(patch, 4)
    indicator = r.byte()
    if indicator & 0x01:
        raise ValueError("secondary compression is not supported")
    if indicator & 0x02:
        raise ValueError("custom code tables are not supported")
    if indicator & 0x04:
        r.take(r.integer())  # xdelta3 application header (file names)
    table = default_code_table()
    out = bytearray()
    while r.pos < len(patch):
        win = r.byte()
        seg_len = seg_pos = 0
        if win & (VCD_SOURCE | VCD_TARGET):
            seg_len, seg_pos = r.integer(), r.integer()
        r.integer()  # delta encoding length
        target_len = r.integer()
        if r.byte():
            raise ValueError("compressed sections are not supported")
        data_len, inst_len, addr_len = r.integer(), r.integer(), r.integer()
        checksum = r.take(4) if win & VCD_ADLER32 else None
        data = Reader(r.take(data_len))
        inst = Reader(r.take(inst_len))
        addr = Reader(r.take(addr_len))
        if win & VCD_SOURCE:
            segment = source[seg_pos:seg_pos + seg_len]
        elif win & VCD_TARGET:
            segment = bytes(out[seg_pos:seg_pos + seg_len])
        else:
            segment = b""
        start = len(out)
        target = bytearray()
        near, same = [0] * 4, [0] * (3 * 256)
        near_slot = 0

        def copy_address(mode: int, here: int) -> int:
            nonlocal near_slot
            if mode == 0:
                a = addr.integer()
            elif mode == 1:
                a = here - addr.integer()
            elif mode < 6:
                a = near[mode - 2] + addr.integer()
            else:
                a = same[(mode - 6) * 256 + addr.byte()]
            near[near_slot] = a
            near_slot = (near_slot + 1) % 4
            same[a % len(same)] = a
            return a

        while inst.pos < inst.end:
            code = table[inst.byte()]
            for kind, size, mode in ((code[0], code[1], code[2]), (code[3], code[4], code[5])):
                if kind == NOOP:
                    continue
                if size == 0:
                    size = inst.integer()
                where = len(target)
                if kind == ADD:
                    target += data.take(size)
                    if record is not None:
                        record.append(("add", start + where, size))
                elif kind == RUN:
                    target += data.take(1) * size
                    if record is not None:
                        record.append(("run", start + where, size))
                else:
                    a = copy_address(mode, len(segment) + where)
                    for i in range(size):
                        pos = a + i
                        target.append(segment[pos] if pos < len(segment) else target[pos - len(segment)])
                    if record is not None:
                        if a < len(segment) and win & VCD_SOURCE:
                            record.append(("copy", start + where, size, seg_pos + a))
                        else:
                            record.append(("self", start + where, size))
        if len(target) != target_len:
            raise ValueError("window length mismatch")
        if checksum is not None and zlib.adler32(bytes(target)).to_bytes(4, "big") != checksum:
            raise ValueError("window checksum mismatch at target offset 0x%X" % start)
        out += target
    return bytes(out)


def main() -> None:
    command, source, patch, out = sys.argv[1:5]
    src, pat = open(source, "rb").read(), open(patch, "rb").read()
    if command == "apply":
        open(out, "wb").write(decode(src, pat))
    elif command == "map":
        record: list = []
        decode(src, pat, record)
        json.dump(record, open(out, "w"))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
