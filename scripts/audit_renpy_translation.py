#!/usr/bin/env python3
"""Audit a Ren'Py translation tree for common localization defects."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


QUOTED_RE = re.compile(
    r'^(?P<indent>\s*)(?P<prefix>(?:old|new|[A-Za-z_]\w*)\s+)?'
    r'(?P<quote>["\'])(?P<text>.*)(?P=quote)\s*(?:#.*)?$'
)
VARIABLE_RE = re.compile(r"\[[^\[\]]+\]")
TAG_RE = re.compile(r"\{/?[A-Za-z][^{}]*\}")
CHINESE_RE = re.compile(r"[\u3400-\u9fff]")
LATIN_WORD_RE = re.compile(r"[A-Za-z]{4,}")
MOJIBAKE_RE = re.compile(r"�|鈥|銆|锛|馃|Â|Ã|â€|ðŸ")
TRANSLATE_RE = re.compile(r"^\s*translate\s+([A-Za-z0-9_-]+)\b")
OLD_PREFIX = "old"
PRINTF_SAFE_NEXT = set("%bcdeEfFgGnosxXrdiuHMSaAwWyYIUpZzjxXc(")


@dataclass
class Issue:
    severity: str
    path: Path
    line: int
    message: str


def unescape_minimal(text: str) -> str:
    return text.replace(r"\"", '"').replace(r"\'", "'")


def tokens(pattern: re.Pattern[str], text: str) -> Counter[str]:
    return Counter(pattern.findall(text))


def tag_shapes(text: str) -> Counter[str]:
    shapes: Counter[str] = Counter()
    for raw in TAG_RE.findall(text):
        inner = raw[1:-1].strip()
        closing = inner.startswith("/")
        if closing:
            inner = inner[1:]
        name = re.split(r"[=\s]", inner, maxsplit=1)[0]
        shapes[("/" if closing else "") + name] += 1
    return shapes



def unsafe_percent_positions(text: str) -> list[int]:
    positions: list[int] = []
    index = 0
    while index < len(text):
        if text[index] != "%":
            index += 1
            continue
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if next_char not in PRINTF_SAFE_NEXT:
            positions.append(index)
        if next_char == "%":
            index += 2
        else:
            index += 1
    return positions

def visible_candidate(prefix: str | None, text: str) -> bool:
    if prefix and prefix.strip() == "old":
        return False
    if not text.strip():
        return False
    if text.startswith(("audio/", "images/", "gui/", "fonts/")):
        return False
    return True


def audit_file(path: Path, language: str, long_limit: int) -> list[Issue]:
    issues: list[Issue] = []
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    active_language = None
    pending_old: tuple[int, str] | None = None
    pending_comment: tuple[int, str] | None = None

    for number, raw in enumerate(lines, 1):
        match_language = TRANSLATE_RE.match(raw)
        if match_language:
            if active_language == language and pending_comment:
                issues.append(
                    Issue("ERROR", path, pending_comment[0], "missing translated dialogue line")
                )
            if active_language == language and pending_old:
                issues.append(Issue("ERROR", path, pending_old[0], "missing matching new string"))
            pending_comment = None
            pending_old = None
            active_language = match_language.group(1)

        stripped = raw.lstrip()
        if stripped.startswith("#"):
            commented = stripped[1:].lstrip()
            parsed_comment = QUOTED_RE.match(commented)
            if parsed_comment:
                pending_comment = (number, unescape_minimal(parsed_comment.group("text")))
            continue

        parsed = QUOTED_RE.match(raw)
        if not parsed or active_language != language:
            continue

        prefix = (parsed.group("prefix") or "").strip()
        text = unescape_minimal(parsed.group("text"))

        if prefix == "old":
            pending_old = (number, text)
            continue

        source: tuple[int, str] | None = None
        if prefix == "new" and pending_old:
            source = pending_old
            pending_old = None
        elif prefix not in {"new", "old"} and pending_comment:
            source = pending_comment
            pending_comment = None

        if MOJIBAKE_RE.search(text):
            issues.append(Issue("ERROR", path, number, "possible mojibake"))

        if prefix != "old" and unsafe_percent_positions(text):
            issues.append(Issue("ERROR", path, number, "unsafe literal percent sign; use %% for visible percent"))

        if prefix == "new" and source and source[1].strip() and not text.strip():
            issues.append(Issue("ERROR", path, number, "empty translation"))

        if source:
            source_text = source[1]
            if tokens(VARIABLE_RE, source_text) != tokens(VARIABLE_RE, text):
                issues.append(Issue("ERROR", path, number, "interpolation variables differ from source"))
            if tag_shapes(source_text) != tag_shapes(text):
                issues.append(Issue("ERROR", path, number, "Ren'Py text tags differ from source"))
            if (
                text.strip() == source_text.strip()
                and LATIN_WORD_RE.search(text)
                and not CHINESE_RE.search(text)
            ):
                issues.append(Issue("WARN", path, number, "translation is identical to English source"))

        if visible_candidate(prefix, text):
            plain = VARIABLE_RE.sub("", TAG_RE.sub("", text))
            if len(plain) > long_limit:
                issues.append(
                    Issue("WARN", path, number, f"long visible line ({len(plain)} characters)")
                )
            if LATIN_WORD_RE.search(plain) and not CHINESE_RE.search(plain):
                issues.append(Issue("INFO", path, number, "visible line may still be untranslated"))

    if active_language == language and pending_comment:
        issues.append(Issue("ERROR", path, pending_comment[0], "missing translated dialogue line"))
    if active_language == language and pending_old:
        issues.append(Issue("ERROR", path, pending_old[0], "missing matching new string"))

    return issues



def audit_string_old_keys(files: list[Path], language: str) -> list[Issue]:
    issues: list[Issue] = []
    old_locations: dict[str, tuple[Path, int]] = {}

    for path in files:
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        active_language = None

        for number, raw in enumerate(lines, 1):
            match_language = TRANSLATE_RE.match(raw)
            if match_language:
                active_language = match_language.group(1)

            if active_language != language:
                continue

            parsed = QUOTED_RE.match(raw)
            if not parsed:
                continue

            prefix = (parsed.group("prefix") or "").strip()
            if prefix != OLD_PREFIX:
                continue

            text = unescape_minimal(parsed.group("text"))
            if CHINESE_RE.search(text):
                issues.append(Issue("ERROR", path, number, "string old key contains CJK; old must remain source text"))

            if text in old_locations:
                first_path, first_line = old_locations[text]
                issues.append(
                    Issue(
                        "ERROR",
                        path,
                        number,
                        f"duplicate string old key; first seen at {first_path}:{first_line}",
                    )
                )
            else:
                old_locations[text] = (path, number)

    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path, help="Ren'Py project root or game directory")
    parser.add_argument("--language", default="chinese")
    parser.add_argument("--long-limit", type=int, default=68)
    parser.add_argument("--strict", action="store_true", help="fail on warnings as well as errors")
    args = parser.parse_args()

    root = args.project.resolve()
    game = root if root.name.lower() == "game" else root / "game"
    translation_root = game / "tl" / args.language

    if not game.is_dir():
        print(f"ERROR: game directory not found under {root}", file=sys.stderr)
        return 2
    if not translation_root.is_dir():
        print(f"ERROR: translation directory not found: {translation_root}", file=sys.stderr)
        return 2

    files = sorted(translation_root.rglob("*.rpy"))
    issues: list[Issue] = []
    for path in files:
        issues.extend(audit_file(path, args.language, args.long_limit))
    issues.extend(audit_string_old_keys(files, args.language))

    counts = Counter(issue.severity for issue in issues)
    for issue in issues:
        relative = issue.path.relative_to(root) if issue.path.is_relative_to(root) else issue.path
        print(f"{issue.severity}: {relative}:{issue.line}: {issue.message}")

    print(
        f"\nAudited {len(files)} files: "
        f"{counts['ERROR']} errors, {counts['WARN']} warnings, {counts['INFO']} info."
    )

    if counts["ERROR"] or (args.strict and counts["WARN"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
