#!/usr/bin/env python3
"""Apply deterministic, syntax-safe repairs to Ren'Py translation files."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SOURCE_COMMENT_RE = re.compile(
    r'^(?P<indent>[ \t]*)# (?:(?P<speaker>[A-Za-z_][A-Za-z0-9_]*)[ \t]+)?'
    r'(?P<quote>"(?:\\.|[^"\\])*")(?P<suffix>.*)$'
)
TARGET_RE = re.compile(
    r'^(?P<indent>[ \t]*)(?:(?P<speaker>[A-Za-z_][A-Za-z0-9_]*)[ \t]+)?'
    r'(?P<quote>"(?:\\.|[^"\\])*")(?P<suffix>.*)$'
)
OLD_RE = re.compile(r'^(?P<indent>[ \t]*)old[ \t]+(?P<quote>"(?:\\.|[^"\\])*")(?P<suffix>.*)$')
NEW_RE = re.compile(r'^(?P<indent>[ \t]*)new[ \t]+(?P<quote>"(?:\\.|[^"\\])*")(?P<suffix>.*)$')
PRINTF_SAFE_NEXT = set("%bcdeEfFgGnosxXrdiuHMSaAwWyYIUpZzjxXc(")

SHORT_UI_MAP = {
    "On": "开",
    "Off": "关",
    "Yes": "是",
    "No": "否",
    "Back": "返回",
    "Return": "返回",
    "Start": "开始",
    "Load": "读取",
    "Save": "保存",
    "Auto": "自动",
    "Skip": "快进",
    "History": "历史",
    "Preferences": "设置",
    "Settings": "设置",
    "Quit": "退出",
    "Main Menu": "主菜单",
    "About": "关于",
    "Help": "帮助",
    "<": "<",
    ">": ">",
    "...": "...",
    "...!": "...!",
    "(...)": "(...)",
}


@dataclass
class Change:
    file: str
    line: int
    kind: str
    before: str
    after: str


def project_root(root: Path) -> Path:
    root = root.resolve()
    if (root / "game").is_dir():
        return root
    if root.name == "game":
        return root.parent
    raise SystemExit(f"Could not find project root for: {root}")


def tl_root(root: Path, language: str) -> Path:
    path = project_root(root) / "game" / "tl" / language
    if not path.is_dir():
        raise SystemExit(f"Translation layer does not exist: {path}")
    return path


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def decode_quote(quote: str) -> str:
    try:
        return ast.literal_eval(quote)
    except Exception:
        return bytes(quote[1:-1], "utf-8").decode("unicode_escape", errors="replace")


def encode_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"') + '"'


def escape_literal_percent(text: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char != "%":
            out.append(char)
            index += 1
            continue

        next_char = text[index + 1] if index + 1 < len(text) else ""
        if next_char == "%":
            out.append("%%")
            index += 2
        elif next_char in PRINTF_SAFE_NEXT:
            out.append("%")
            index += 1
        else:
            out.append("%%")
            index += 1
    return "".join(out)


def rewrite_target_line(line: str, text: str) -> str | None:
    new = NEW_RE.match(line)
    if new:
        return new.group("indent") + "new " + encode_quote(text) + new.group("suffix")

    target = TARGET_RE.match(line)
    if target and not line.lstrip().startswith(("old ", "#")):
        speaker = target.group("speaker")
        return (
            target.group("indent")
            + ((speaker + " ") if speaker else "")
            + encode_quote(text)
            + target.group("suffix")
        )
    return None


def repair_file(path: Path, root: Path, apply: bool) -> list[Change]:
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    changes: list[Change] = []
    pending_source: str | None = None

    for index, line in enumerate(lines):
        stripped = line.lstrip()
        source = SOURCE_COMMENT_RE.match(line)
        if source:
            pending_source = decode_quote(source.group("quote"))
            continue

        old = OLD_RE.match(line)
        if old:
            pending_source = decode_quote(old.group("quote"))
            continue

        match = NEW_RE.match(line) or (TARGET_RE.match(line) if not stripped.startswith("#") else None)
        if not match:
            if stripped:
                pending_source = None
            continue

        text = decode_quote(match.group("quote"))
        new_text = escape_literal_percent(text)

        if pending_source and text == "" and pending_source in SHORT_UI_MAP:
            new_text = SHORT_UI_MAP[pending_source]

        if new_text != text:
            new_line = rewrite_target_line(line, new_text)
            if new_line is not None:
                changes.append(
                    Change(
                        file=rel(path, root),
                        line=index + 1,
                        kind="target_repair",
                        before=text,
                        after=new_text,
                    )
                )
                if apply:
                    lines[index] = new_line

        if stripped:
            pending_source = None

    if apply and changes:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Ren'Py project root or game directory")
    parser.add_argument("--language", default="chinese")
    parser.add_argument("--apply", action="store_true", help="Write repairs; default is dry-run")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args()

    root = project_root(args.root)
    base = tl_root(root, args.language)
    changes: list[Change] = []
    for path in sorted(base.rglob("*.rpy")):
        changes.extend(repair_file(path, root, args.apply))

    report: dict[str, Any] = {
        "root": str(root),
        "language": args.language,
        "applied": args.apply,
        "changes": [change.__dict__ for change in changes],
        "changed_lines": len(changes),
        "changed_files": len({change.file for change in changes}),
    }
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
