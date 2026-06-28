#!/usr/bin/env python3
"""Minimal regression tests for translation-unit export and project scan."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_UNITS = ROOT / "scripts" / "build_translation_units.py"
SCAN = ROOT / "scripts" / "scan_renpy_project.py"


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, encoding="utf-8", capture_output=True, check=True)


def write_fixture(project: Path) -> None:
    tl = project / "game" / "tl" / "schinese"
    tl.mkdir(parents=True)
    (project / "game").mkdir(exist_ok=True)
    (project / "game" / "script.rpy").write_text(
        'label start:\n    e "Hello [player]"\n',
        encoding="utf-8",
    )
    (project / "game" / "screens.rpy").write_text(
        "\n".join(
            [
                "screen say(who, what):",
                "    if what:",
                "        $ what = renpy.translate_string(what)",
                "        text what",
                "",
                "init python:",
                '    renpy.translate_string("Quick Menu")',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tl / "script.rpy").write_text(
        "\n".join(
            [
                "translate schinese start_abcd1234:",
                '    # e "Hello [player] {i}%s{/i}\\n100%% ready"',
                '    e ""',
                "",
                "translate schinese strings:",
                '    old "Start [player]"',
                '    new ""',
                "",
                '    old "gui/button.png"',
                '    new ""',
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_build_units(project: Path) -> None:
    completed = run([sys.executable, str(BUILD_UNITS), str(project), "--language", "schinese"], project)
    units = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    assert len(units) == 2, units
    kinds = {unit["kind"] for unit in units}
    assert kinds == {"dialogue", "string"}, units
    dialogue = next(unit for unit in units if unit["kind"] == "dialogue")
    assert dialogue["speaker"] == "e", dialogue
    assert dialogue["status"] == "empty", dialogue
    token_values = {token["value"] for token in dialogue["preserve_tokens"]}
    assert "[player]" in token_values, dialogue
    assert "{i}" in token_values and "{/i}" in token_values, dialogue
    assert "%s" in token_values and "%%" in token_values, dialogue
    assert r"\n" in token_values, dialogue
    assert all(unit["source"] != "gui/button.png" for unit in units), units


def test_scan(project: Path) -> None:
    completed = run([sys.executable, str(SCAN), str(project), "--language", "schinese"], project)
    report = json.loads(completed.stdout)
    detection = report["custom_translation_detection"]
    assert detection["summary"]["renpy_translate_string_calls"] == 2, detection
    assert detection["summary"]["screen_say_definitions"] == 1, detection
    assert detection["summary"]["what_translate_string_wrappers"] == 1, detection
    recommendation = report["translation_mode_recommendation"]
    assert recommendation["mode"] == "mixed", recommendation
    assert recommendation["reason"], recommendation
    assert recommendation["evidence"], recommendation


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="renpy-localizer-test-") as tmp:
        project = Path(tmp) / "project"
        write_fixture(project)
        run([sys.executable, str(BUILD_UNITS), "--help"], project)
        test_build_units(project)
        test_scan(project)
    print("translation unit and scan fixture tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
