#!/usr/bin/env python3
"""Export Ren'Py tl/<language> files as JSONL translation units."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


TRANSLATE_RE = re.compile(r"^\s*translate\s+(?P<language>[A-Za-z0-9_-]+)\s+(?P<label>[^:]+):")
HIDDEN_TAG_RE = re.compile(r"^\{#[^{}]*\}$")
VARIABLE_RE = re.compile(r"\[[^\[\]]+\]")
TAG_RE = re.compile(r"\{[^{}]+\}")
ESCAPE_RE = re.compile(r"""\\(?:[\\'"abfnrtv]|N\{[^}]+\}|u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|x[0-9A-Fa-f]{2})""")
PRINTF_RE = re.compile(
    r"%(?:\([^)]+\))?[#0 +\-]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[hlL]?[diouxXeEfFgGcrs%]"
)
ASSET_OR_CODE_PATH_RE = re.compile(
    r"(?i)^(?:https?://|[A-Za-z]:[\\/]|(?:audio|bgm|sfx|voice|voices|images|image|gui|fonts|font|video|movies?)[\\/])"
)
ASSET_EXTENSION_RE = re.compile(
    r"(?i)\.(?:png|jpe?g|webp|gif|bmp|svg|mp3|ogg|opus|wav|flac|mp4|webm|avi|ttf|otf|ttc|rpy|rpyc|rpa|rpym|rpymc)$"
)
RENPY_CODE_RE = re.compile(r"(?i)^(?:renpy|persistent|config|gui|style|Transform|Animation|Movie|Null|Text)\b")
STRING_PREFIX_RE = re.compile(r"(?i)^[rubf]{0,3}['\"]")


@dataclass(frozen=True)
class ParsedString:
    prefix: str
    literal: str
    suffix: str
    quote_start: int
    text: str


def project_root(root: Path) -> Path:
    root = root.resolve()
    if (root / "game").is_dir():
        return root
    if root.name.lower() == "game" and root.is_dir():
        return root.parent
    raise SystemExit(f"Could not find a Ren'Py project root for: {root}")


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def find_string_literal(line: str) -> tuple[int, str, str] | None:
    for index, char in enumerate(line):
        if char not in {'"', "'"}:
            continue
        prefix_start = index
        while prefix_start > 0 and line[prefix_start - 1].isalpha():
            prefix_start -= 1
        if prefix_start != index and not STRING_PREFIX_RE.fullmatch(line[prefix_start : index + 1]):
            continue
        quote = char
        position = index + 1
        escaped = False
        while position < len(line):
            current = line[position]
            if escaped:
                escaped = False
            elif current == "\\":
                escaped = True
            elif current == quote:
                return prefix_start, line[prefix_start : position + 1], line[position + 1 :]
            position += 1
    return None


def decode_renpy_string(literal: str) -> str:
    try:
        value = ast.literal_eval(literal)
        return value if isinstance(value, str) else str(value)
    except Exception:
        body = literal[1:-1] if len(literal) >= 2 else literal
        try:
            return bytes(body, "utf-8").decode("unicode_escape")
        except Exception:
            return body


def parse_string_line(line: str) -> ParsedString | None:
    found = find_string_literal(line)
    if not found:
        return None
    start, literal, suffix = found
    prefix = line[:start].strip()
    return ParsedString(prefix=prefix, literal=literal, suffix=suffix, quote_start=start, text=decode_renpy_string(literal))


def line_command(prefix: str) -> str:
    stripped = prefix.strip()
    return stripped.split(None, 1)[0] if stripped else ""


def speaker_from_prefix(prefix: str) -> str:
    command = line_command(prefix)
    if command in {"old", "new"}:
        return ""
    return prefix.strip()


def is_dialogue_prefix(prefix: str) -> bool:
    stripped = prefix.strip()
    if not stripped:
        return True
    if any(char in stripped for char in "=()[]{}:,."):
        return False
    return bool(re.fullmatch(r"[A-Za-z_]\w*(?:\s+[A-Za-z_]\w*)*", stripped))


def visible_translatable_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if HIDDEN_TAG_RE.fullmatch(stripped):
        return False
    without_tokens = TAG_RE.sub("", VARIABLE_RE.sub("", stripped)).strip()
    if not without_tokens:
        return False
    normalized = stripped.replace("\\", "/")
    if ASSET_OR_CODE_PATH_RE.search(normalized) or ASSET_EXTENSION_RE.search(normalized):
        return False
    if RENPY_CODE_RE.search(stripped):
        return False
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_.]*", stripped):
        return False
    return True


def raw_body(literal: str) -> str:
    if len(literal) < 2:
        return literal
    index = 0
    while index < len(literal) and literal[index].isalpha():
        index += 1
    return literal[index + 1 : -1]


def preserve_tokens(literal: str, text: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: Counter[tuple[str, str]] = Counter()

    def add(kind: str, value: str, position: int) -> None:
        key = (kind, value)
        seen[key] += 1
        found.append({"kind": kind, "value": value, "position": position, "occurrence": seen[key]})

    for match in VARIABLE_RE.finditer(text):
        add("variable", match.group(0), match.start())
    for match in TAG_RE.finditer(text):
        add("tag", match.group(0), match.start())
    for match in PRINTF_RE.finditer(text):
        add("percent", match.group(0), match.start())
    for match in ESCAPE_RE.finditer(raw_body(literal)):
        add("escape", match.group(0), match.start())

    return sorted(found, key=lambda item: (item["position"], item["kind"], item["occurrence"]))


def status_for(source: str, target: str) -> str:
    if not target:
        return "empty"
    if target.strip() == source.strip():
        return "source_copy"
    return "translated"


def stable_id(
    *,
    language: str,
    kind: str,
    file: str,
    label: str,
    source: str,
    speaker: str,
    occurrence: int,
) -> str:
    payload = json.dumps(
        {
            "schema": "renpy-translation-unit-v1",
            "language": language,
            "kind": kind,
            "file": file,
            "label": label,
            "source": source,
            "speaker": speaker,
            "occurrence": occurrence,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"{kind}:{digest}"


def next_content_line(lines: list[str], start: int) -> tuple[int, str] | None:
    index = start
    while index < len(lines):
        if lines[index].strip():
            return index, lines[index]
        index += 1
    return None


def iter_units(root: Path, language: str) -> Iterable[dict[str, Any]]:
    tl_root = root / "game" / "tl" / language
    if not tl_root.is_dir():
        raise SystemExit(f"Translation directory not found: {tl_root}")

    occurrence_counts: Counter[tuple[str, str, str, str, str]] = Counter()
    for path in sorted(tl_root.rglob("*.rpy")):
        rel_file = rel(path, root)
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        active_language = ""
        active_label = ""
        index = 0
        while index < len(lines):
            raw = lines[index]
            block = TRANSLATE_RE.match(raw)
            if block:
                active_language = block.group("language")
                active_label = block.group("label").strip()
                index += 1
                continue

            if active_language != language:
                index += 1
                continue

            if active_label == "strings":
                parsed_old = parse_string_line(raw)
                if parsed_old and line_command(parsed_old.prefix) == "old" and visible_translatable_text(parsed_old.text):
                    next_line = next_content_line(lines, index + 1)
                    if next_line:
                        target_index, target_raw = next_line
                        parsed_new = parse_string_line(target_raw)
                        if parsed_new and line_command(parsed_new.prefix) == "new":
                            key = ("string", rel_file, active_label, "", parsed_old.text)
                            occurrence_counts[key] += 1
                            occurrence = occurrence_counts[key]
                            yield {
                                "id": stable_id(
                                    language=language,
                                    kind="string",
                                    file=rel_file,
                                    label=active_label,
                                    source=parsed_old.text,
                                    speaker="",
                                    occurrence=occurrence,
                                ),
                                "kind": "string",
                                "file": rel_file,
                                "line": target_index + 1,
                                "language": language,
                                "source": parsed_old.text,
                                "target": parsed_new.text,
                                "speaker": "",
                                "label": active_label,
                                "preserve_tokens": preserve_tokens(parsed_old.literal, parsed_old.text),
                                "status": status_for(parsed_old.text, parsed_new.text),
                                "source_line": index + 1,
                            }
                            index = target_index + 1
                            continue
                index += 1
                continue

            stripped = raw.lstrip()
            if not stripped.startswith("#"):
                index += 1
                continue
            parsed_source = parse_string_line(stripped[1:].lstrip())
            if (
                not parsed_source
                or not is_dialogue_prefix(parsed_source.prefix)
                or not visible_translatable_text(parsed_source.text)
            ):
                index += 1
                continue

            next_line = next_content_line(lines, index + 1)
            if not next_line:
                index += 1
                continue
            target_index, target_raw = next_line
            parsed_target = parse_string_line(target_raw)
            if not parsed_target or not is_dialogue_prefix(parsed_target.prefix):
                index += 1
                continue
            if line_command(parsed_target.prefix) in {"old", "new"}:
                index += 1
                continue

            speaker = speaker_from_prefix(parsed_source.prefix) or speaker_from_prefix(parsed_target.prefix)
            key = ("dialogue", rel_file, active_label, speaker, parsed_source.text)
            occurrence_counts[key] += 1
            occurrence = occurrence_counts[key]
            yield {
                "id": stable_id(
                    language=language,
                    kind="dialogue",
                    file=rel_file,
                    label=active_label,
                    source=parsed_source.text,
                    speaker=speaker,
                    occurrence=occurrence,
                ),
                "kind": "dialogue",
                "file": rel_file,
                "line": target_index + 1,
                "language": language,
                "source": parsed_source.text,
                "target": parsed_target.text,
                "speaker": speaker,
                "label": active_label,
                "preserve_tokens": preserve_tokens(parsed_source.literal, parsed_source.text),
                "status": status_for(parsed_source.text, parsed_target.text),
                "source_line": index + 1,
            }
            index = target_index + 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Ren'Py project root or game directory")
    parser.add_argument("--language", default="chinese", help="Language layer under game/tl/")
    parser.add_argument("--output", type=Path, help="Write JSONL here instead of stdout")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print one JSON object per unit for debugging")
    parser.add_argument("--pending-only", action="store_true", help="Only export units whose target is empty or still source text")
    args = parser.parse_args()

    root = project_root(args.root)
    units = list(iter_units(root, args.language))
    if args.pending_only:
        units = [unit for unit in units if unit["status"] in {"empty", "source_copy"}]

    output = args.output.open("w", encoding="utf-8") if args.output else sys.stdout
    try:
        for unit in units:
            output.write(json.dumps(unit, ensure_ascii=False, indent=2 if args.pretty else None))
            output.write("\n")
    finally:
        if output is not sys.stdout:
            output.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
