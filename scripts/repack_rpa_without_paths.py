from __future__ import annotations

import argparse
import os
import pickle
import random
import shutil
import tempfile
import zlib
from pathlib import Path

from extract_rpa import load_index


def read_archive_member(archive_path: Path, name: str, entries: list[tuple[int, int, bytes | str]]) -> bytes:
    offset, length, prefix = entries[0]
    if isinstance(prefix, str):
        prefix = prefix.encode("latin1")

    with archive_path.open("rb") as handle:
        handle.seek(offset)
        return prefix + handle.read(length - len(prefix))


def should_skip(name: str, prefixes: list[str]) -> bool:
    normalized = name.replace("\\", "/").lower()
    return any(normalized.startswith(prefix) for prefix in prefixes)


def repack(archive_path: Path, output_path: Path, skip_prefixes: list[str]) -> tuple[int, int]:
    index = load_index(archive_path)
    key = random.randint(1, 0x7FFFFFFF)
    new_index: dict[str, list[tuple[int, int]]] = {}
    kept = 0
    skipped = 0

    with output_path.open("wb") as out:
        out.write(b"RPA-3.0 0000000000000000 00000000\n")

        for name in sorted(index):
            if should_skip(name, skip_prefixes):
                skipped += 1
                continue

            data = read_archive_member(archive_path, name, index[name])
            offset = out.tell()
            out.write(data)
            new_index[name] = [(offset ^ key, len(data) ^ key)]
            kept += 1

        index_offset = out.tell()
        out.write(zlib.compress(pickle.dumps(new_index, protocol=2)))
        out.seek(0)
        out.write(f"RPA-3.0 {index_offset:016x} {key:08x}\n".encode("ascii"))

    return kept, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Repack an RPA archive while omitting selected path prefixes.")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--skip-prefix", action="append", default=[], help="Path prefix to omit, e.g. tl/chinese/")
    parser.add_argument("--backup-dir", type=Path, required=True)
    args = parser.parse_args()

    archive = args.archive.resolve()
    if not archive.exists():
        raise FileNotFoundError(archive)

    backup_dir = args.backup_dir.resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / archive.name
    if backup_path.exists():
        raise FileExistsError(f"Backup already exists: {backup_path}")

    skip_prefixes = [prefix.replace("\\", "/").lower().rstrip("/") + "/" for prefix in args.skip_prefix]
    if not skip_prefixes:
        raise ValueError("At least one --skip-prefix is required.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".rpa", dir=str(archive.parent)) as tmp:
        tmp_path = Path(tmp.name)

    try:
        kept, skipped = repack(archive, tmp_path, skip_prefixes)
        shutil.copy2(archive, backup_path)
        os.replace(tmp_path, archive)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    print(f"Repacked {archive}")
    print(f"Kept: {kept}")
    print(f"Skipped: {skipped}")
    print(f"Backup: {backup_path}")


if __name__ == "__main__":
    main()
