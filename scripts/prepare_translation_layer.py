#!/usr/bin/env python3
"""Prepare a Ren'Py translation layer before paid or bulk translation.

This is a front-loaded stage runner inspired by GUI localizers: prefer the
game's own Ren'Py runtime to generate templates, then install deterministic UI
strings and CJK font/style defaults before any LLM sees text.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


STYLE_NAMES = (
    "default", "say_dialogue", "say_label", "input", "button_text",
    "choice_button_text", "label_text", "prompt_text", "notify_text",
    "gui_text", "interface_text", "main_menu_button_text",
    "navigation_button_text", "game_menu_label_text", "return_button_text",
    "page_label_text", "file_slot_button_text", "file_slot_name_text",
    "file_slot_time_text", "file_slot_empty_text", "preferences_button_text",
    "radio_button_text", "check_button_text", "slider_label_text",
    "history_name_text", "history_text", "history_label_text",
    "help_button_text", "help_label_text", "quick_button_text",
    "confirm_prompt_text", "skip_indicator_text", "gallery_button_text",
    "credits_text", "credits_title_text",
)


def project_root(root: Path) -> Path:
    root = root.resolve()
    if (root / "game").is_dir():
        return root
    if root.name == "game" and root.is_dir():
        return root.parent
    raise SystemExit(f"Could not find Ren'Py project root for: {root}")


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def find_runtime_translate_command(root: Path, language: str) -> list[str] | None:
    py_scripts = sorted(path for path in root.glob("*.py") if path.name.lower() not in {"renpy.py"})
    if not py_scripts:
        return None

    python_candidates = [
        root / "lib" / "py3-windows-x86_64" / "python.exe",
        root / "lib" / "py3-windows-i686" / "python.exe",
        root / "lib" / "windows-x86_64" / "python.exe",
        root / "lib" / "windows-i686" / "python.exe",
    ]
    for python in python_candidates:
        if python.exists():
            return [str(python), "-O", str(py_scripts[0]), str(root), "translate", language]
    return None


def run_command(command: list[str], cwd: Path, timeout: int) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
        )
        return {
            "ran": True,
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-2000:],
            "stderr_tail": completed.stderr[-2000:],
        }
    except Exception as exc:
        return {"ran": True, "ok": False, "error": repr(exc)}


def choose_font(root: Path, requested: Path | None) -> tuple[Path | None, str | None, list[str]]:
    notes: list[str] = []
    game_dir = root / "game"
    if requested:
        requested = requested.resolve()
        if not requested.exists():
            notes.append(f"requested font does not exist: {requested}")
            return None, None, notes
        target_dir = game_dir / "fonts"
        target_path = target_dir / requested.name
        return requested, rel(target_path, game_dir), notes

    existing_fonts = [
        path
        for pattern in ("*.ttf", "*.otf", "*.ttc")
        for path in sorted((game_dir / "fonts").glob(pattern))
    ]
    preferred_markers = ("noto", "sourcehan", "cjk", "sc", "cn", "chinese", "msyh", "simhei", "simsun")
    for path in existing_fonts:
        lowered = path.name.lower()
        if any(marker in lowered for marker in preferred_markers):
            return path, rel(path, game_dir), notes
    if existing_fonts:
        notes.append(f"selected existing font without obvious CJK marker: {existing_fonts[0].name}")
        return existing_fonts[0], rel(existing_fonts[0], game_dir), notes

    for system_font in (
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
    ):
        if system_font.exists():
            target_path = game_dir / "fonts" / system_font.name
            return system_font, rel(target_path, game_dir), notes

    notes.append("no CJK font candidate found")
    return None, None, notes


def write_language_setup(root: Path, language: str, font_source: Path | None, font_rel: str | None) -> dict[str, Any]:
    lang_dir = root / "game" / "tl" / language
    lang_dir.mkdir(parents=True, exist_ok=True)
    copied_font = None
    if font_source and font_rel:
        target = root / "game" / font_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if font_source.resolve() != target.resolve():
            shutil.copy2(font_source, target)
            copied_font = rel(target, root)

    if not font_rel:
        return {"written": False, "reason": "no font selected", "copied_font": copied_font}

    style_list = ",\n        ".join(repr(name) for name in STYLE_NAMES)
    text = f'''# Generated by renpy-game-localizer prepare_translation_layer.py.
init 999 python:
    config.language = "{language}"

init 1000 python:
    _cjk_font = "{font_rel}"
    for _style_name in (
        {style_list},
    ):
        try:
            getattr(style, _style_name).font = _cjk_font
        except Exception:
            pass

    try:
        gui.text_font = _cjk_font
        gui.name_text_font = _cjk_font
        gui.interface_text_font = _cjk_font
        gui.button_text_font = _cjk_font
        gui.choice_button_text_font = _cjk_font
    except Exception:
        pass
'''
    output = lang_dir / f"zz_{language}_setup.rpy"
    output.write_text(text, encoding="utf-8", newline="\n")
    return {"written": True, "path": rel(output, root), "copied_font": copied_font, "font": font_rel}


def run_ui_helper(root: Path, language: str, apply: bool, update_existing: bool, pretty: bool) -> dict[str, Any]:
    helper = Path(__file__).with_name("add_ui_string_overrides.py")
    command = [sys.executable, str(helper), str(root), "--language", language]
    if apply:
        command.append("--apply")
    if update_existing:
        command.append("--update-existing")
    if pretty:
        command.append("--pretty")
    result = run_command(command, root, 120)
    try:
        result["json"] = json.loads(result.get("stdout_tail", "") or "{}")
    except Exception:
        pass
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Ren'Py project root or game directory")
    parser.add_argument("--language", default="chinese")
    parser.add_argument("--apply", action="store_true", help="Write setup/UI files; default reports the plan")
    parser.add_argument("--generate-official", action="store_true", help="Run the bundled Ren'Py translate command when detected")
    parser.add_argument("--font", type=Path, help="CJK font to copy into game/fonts and use in style defaults")
    parser.add_argument("--update-existing-ui", action="store_true", help="Normalize existing known UI targets such as Page {}")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    root = project_root(args.root)
    lang_dir = root / "game" / "tl" / args.language
    report: dict[str, Any] = {
        "root": str(root),
        "language": args.language,
        "applied": args.apply,
        "stages": {},
        "next_actions": [],
    }

    command = find_runtime_translate_command(root, args.language)
    report["stages"]["official_translate_command"] = command
    if args.generate_official:
        if command:
            report["stages"]["official_translate"] = run_command(command, root, args.timeout)
        else:
            report["stages"]["official_translate"] = {"ran": False, "ok": False, "reason": "no bundled Ren'Py python/script command detected"}
    elif not lang_dir.exists():
        report["next_actions"].append("Run with --generate-official when a bundled Ren'Py runtime is detected, or generate translations in the Ren'Py launcher.")

    font_source, font_rel, font_notes = choose_font(root, args.font)
    report["stages"]["font_selection"] = {
        "source": str(font_source) if font_source else None,
        "game_path": font_rel,
        "notes": font_notes,
    }
    if args.apply:
        report["stages"]["language_setup"] = write_language_setup(root, args.language, font_source, font_rel)
    else:
        report["next_actions"].append("Run with --apply to write language setup, CJK style defaults, and UI string overrides.")

    if args.apply:
        ui_result = run_ui_helper(root, args.language, True, args.update_existing_ui, args.pretty)
    else:
        ui_result = run_ui_helper(root, args.language, False, args.update_existing_ui, args.pretty)
    report["stages"]["ui_strings"] = ui_result

    report["gates"] = {
        "old_keys_must_remain_source": True,
        "llm_should_translate_targets_only": True,
        "run_audit_before_deepseek_apply": True,
    }
    report["next_actions"].extend(
        [
            "Run scan_renpy_project.py and confirm missing_extended_ui_keys is empty.",
            "Build or update localization_work/glossary.md before the paid sample pass.",
            "Run deepseek_renpy_tl_translate.py in sample mode before bulk translation.",
            "After apply, run audit_renpy_translation.py and renpy_compile_launch_probe.py.",
        ]
    )

    json.dump(report, sys.stdout, ensure_ascii=False, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
