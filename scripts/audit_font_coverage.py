#!/usr/bin/env python3
"""Check whether a font covers CJK characters used by a Ren'Py translation."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path


def u16(data: bytes, offset: int) -> int:
    return struct.unpack(">H", data[offset : offset + 2])[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack(">I", data[offset : offset + 4])[0]


def table_offsets(data: bytes, font_offset: int) -> dict[str, tuple[int, int]]:
    count = u16(data, font_offset + 4)
    records: dict[str, tuple[int, int]] = {}
    pos = font_offset + 12
    for _ in range(count):
        tag = data[pos : pos + 4].decode("latin1")
        records[tag] = (u32(data, pos + 8), u32(data, pos + 12))
        pos += 16
    return records


def font_offsets(data: bytes) -> list[int]:
    if data[:4] == b"ttcf":
        return [u32(data, 12 + 4 * i) for i in range(u32(data, 8))]
    return [0]


def collect_cmap(data: bytes) -> set[int]:
    covered: set[int] = set()
    for font_offset in font_offsets(data):
        tables = table_offsets(data, font_offset)
        if "cmap" not in tables:
            continue
        cmap_offset, _ = tables["cmap"]
        subtable_count = u16(data, cmap_offset + 2)
        subtables: list[tuple[int, int]] = []

        for index in range(subtable_count):
            pos = cmap_offset + 4 + index * 8
            platform = u16(data, pos)
            sub_offset = cmap_offset + u32(data, pos + 4)
            fmt = u16(data, sub_offset)
            if platform in (0, 3) and fmt in (4, 12, 13):
                subtables.append((fmt, sub_offset))

        for fmt, offset in subtables:
            if fmt == 4:
                seg_count = u16(data, offset + 6) // 2
                end_codes = offset + 14
                start_codes = end_codes + 2 + seg_count * 2
                for index in range(seg_count):
                    start = u16(data, start_codes + 2 * index)
                    end = u16(data, end_codes + 2 * index)
                    if start == 0xFFFF and end == 0xFFFF:
                        continue
                    covered.update(range(start, end + 1))
            else:
                groups = u32(data, offset + 12)
                pos = offset + 16
                for _ in range(groups):
                    start = u32(data, pos)
                    end = u32(data, pos + 4)
                    covered.update(range(start, end + 1))
                    pos += 12

    return covered


def is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x3400 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x2FFFF
    )


def collect_translation_chars(root: Path, language: str) -> set[int]:
    tl_root = root / "game" / "tl" / language
    if not tl_root.is_dir():
        raise SystemExit(f"translation directory not found: {tl_root}")

    chars: set[int] = set()
    for path in tl_root.rglob("*.rpy"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        chars.update(ord(char) for char in text if is_cjk(char))
    return chars


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="Ren'Py project root")
    parser.add_argument("--language", default="chinese")
    parser.add_argument("--font", type=Path, required=True, help="font path, absolute or relative to root")
    args = parser.parse_args()

    root = args.root.resolve()
    font_path = args.font if args.font.is_absolute() else root / args.font
    if not font_path.is_file():
        raise SystemExit(f"font not found: {font_path}")

    chars = collect_translation_chars(root, args.language)
    covered = collect_cmap(font_path.read_bytes())
    missing = sorted(chars - covered)

    print(f"translation_cjk_chars={len(chars)}")
    print(f"covered={len(chars) - len(missing)}")
    print(f"missing={len(missing)}")
    if missing:
        print("missing_sample=" + "".join(chr(code) for code in missing[:120]))
    else:
        print("missing_sample=")

    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
