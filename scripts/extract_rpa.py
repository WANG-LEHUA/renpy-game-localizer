from __future__ import annotations

import argparse
import os
import pickle
import zlib
from pathlib import Path


def load_index(archive_path: Path):
    with archive_path.open("rb") as f:
        header = f.readline()

        if header.startswith(b"RPA-3.0 "):
            offset = int(header[8:24], 16)
            key = int(header[25:33], 16)
            f.seek(offset)
            index = pickle.loads(zlib.decompress(f.read()), encoding="latin1")
            return {
                name: [
                    (entry[0] ^ key, entry[1] ^ key, entry[2] if len(entry) > 2 else b"")
                    for entry in entries
                ]
                for name, entries in index.items()
            }

        if header.startswith(b"RPA-2.0 "):
            offset = int(header[8:], 16)
            f.seek(offset)
            return pickle.loads(zlib.decompress(f.read()), encoding="latin1")

    raise ValueError(f"Unsupported archive format: {archive_path}")


def safe_output_path(output_root: Path, archive_name: str) -> Path:
    rel = Path(archive_name.replace("\\", "/"))
    target = (output_root / rel).resolve()
    root = output_root.resolve()

    if not str(target).startswith(str(root) + os.sep) and target != root:
        raise ValueError(f"Unsafe archive path: {archive_name}")

    return target


def extract(archive_path: Path, output_root: Path, suffix: str | None) -> int:
    index = load_index(archive_path)
    count = 0

    with archive_path.open("rb") as f:
        for name in sorted(index):
            if suffix and not name.lower().endswith(suffix.lower()):
                continue

            entry = index[name][0]
            offset, length = entry[0], entry[1]
            prefix = entry[2] if len(entry) > 2 else b""

            if isinstance(prefix, str):
                prefix = prefix.encode("latin1")

            f.seek(offset)
            data = prefix + f.read(length - len(prefix))

            target = safe_output_path(output_root, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            count += 1

    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract files from a Ren'Py .rpa archive.")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, default=Path("."))
    parser.add_argument("--suffix", help="Only extract files with this suffix, for example .rpyc")
    args = parser.parse_args()

    count = extract(args.archive, args.output, args.suffix)
    print(f"Extracted {count} file(s) from {args.archive}")


if __name__ == "__main__":
    main()
