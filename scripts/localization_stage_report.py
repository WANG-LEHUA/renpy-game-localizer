#!/usr/bin/env python3
"""Run Ren'Py localization stages and emit decision signals for an agent.

This is intentionally a guided runner rather than a one-command localizer.
It automates repeatable probes and JSON aggregation, while leaving policy
decisions such as language choice, paid translation approval, concurrency, and
visual acceptance to the agent reading the report.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def project_root(root: Path) -> Path:
    root = root.resolve()
    if (root / "game").is_dir():
        return root
    if root.name.lower() == "game" and root.is_dir():
        return root.parent
    raise SystemExit(f"Could not find Ren'Py project root for: {root}")


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
        result: dict[str, Any] = {
            "ran": True,
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "command": command,
            "stdout_tail": completed.stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:],
        }
        try:
            result["json"] = json.loads(completed.stdout)
        except Exception:
            pass
        return result
    except subprocess.TimeoutExpired as exc:
        return {
            "ran": True,
            "ok": False,
            "timeout": True,
            "command": command,
            "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
        }
    except Exception as exc:
        return {"ran": True, "ok": False, "command": command, "error": repr(exc)}


def parse_audit(stdout: str) -> dict[str, Any]:
    match = re.search(r"Audited\s+(\d+)\s+files:\s+(\d+)\s+errors,\s+(\d+)\s+warnings,\s+(\d+)\s+info\.", stdout)
    if not match:
        return {"parsed": False}
    return {
        "parsed": True,
        "files": int(match.group(1)),
        "errors": int(match.group(2)),
        "warnings": int(match.group(3)),
        "info": int(match.group(4)),
    }


def scan_stage(root: Path, language: str, timeout: int) -> dict[str, Any]:
    return run_command(
        [sys.executable, str(SCRIPT_DIR / "scan_renpy_project.py"), str(root), "--language", language],
        root,
        timeout,
    )


def prepare_stage(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        str(SCRIPT_DIR / "prepare_translation_layer.py"),
        str(root),
        "--language",
        args.language,
    ]
    if args.apply_prepare:
        command.append("--apply")
    if args.generate_official:
        command.append("--generate-official")
    if args.update_existing_ui:
        command.append("--update-existing-ui")
    if args.font:
        command.extend(["--font", str(args.font)])
    return run_command(command, root, args.timeout)


def audit_stage(root: Path, language: str, timeout: int) -> dict[str, Any]:
    result = run_command(
        [sys.executable, str(SCRIPT_DIR / "audit_renpy_translation.py"), str(root), "--language", language],
        root,
        timeout,
    )
    result["summary"] = parse_audit(result.get("stdout_tail", ""))
    return result


def font_stage(root: Path, language: str, font: Path | None, timeout: int) -> dict[str, Any]:
    if not font:
        return {"ran": False, "reason": "no --font provided"}
    return run_command(
        [
            sys.executable,
            str(SCRIPT_DIR / "audit_font_coverage.py"),
            str(root),
            "--language",
            language,
            "--font",
            str(font),
        ],
        root,
        timeout,
    )


def launch_stage(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    if args.skip_launch:
        return {"ran": False, "reason": "--skip-launch"}
    if not args.exe:
        return {"ran": False, "reason": "no --exe provided"}
    command = [
        sys.executable,
        str(SCRIPT_DIR / "renpy_compile_launch_probe.py"),
        str(root),
        "--exe",
        str(args.exe),
        "--launch-seconds",
        str(args.launch_seconds),
    ]
    if args.skip_compile:
        command.append("--skip-compile")
    if args.strict_compile:
        command.append("--strict-compile")
    return run_command(command, root, max(args.timeout, args.launch_seconds + 30))


def latest_language_report(scan_json: dict[str, Any], language: str) -> dict[str, Any]:
    for item in scan_json.get("language_reports", []):
        if item.get("language") == language:
            return item
    return {}


def add_decision(decisions: list[dict[str, Any]], severity: str, gate: str, message: str, next_action: str) -> None:
    decisions.append(
        {
            "severity": severity,
            "gate": gate,
            "message": message,
            "next_action": next_action,
        }
    )


def build_decisions(report: dict[str, Any], language: str) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    scan_json = report.get("stages", {}).get("scan", {}).get("json") or {}
    language_report = latest_language_report(scan_json, language)
    signals = set(scan_json.get("signals", []))

    if "compiled_only_project" in signals or scan_json.get("files", {}).get("rpa", 0):
        add_decision(
            decisions,
            "info",
            "discovery",
            "Project contains archives or compiled scripts.",
            "Prefer official Ren'Py generation first; if incomplete, extract/decompile before paid translation.",
        )
    if any(str(signal).endswith("_layer_may_be_polluted") for signal in signals):
        add_decision(
            decisions,
            "blocker",
            "language_layer",
            "Selected language layer may contain polluted old keys, duplicate keys, or mojibake.",
            "Use a clean language layer or rebuild affected string blocks before translation.",
        )
    if language_report.get("missing_extended_ui_keys"):
        add_decision(
            decisions,
            "blocker",
            "ui_strings",
            f"Missing UI keys: {len(language_report['missing_extended_ui_keys'])}.",
            "Run prepare_translation_layer.py --apply --update-existing-ui before bulk translation.",
        )
    if language_report.get("missing_discovered_ui_keys"):
        add_decision(
            decisions,
            "blocker",
            "ui_runtime_strings",
            f"Missing strings discovered in compiled UI: {len(language_report['missing_discovered_ui_keys'])}.",
            "Add the discovered UI keys to add_ui_string_overrides.py or pass them with --extra, then rerun the UI helper.",
        )
    if language_report.get("empty_new_lines") or language_report.get("empty_dialogue_targets"):
        add_decision(
            decisions,
            "needs_translation",
            "translation_coverage",
            "Translation targets still contain empty lines.",
            "Run a sample LLM pass first, inspect it, then run resumable bulk translation.",
        )

    prepare = report.get("stages", {}).get("prepare")
    if prepare and prepare.get("ran") and not prepare.get("ok"):
        add_decision(
            decisions,
            "warn",
            "prepare",
            "Preparation command did not complete cleanly.",
            "Inspect prepare stderr/stdout and choose official generation, extraction, or manual repair.",
        )

    audit = report.get("stages", {}).get("audit")
    audit_summary = (audit or {}).get("summary", {})
    if audit and audit.get("ran"):
        if audit_summary.get("errors", 0):
            add_decision(
                decisions,
                "blocker",
                "audit",
                f"Audit found {audit_summary['errors']} errors.",
                "Fix structural translation errors before launching or handing off.",
            )
        elif audit_summary.get("warnings", 0) or audit_summary.get("info", 0):
            add_decision(
                decisions,
                "review",
                "audit",
                f"Audit has {audit_summary.get('warnings', 0)} warnings and {audit_summary.get('info', 0)} info items.",
                "Review suspicious untranslated or long lines; repair only true positives.",
            )

    font = report.get("stages", {}).get("font_coverage")
    if font and font.get("ran") and not font.get("ok"):
        add_decision(
            decisions,
            "blocker",
            "font",
            "Font coverage check failed.",
            "Switch to a CJK font that covers all translated characters, then rerun the audit.",
        )

    launch = report.get("stages", {}).get("launch_probe")
    if launch and launch.get("ran") and not launch.get("ok"):
        add_decision(
            decisions,
            "blocker",
            "launch",
            "Launch or compile probe failed.",
            "Inspect traceback changes and fix startup errors before handoff.",
        )

    if not decisions:
        add_decision(
            decisions,
            "pass",
            "handoff",
            "No blocking automated gates were detected.",
            "Proceed with agent visual QA and final handoff notes.",
        )
    return decisions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Ren'Py project root or game directory")
    parser.add_argument("--language", default="chinese")
    parser.add_argument(
        "--stage",
        choices=("preflight", "prepare", "validate", "handoff", "all"),
        default="preflight",
        help="Stage bundle to run. Paid LLM calls are never run by this script.",
    )
    parser.add_argument("--apply-prepare", action="store_true", help="Allow prepare stage to write setup/UI files")
    parser.add_argument("--generate-official", action="store_true", help="Ask prepare stage to run official translate generation")
    parser.add_argument("--update-existing-ui", action="store_true", help="Normalize existing known UI translations")
    parser.add_argument("--font", type=Path, help="Font path for font coverage audit and optional preparation")
    parser.add_argument("--exe", type=Path, help="Game executable for launch probe")
    parser.add_argument("--skip-launch", action="store_true")
    parser.add_argument("--skip-compile", action="store_true")
    parser.add_argument("--strict-compile", action="store_true")
    parser.add_argument("--launch-seconds", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    root = project_root(args.root)
    report: dict[str, Any] = {
        "root": str(root),
        "language": args.language,
        "stage": args.stage,
        "policy": {
            "paid_llm_calls": "not_run_by_this_script",
            "agent_role": "read_results_and_choose_next_step",
        },
        "stages": {},
    }

    report["stages"]["scan"] = scan_stage(root, args.language, args.timeout)

    if args.stage in {"prepare", "all"}:
        report["stages"]["prepare"] = prepare_stage(args, root)
        report["stages"]["scan_after_prepare"] = scan_stage(root, args.language, args.timeout)
    if args.stage in {"validate", "handoff", "all"}:
        report["stages"]["audit"] = audit_stage(root, args.language, args.timeout)
        report["stages"]["font_coverage"] = font_stage(root, args.language, args.font, args.timeout)
    if args.stage in {"handoff", "all"}:
        report["stages"]["launch_probe"] = launch_stage(args, root)

    if "scan_after_prepare" in report["stages"]:
        initial_scan = report["stages"]["scan"]
        report["stages"]["scan"] = report["stages"].pop("scan_after_prepare")
        report["stages"]["initial_scan"] = initial_scan
    report["agent_decisions"] = build_decisions(report, args.language)

    json.dump(report, sys.stdout, ensure_ascii=False, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
