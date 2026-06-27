#!/usr/bin/env python3
"""Rebuild Ren'Py translate strings blocks from clean generated templates."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


COMMENT_RE = re.compile(r"^\s*#\s+(?P<comment>game/.*\.rpy:\d+)\s*$")
OLD_RE = re.compile(r'^(?P<indent>[ \t]*)old[ \t]+(?P<quote>"(?:\\.|[^"\\])*")(?P<suffix>.*)$')
NEW_RE = re.compile(r'^(?P<indent>[ \t]*)new[ \t]+(?P<quote>"(?:\\.|[^"\\])*")(?P<suffix>.*)$')
STRINGS_START_RE = re.compile(r"^translate\s+[A-Za-z0-9_-]+\s+strings:\s*$")
TRANSLATE_START_RE = re.compile(r"^translate\s+[A-Za-z0-9_-]+\s+(?!strings:)\S+:\s*$")


@dataclass(frozen=True)
class Entry:
    rel_file: str
    comment: str | None
    old_quote: str
    old_text: str


def decode_quote(quote: str) -> str:
    try:
        return ast.literal_eval(quote)
    except Exception:
        return bytes(quote[1:-1], "utf-8").decode("unicode_escape", errors="replace")


def encode_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"') + '"'


def project_root(root: Path) -> Path:
    root = root.resolve()
    if (root / "game").is_dir():
        return root
    if root.name == "game":
        return root.parent
    raise SystemExit(f"Could not find project root for: {root}")


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def collect_template_entries(template_root: Path) -> dict[str, list[Entry]]:
    by_file: dict[str, list[Entry]] = {}
    global_seen: set[str] = set()

    for path in sorted(template_root.rglob("*.rpy")):
        rel_file = path.relative_to(template_root).as_posix()
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        in_strings = False
        pending_comment: str | None = None

        for line in lines:
            if STRINGS_START_RE.match(line):
                in_strings = True
                pending_comment = None
                continue
            if in_strings and TRANSLATE_START_RE.match(line):
                in_strings = False
                pending_comment = None
            if not in_strings:
                continue

            comment = COMMENT_RE.match(line)
            if comment:
                pending_comment = comment.group("comment")
                continue

            old = OLD_RE.match(line)
            if old:
                old_quote = old.group("quote")
                old_text = decode_quote(old_quote)
                if old_text not in global_seen:
                    by_file.setdefault(rel_file, []).append(
                        Entry(rel_file=rel_file, comment=pending_comment, old_quote=old_quote, old_text=old_text)
                    )
                    global_seen.add(old_text)
                pending_comment = None
                continue

            if line.strip():
                pending_comment = None

    return by_file


def collect_existing_translations(target_root: Path) -> dict[str, str]:
    translations: dict[str, str] = {}
    for path in sorted(target_root.rglob("*.rpy")):
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        pending_old: str | None = None
        in_strings = False
        for line in lines:
            if STRINGS_START_RE.match(line):
                in_strings = True
                pending_old = None
                continue
            if in_strings and TRANSLATE_START_RE.match(line):
                in_strings = False
                pending_old = None
            if not in_strings:
                continue

            old = OLD_RE.match(line)
            if old:
                pending_old = decode_quote(old.group("quote"))
                continue
            new = NEW_RE.match(line)
            if new and pending_old is not None:
                translations.setdefault(pending_old, decode_quote(new.group("quote")))
                pending_old = None
                continue
            if line.strip() and not line.lstrip().startswith("#"):
                pending_old = None
    return translations


def remove_string_blocks(lines: list[str]) -> tuple[list[str], int | None, int]:
    output: list[str] = []
    first_index: int | None = None
    removed = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        if not STRINGS_START_RE.match(line):
            output.append(line)
            index += 1
            continue

        if first_index is None:
            first_index = len(output)
        removed += 1
        index += 1
        while index < len(lines):
            if re.match(r"^translate\s+[A-Za-z0-9_-]+\s+\S+", lines[index]):
                break
            index += 1
        while output and output[-1] == "":
            output.pop()
        if index < len(lines) and output:
            output.append("")
    return output, first_index, removed


def render_block(language: str, entries: list[Entry], translations: dict[str, str], empty_missing: bool) -> list[str]:
    if not entries:
        return []
    lines = [f"translate {language} strings:", ""]
    for entry in entries:
        if entry.comment:
            lines.append(f"    # {entry.comment}")
        lines.append(f"    old {entry.old_quote}")
        target = translations.get(entry.old_text, "" if empty_missing else entry.old_text)
        lines.append(f"    new {encode_quote(target)}")
        lines.append("")
    return lines


def rebuild_file(
    target_path: Path,
    root: Path,
    language: str,
    entries: list[Entry],
    translations: dict[str, str],
    empty_missing: bool,
    apply: bool,
) -> dict[str, Any]:
    original = target_path.read_text(encoding="utf-8-sig", errors="replace").splitlines() if target_path.exists() else []
    stripped, insert_at, removed_blocks = remove_string_blocks(original)
    block = render_block(language, entries, translations, empty_missing)
    if insert_at is None:
        insert_at = len(stripped)
        if stripped and stripped[-1] != "":
            block = [""] + block

    rebuilt = stripped[:insert_at] + block + stripped[insert_at:]
    changed = rebuilt != original
    if apply and changed:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("\n".join(rebuilt).rstrip() + "\n", encoding="utf-8")
    return {
        "file": rel(target_path, root),
        "entries": len(entries),
        "removed_blocks": removed_blocks,
        "changed": changed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Ren'Py project root or game directory")
    parser.add_argument("--language", default="chinese")
    parser.add_argument("--template-root", type=Path, required=True, help="Clean generated tl/<language> template root")
    parser.add_argument("--apply", action="store_true", help="Write rebuilt string blocks; default is dry-run")
    parser.add_argument(
        "--empty-missing",
        action="store_true",
        help="Use empty new strings when no existing translation exists; default copies source",
    )
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    root = project_root(args.root)
    target_root = root / "game" / "tl" / args.language
    if not target_root.is_dir():
        raise SystemExit(f"Target translation layer does not exist: {target_root}")

    templates = collect_template_entries(args.template_root.resolve())
    translations = collect_existing_translations(target_root)
    results = []
    for rel_file, entries in sorted(templates.items()):
        results.append(
            rebuild_file(
                target_root / rel_file,
                root,
                args.language,
                entries,
                translations,
                args.empty_missing,
                args.apply,
            )
        )

    report = {
        "root": str(root),
        "language": args.language,
        "template_root": str(args.template_root.resolve()),
        "applied": args.apply,
        "template_files": len(templates),
        "template_entries": sum(len(items) for items in templates.values()),
        "existing_translations": len(translations),
        "changed_files": sum(1 for item in results if item["changed"]),
        "files": results,
    }
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
