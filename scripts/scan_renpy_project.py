#!/usr/bin/env python3
"""Scan a Ren'Py project and emit a JSON localization readiness report."""

from __future__ import annotations

import argparse
import json
import pickle
import re
import struct
import sys
import zlib
from collections import Counter
from pathlib import Path
from typing import Any


TRANSLATE_RE = re.compile(r"^\s*translate\s+([A-Za-z0-9_-]+)\b")
OLD_RE = re.compile(r'^\s*old\s+(?P<quote>"(?:\\.|[^"\\])*")')
NEW_EMPTY_RE = re.compile(r'^\s*new\s+""\s*(?:#.*)?$')
SOURCE_COMMENT_RE = re.compile(r'^\s*#\s+(?:(?:[A-Za-z_]\w*)\s+)?"(?:\\.|[^"\\])*"')
EMPTY_DIALOGUE_RE = re.compile(r'^\s*(?:[A-Za-z_]\w*\s+)?""\s*(?:#.*)?$')
CHARACTER_RE = re.compile(r"^\s*define\s+([A-Za-z_]\w*)\s*=\s*Character\((.*)")
MOJIBAKE_RE = re.compile(r"\ufffd|\u951f|\u8119|\u9239|\u95b3|\u68e3")
CHINESE_RE = re.compile(r"[\u3400-\u9fff]")
HIDDEN_TAG_RE = re.compile(r"^\{#[^{}]*\}$")
UI_RPYC_NAMES = {"screens.rpyc", "gui.rpyc", "gallery.rpyc", "credits.rpyc", "named_file_save.rpyc"}
EXPECTED_UI_KEYS = {'About',
 'Accessibility',
 'Accessibility Menu',
 'Achievements',
 'After Choices',
 'Auto',
 'Auto Save',
 'Auto-Forward Time',
 'Back',
 'Cancel',
 'Chinese',
 'Chinese Mode',
 'Clipboard voicing',
 'Confirm',
 'Continue',
 'Credits',
 'Debug voicing',
 'Default',
 'Delete',
 'Disable',
 'Display',
 'Done',
 'Empty Slot',
 'Empty Slot.',
 'English',
 'English Mode',
 'Extras',
 'File',
 'Font Override',
 'Full Screen',
 'Fullscreen',
 'Fullscreen Mode',
 'Gallery',
 'Help',
 'High Contrast Text',
 'History',
 'Language',
 'Left',
 'Line Spacing Scaling',
 'Load',
 'Main Menu',
 'Menu',
 'Music Volume',
 'Mute All',
 'New Game',
 'Newest',
 'Next',
 'No',
 'Off',
 'Oldest',
 'On',
 'OpenDyslexic',
 'Page',
 'Page {}',
 'Preferences',
 'Prefs',
 'Previous',
 'Q.Load',
 'Q.Save',
 'Quick',
 'Quick Load',
 'Quick Save',
 'Quit',
 'Reset',
 'Return',
 'Right',
 'Rollback Side',
 'Save',
 'Self-Voicing',
 'Self-voicing',
 'Settings',
 'Skip',
 'Sound Volume',
 'Start',
 'Test',
 'Text Size Scaling',
 'Text Speed',
 'Transitions',
 'Unseen Text',
 'Voice Volume',
 'Window',
 'Window Mode',
 'Windowed',
 'Yes'}

UI_STRING_RE = re.compile(r'^\s*old\s+(?P<quote>"(?:\\.|[^"\\])*")')
MAIN_MENU_EXPECTED_KEYS = {"Start", "Load", "Preferences", "About", "Help", "Quit"}
RPYC2_HEADER = b"RENPY RPC2"
RPYC_TRANSLATE_STRING_RE = re.compile(rb'_\("((?:\\.|[^"\\]){1,200})"\)')
IGNORED_DISCOVERED_UI_KEYS = {
    "[pname]",
    "[pname2]",
    "[pname3]",
    "[pname4]",
    "gui/patreon2.png",
    "gui/patreonhover2.jpg",
    "https://patreon.com/grymgudinnagames",
}

try:
    from add_ui_string_overrides import DEFAULT_UI_TRANSLATIONS

    EXPECTED_UI_KEYS = set(DEFAULT_UI_TRANSLATIONS)
except Exception:
    pass


def decode_renpy_string(literal: str) -> str:
    try:
        return bytes(literal[1:-1], "utf-8").decode("unicode_escape")
    except Exception:
        return literal[1:-1]


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def find_game_dir(root: Path) -> Path:
    if (root / "game").is_dir():
        return root / "game"
    if root.name == "game" and root.is_dir():
        return root
    raise SystemExit(f"Could not find a Ren'Py game directory under: {root}")


def file_stat(path: Path, root: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": rel(path, root),
        "size": stat.st_size,
        "mtime": stat.st_mtime,
    }


def visible_source_text(text: str | None) -> bool:
    if text is None:
        return False
    stripped = text.strip()
    if not stripped:
        return False
    if HIDDEN_TAG_RE.fullmatch(stripped):
        return False
    return True


