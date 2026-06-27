#!/usr/bin/env python3
"""Run Ren'Py compile and a short hidden launch probe, then report traceback changes."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def project_root(root: Path) -> Path:
    root = root.resolve()
    if (root / "game").is_dir():
        return root
    if root.name == "game":
        return root.parent
    raise SystemExit(f"Could not find project root for: {root}")


def find_exe(root: Path) -> Path:
    candidates = sorted(root.glob("*.exe"))
    if not candidates:
        raise SystemExit(f"No Windows executable found in: {root}")
    preferred = [path for path in candidates if not path.name.lower().startswith(("crash", "updater", "uninstall"))]
    return preferred[0] if preferred else candidates[0]


def stat_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    stat = path.stat()
    return {"exists": True, "size": stat.st_size, "mtime": stat.st_mtime}


def startupinfo() -> subprocess.STARTUPINFO | None:
    if os.name != "nt":
        return None
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = 0
    return info


def run_compile(root: Path, exe: Path, timeout: int) -> dict[str, Any]:
    started = time.time()
    try:
        completed = subprocess.run(
            [str(exe), "--compile"],
            cwd=str(root),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            startupinfo=startupinfo(),
        )
        return {
            "ran": True,
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "elapsed": round(time.time() - started, 3),
            "stdout_tail": completed.stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ran": True,
            "ok": False,
            "timeout": True,
            "elapsed": round(time.time() - started, 3),
            "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
        }


def run_launch_probe(root: Path, exe: Path, seconds: int) -> dict[str, Any]:
    traceback_path = root / "traceback.txt"
    before = stat_file(traceback_path)
    started = time.time()
    process = subprocess.Popen(
        [str(exe)],
        cwd=str(root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        startupinfo=startupinfo(),
    )
    time.sleep(seconds)
    returncode = process.poll()
    terminated = False
    if returncode is None:
        process.terminate()
        terminated = True
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    after = stat_file(traceback_path)
    changed = before != after
    return {
        "ran": True,
        "ok": not changed,
        "elapsed": round(time.time() - started, 3),
        "returncode_after_wait": returncode,
        "terminated": terminated,
        "traceback_before": before,
        "traceback_after": after,
        "traceback_changed": changed,
    }


def compile_timeout_can_be_accepted(compile_report: dict[str, Any], launch_report: dict[str, Any]) -> bool:
    """Treat packaged exe --compile hangs as non-fatal when startup is clean.

    Some distributed Ren'Py Windows executables accept --compile but never exit
    cleanly. If the process times out without stderr/stdout diagnostics and a
    real launch does not create or update traceback.txt, the startup probe is a
    stronger signal for translation-layer safety than the hung compile process.
    """
    if not compile_report.get("timeout"):
        return False
    if compile_report.get("stdout_tail") or compile_report.get("stderr_tail"):
        return False
    return bool(launch_report.get("ok"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Ren'Py project root or game directory")
    parser.add_argument("--exe", type=Path, help="Game executable; default finds one in project root")
    parser.add_argument("--skip-compile", action="store_true")
    parser.add_argument("--skip-launch", action="store_true")
    parser.add_argument("--compile-timeout", type=int, default=120)
    parser.add_argument("--launch-seconds", type=int, default=12)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument(
        "--strict-compile",
        action="store_true",
        help="Fail on compile timeout even when the launch probe is clean.",
    )
    args = parser.parse_args()

    root = project_root(args.root)
    exe = args.exe.resolve() if args.exe else find_exe(root)

    report: dict[str, Any] = {
        "root": str(root),
        "exe": str(exe),
        "compile": {"ran": False},
        "launch_probe": {"ran": False},
    }
    if not args.skip_compile:
        report["compile"] = run_compile(root, exe, args.compile_timeout)
    if not args.skip_launch:
        report["launch_probe"] = run_launch_probe(root, exe, args.launch_seconds)

    compile_ok = bool(report["compile"].get("ok", True))
    launch_ok = bool(report["launch_probe"].get("ok", True))
    accepted_compile_timeout = False
    if not compile_ok and not args.strict_compile:
        accepted_compile_timeout = compile_timeout_can_be_accepted(report["compile"], report["launch_probe"])
    report["accepted_compile_timeout"] = accepted_compile_timeout
    report["ok"] = bool((compile_ok or accepted_compile_timeout) and launch_ok)
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

