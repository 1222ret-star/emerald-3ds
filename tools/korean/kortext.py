"""Decode Korean-patch text (KS X 1001 two-byte Hangul + pret charmap basics) for inspection."""
HANGUL = [bytes([b0, b1]).decode("euc-kr") for b0 in range(0xB0, 0xC9) for b1 in range(0xA1, 0xFF)]
LATIN = {0x00: " ", 0xAB: "!", 0xAC: "?", 0xAD: ".", 0xAE: "-", 0xB0: "…", 0xB1: "“", 0xB2: "”",
         0xB4: "'", 0xB8: ",", 0xBA: "/", 0xF0: ":", 0xFE: "\\n", 0xFA: "\\l", 0xFB: "\\p"}
for i in range(10):
    LATIN[0xA1 + i] = str(i)
for i in range(26):
    LATIN[0xBB + i] = chr(65 + i)
    LATIN[0xD5 + i] = chr(97 + i)


def decode(data: bytes, start: int = 0, limit: int = 400) -> str:
    out, i = [], start
    while i < len(data) and i < start + limit and data[i] != 0xFF:
        c = data[i]
        if 0x37 <= c <= 0x40 and i + 1 < len(data):
            k = (c - 0x37) * 239 + data[i + 1] - 1
            out.append(HANGUL[k] if 0 <= k < len(HANGUL) else "[%02X%02X]" % (c, data[i + 1]))
            i += 2
        elif c == 0x41 and i + 1 < len(data):
            out.append("[J%02X]" % data[i + 1])
            i += 2
        elif c == 0xFD and i + 1 < len(data):
            out.append("{%02X}" % data[i + 1])
            i += 2
        elif c == 0xFC and i + 1 < len(data):
            out.append("{C%02X}" % data[i + 1])
            i += 2
        else:
            out.append(LATIN.get(c, "[%02X]" % c))
            i += 1
    return "".join(out)