def load_rpa_index(archive_path: Path) -> list[str]:
    try:
        with archive_path.open("rb") as handle:
            header = handle.readline()
            if header.startswith(b"RPA-3.0 "):
                offset = int(header[8:24], 16)
                handle.seek(offset)
                index = pickle.loads(zlib.decompress(handle.read()), encoding="latin1")
                return sorted(str(name).replace("\\", "/") for name in index)
            if header.startswith(b"RPA-2.0 "):
                offset = int(header[8:], 16)
                handle.seek(offset)
                index = pickle.loads(zlib.decompress(handle.read()), encoding="latin1")
                return sorted(str(name).replace("\\", "/") for name in index)
    except Exception:
        return []
    return []


def read_rpyc_payloads(path: Path) -> list[bytes]:
    try:
        data = path.read_bytes()
        if not data.startswith(RPYC2_HEADER):
            return [zlib.decompress(data)]
        payloads: list[bytes] = []
        position = len(RPYC2_HEADER)
        while True:
            slot, start, length = struct.unpack("III", data[position : position + 12])
            if slot == 0:
                break
            payloads.append(zlib.decompress(data[start : start + length]))
            position += 12
        return payloads
    except Exception:
        return []


def decode_embedded_renpy_string(value: bytes) -> str:
    text = value.decode("utf-8", errors="replace")
    return decode_renpy_string('"' + text.replace('"', r'\"') + '"')


def discover_rpyc_ui_string_keys(paths: list[Path]) -> list[str]:
    keys: set[str] = set()
    for path in paths:
        if path.name not in UI_RPYC_NAMES:
            continue
        for payload in read_rpyc_payloads(path):
            for match in RPYC_TRANSLATE_STRING_RE.finditer(payload):
                key = decode_embedded_renpy_string(match.group(1))
                if key and key not in IGNORED_DISCOVERED_UI_KEYS:
                    keys.add(key)
    return sorted(keys)


def inspect_language(tl_dir: Path, language: str, root: Path, discovered_ui_keys: list[str]) -> dict[str, Any]:
    lang_dir = tl_dir / language
    report: dict[str, Any] = {
        "language": language,
        "exists": lang_dir.is_dir(),
        "rpy_files": 0,
        "translate_blocks": 0,
        "string_old_lines": 0,
        "string_old_with_cjk": 0,
        "duplicate_old_keys": 0,
        "empty_new_lines": 0,
        "empty_dialogue_targets": 0,
        "ui_string_keys": 0,
        "ui_string_key_values": [],
        "missing_expected_ui_keys": [],
        "missing_extended_ui_keys": [],
        "missing_discovered_ui_keys": [],
        "mojibake_lines": 0,
        "sample_problem_files": [],
    }
    if not lang_dir.is_dir():
        return report

    old_seen: dict[str, str] = {}
    ui_keys: set[str] = set()
    problem_files: set[str] = set()
    for path in sorted(lang_dir.rglob("*.rpy")):
        report["rpy_files"] += 1
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        pending_source: str | None = None
        for number, line in enumerate(lines, 1):
            if TRANSLATE_RE.match(line):
                report["translate_blocks"] += 1
            if SOURCE_COMMENT_RE.match(line):
                source_match = SOURCE_COMMENT_RE.match(line)
                if source_match:
                    quote_match = re.search(r'"(?:\\.|[^"\\])*"', line)
                    pending_source = decode_renpy_string(quote_match.group(0)) if quote_match else None
                continue

            old = OLD_RE.match(line)
            if old:
                report["string_old_lines"] += 1
                ui_match = UI_STRING_RE.match(line)
                ui_text = decode_renpy_string(ui_match.group("quote")) if ui_match else ""
                if ui_text in EXPECTED_UI_KEYS:
                    report["ui_string_keys"] += 1
                    ui_keys.add(ui_text)
                text = decode_renpy_string(old.group("quote"))
                if CHINESE_RE.search(text):
                    report["string_old_with_cjk"] += 1
                    problem_files.add(rel(path, root))
                if text in old_seen:
                    report["duplicate_old_keys"] += 1
                    problem_files.add(rel(path, root))
                else:
                    old_seen[text] = f"{rel(path, root)}:{number}"

            if NEW_EMPTY_RE.match(line):
                report["empty_new_lines"] += 1
                problem_files.add(rel(path, root))
            elif visible_source_text(pending_source) and EMPTY_DIALOGUE_RE.match(line):
                report["empty_dialogue_targets"] += 1
                problem_files.add(rel(path, root))
            elif line.strip():
                pending_source = None

            if MOJIBAKE_RE.search(line):
                report["mojibake_lines"] += 1
                problem_files.add(rel(path, root))

    report["sample_problem_files"] = sorted(problem_files)[:20]
    report["ui_string_key_values"] = sorted(ui_keys)
    report["missing_expected_ui_keys"] = sorted(MAIN_MENU_EXPECTED_KEYS - ui_keys)
    report["missing_extended_ui_keys"] = sorted(EXPECTED_UI_KEYS - ui_keys)
    report["missing_discovered_ui_keys"] = sorted(set(discovered_ui_keys) - ui_keys)
    return report


def scan(root: Path, languages: list[str]) -> dict[str, Any]:
    root = root.resolve()
    game_dir = find_game_dir(root)
    project_root = game_dir.parent

    rpy_files = sorted(game_dir.rglob("*.rpy"))
    rpyc_files = sorted(game_dir.rglob("*.rpyc"))
    rpa_files = sorted(game_dir.rglob("*.rpa"))
    archive_entries: dict[str, list[str]] = {rel(path, project_root): load_rpa_index(path) for path in rpa_files}
    archived_ui_rpyc = sorted(
        entry
        for entries in archive_entries.values()
        for entry in entries
        if Path(entry).name in UI_RPYC_NAMES
    )
    font_files = sorted(
        path for pattern in ("*.ttf", "*.otf", "*.ttc") for path in game_dir.rglob(pattern)
    )
    tl_dir = game_dir / "tl"
    tl_languages = sorted(path.name for path in tl_dir.iterdir() if path.is_dir()) if tl_dir.is_dir() else []
    selected_languages = languages or tl_languages or ["chinese"]

    character_ids: Counter[str] = Counter()
    labels = 0
    menus = 0
    for path in rpy_files:
        if "/tl/" in path.as_posix().replace("\\", "/"):
            continue
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            if CHARACTER_RE.match(line):
                character_ids[CHARACTER_RE.match(line).group(1)] += 1  # type: ignore[union-attr]
            if re.match(r"^\s*label\s+\S+:", line):
                labels += 1
            if re.match(r"^\s*menu\s*:", line):
                menus += 1

    exe_files = sorted(project_root.glob("*.exe"))
    logs = [project_root / "traceback.txt", project_root / "log.txt"]
    discovered_ui_keys = discover_rpyc_ui_string_keys(rpyc_files)
    language_reports = [
        inspect_language(tl_dir, language, project_root, discovered_ui_keys)
        for language in selected_languages
    ]

    signals: list[str] = []
    recommended_actions: list[dict[str, Any]] = []
    if rpyc_files and not rpy_files:
        signals.append("compiled_only_project")
    if rpa_files:
        signals.append("archives_present")
    if archived_ui_rpyc:
        signals.append("archived_ui_rpyc_present")
    for item in language_reports:
        if item["exists"] and (item["string_old_with_cjk"] or item["duplicate_old_keys"] or item["mojibake_lines"]):
            signals.append(f"{item['language']}_layer_may_be_polluted")
        if archived_ui_rpyc and item["exists"] and item["missing_extended_ui_keys"]:
            signals.append(f"{item['language']}_ui_screen_translation_may_be_missing")
            recommended_actions.append(
                {
                    "reason": "Archived UI screen bytecode exists, but expected menu/save/history UI string keys are missing.",
                    "language": item["language"],
                    "missing_keys": item["missing_extended_ui_keys"],
                    "command": (
                        "python <skill>/scripts/add_ui_string_overrides.py "
                        f"<project-root> --language {item['language']} --apply"
                    ),
                }
            )
        if item["exists"] and item.get("missing_discovered_ui_keys"):
            signals.append(f"{item['language']}_ui_runtime_strings_missing")
            recommended_actions.append(
                {
                    "reason": "Compiled UI bytecode contains translatable strings that are missing from the language layer.",
                    "language": item["language"],
                    "missing_keys": item["missing_discovered_ui_keys"],
                    "command": (
                        "Add these keys to add_ui_string_overrides.py or pass them with --extra, then run "
                        f"python <skill>/scripts/add_ui_string_overrides.py <project-root> --language {item['language']} --apply --update-existing"
                    ),
                }
            )
    if not font_files:
        signals.append("no_bundled_font_detected")

    return {
        "project_root": str(project_root),
        "game_dir": rel(game_dir, project_root),
        "files": {
            "rpy": len(rpy_files),
            "rpyc": len(rpyc_files),
            "rpa": len(rpa_files),
            "fonts": len(font_files),
            "executables": len(exe_files),
        },
        "samples": {
            "archives": [rel(path, project_root) for path in rpa_files[:20]],
            "archived_ui_rpyc": archived_ui_rpyc[:20],
            "discovered_ui_strings": discovered_ui_keys[:100],
            "fonts": [rel(path, project_root) for path in font_files[:20]],
            "executables": [rel(path, project_root) for path in exe_files[:20]],
        },
        "source_structure": {
            "labels": labels,
            "menus": menus,
            "character_ids": sorted(character_ids),
        },
        "tl_languages": tl_languages,
        "language_reports": language_reports,
        "logs": {path.name: file_stat(path, project_root) for path in logs if path.exists()},
        "signals": sorted(set(signals)),
        "recommended_actions": recommended_actions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Ren'Py project root or game directory")
    parser.add_argument("--language", action="append", default=[], help="Language layer to inspect; repeatable")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args()

    report = scan(args.root, args.language)
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
