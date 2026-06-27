from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


MODEL = "deepseek-v4-flash"
API_URL = "https://api.deepseek.com/chat/completions"

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


@dataclass(frozen=True)
class Unit:
    key: str
    file: str
    source_line_no: int
    target_line_no: int
    original: str
    speaker: str
    kind: str


def get_api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key

    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as env_key:
                value, _ = winreg.QueryValueEx(env_key, "DEEPSEEK_API_KEY")
                if value:
                    return str(value)
        except OSError:
            pass

    raise RuntimeError("DEEPSEEK_API_KEY is not available.")


def decode_renpy_string(literal: str) -> str:
    body = literal[1:-1]
    return bytes(body, "utf-8").decode("unicode_escape")


def encode_renpy_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"') + '"'


def is_empty_literal(literal: str) -> bool:
    return decode_renpy_string(literal) == ""


def collect_units(root: Path, language: str) -> list[Unit]:
    tl_root = root / "game" / "tl" / language
    units: list[Unit] = []

    for path in sorted(tl_root.rglob("*.rpy")):
        rel_path = path.relative_to(root).as_posix()
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]

            old_match = OLD_RE.match(line)
            if old_match:
                old_text = decode_renpy_string(old_match.group("quote"))
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    new_match = NEW_RE.match(lines[j])
                    if new_match and is_empty_literal(new_match.group("quote")) and should_translate(old_text):
                        units.append(
                            Unit(
                                key=f"{rel_path}:{j + 1}",
                                file=rel_path,
                                source_line_no=i + 1,
                                target_line_no=j + 1,
                                original=old_text,
                                speaker="",
                                kind="string",
                            )
                        )
                i += 1
                continue

            source_match = SOURCE_COMMENT_RE.match(line)
            if source_match:
                source_text = decode_renpy_string(source_match.group("quote"))
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    target_match = TARGET_RE.match(lines[j])
                    if target_match and is_empty_literal(target_match.group("quote")) and should_translate(source_text):
                        units.append(
                            Unit(
                                key=f"{rel_path}:{j + 1}",
                                file=rel_path,
                                source_line_no=i + 1,
                                target_line_no=j + 1,
                                original=source_text,
                                speaker=source_match.group("speaker") or "",
                                kind="dialogue",
                            )
                        )
                i += 1
                continue

            i += 1

    return units


def should_translate(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped in {"???", "MC", "On", "Off", "<", ">"}:
        return False
    if re.fullmatch(r"[\W_]+", stripped):
        return False
    return True


def load_glossary(root: Path) -> str:
    work_dir = root / "localization_work"
    parts = []
    for name in ("glossary.md", "glossary_overrides.md"):
        path = work_dir / name
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


def load_done(path: Path) -> dict[str, str]:
    done: dict[str, str] = {}
    if not path.exists():
        return done
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                item = json.loads(line)
                done[item["key"]] = item["translation"]
    return done


def append_done(path: Path, items: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def build_prompt(items: list[Unit], glossary: str) -> str:
    payload = [
        {
            "id": item.key,
            "speaker": item.speaker,
            "kind": item.kind,
            "file": item.file,
            "text": item.original,
        }
        for item in items
    ]
    return (
        "Translate the following Ren'Py translation entries into Simplified Chinese.\n"
        "Use this project glossary exactly:\n"
        f"{glossary}\n\n"
        "Rules:\n"
        "- Return only JSON: {\"translations\":[{\"id\":\"...\",\"text\":\"...\"}]}.\n"
        "- Preserve all Ren'Py variables like [player_name] and tags like {color=#fff}, {/color}, {image=...} exactly.\n"
        "- Preserve line-break escapes as \\n where present.\n"
        "- Keep character names in English according to the glossary.\n"
        "- Do not preserve ordinary uppercase emphasis words like ME, YOU, DID, THIS, REALLY; translate their meaning into Chinese emphasis.\n"
        "- Translate adult content directly and naturally; do not censor or intensify.\n"
        "- If the source contains mojibake for apostrophes, infer the intended English before translating.\n"
        "- Keep UI/menu choices short.\n\n"
        + json.dumps({"items": payload}, ensure_ascii=False)
    )


def call_deepseek(api_key: str, items: list[Unit], glossary: str, max_retries: int = 6) -> dict:
    data = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a careful Ren'Py game localizer for Simplified Chinese."},
            {"role": "user", "content": build_prompt(items, glossary)},
        ],
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")

    for attempt in range(max_retries):
        request = urllib.request.Request(
            API_URL,
            data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read().decode("utf-8")
            response_payload = json.loads(raw)
            content = response_payload["choices"][0]["message"]["content"]
            parsed = parse_json_content(content)
            return {
                "translations": validate(items, parsed.get("translations", [])),
                "usage": response_payload.get("usage", {}),
            }
        except urllib.error.HTTPError as error:
            if error.code not in {408, 409, 429, 500, 502, 503, 504} or attempt == max_retries - 1:
                detail = error.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"DeepSeek HTTP {error.code}: {detail[:500]}") from error
        except Exception:
            if attempt == max_retries - 1:
                raise
        time.sleep((2**attempt) + random.random())

    raise RuntimeError("DeepSeek request failed after retries.")


def parse_json_content(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?", "", content).strip()
        content = re.sub(r"```$", "", content).strip()
    return json.loads(content)


def validate(items: list[Unit], translations: list[dict]) -> list[dict[str, str]]:
    wanted = {item.key: item for item in items}
    output: list[dict[str, str]] = []

    for entry in translations:
        key = entry.get("id")
        text = entry.get("text")
        if key not in wanted or not isinstance(text, str):
            continue
        source = wanted[key].original
        if re.findall(r"\[[^\]]+\]", source) != re.findall(r"\[[^\]]+\]", text):
            text = source
        if re.findall(r"\{[^}]+\}", source) != re.findall(r"\{[^}]+\}", text):
            text = source
        output.append({"key": key, "translation": text})

    found = {entry["key"] for entry in output}
    for item in items:
        if item.key not in found:
            output.append({"key": item.key, "translation": item.original})
    return output


def chunked(items: list[Unit], size: int) -> list[list[Unit]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def command_translate(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    state = root / "localization_work" / f"deepseek_{args.language}.jsonl"
    usage_state = root / "localization_work" / f"deepseek_{args.language}_usage.jsonl"
    units = collect_units(root, args.language)
    done = load_done(state)
    pending = [unit for unit in units if unit.key not in done]
    if args.path_filter:
        pending = [unit for unit in pending if args.path_filter.lower() in unit.file.lower()]
    if args.limit:
        pending = pending[: args.limit]

    print(f"Candidates: {len(units)}")
    print(f"Already translated: {len(done)}")
    print(f"Pending this run: {len(pending)}")
    if args.dry_run or not pending:
        return

    api_key = get_api_key()
    glossary = load_glossary(root)
    batches = chunked(pending, args.batch_size)

    def worker(batch: list[Unit]) -> dict:
        return call_deepseek(api_key, batch, glossary)

    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        future_map = {executor.submit(worker, batch): batch for batch in batches}
        for future in concurrent.futures.as_completed(future_map):
            batch = future_map[future]
            result = future.result()
            append_done(state, result["translations"])
            if result.get("usage"):
                usage_entry = {
                    "batch_size": len(batch),
                    "usage": result["usage"],
                    "first_key": batch[0].key,
                    "last_key": batch[-1].key,
                }
                usage_state.parent.mkdir(parents=True, exist_ok=True)
                with usage_state.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(usage_entry, ensure_ascii=False) + "\n")
            completed += len(batch)
            print(f"Translated {completed}/{len(pending)}")


def command_apply(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    state = root / "localization_work" / f"deepseek_{args.language}.jsonl"
    translations = load_done(state)
    units = {unit.key: unit for unit in collect_units(root, args.language)}

    by_file: dict[str, dict[int, Unit]] = {}
    for key, unit in units.items():
        if key in translations:
            by_file.setdefault(unit.file, {})[unit.target_line_no] = unit

    changed = 0
    for rel_file, file_units in sorted(by_file.items()):
        path = root / rel_file
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        modified = False
        for line_no, unit in file_units.items():
            original_line = lines[line_no - 1]
            encoded = encode_renpy_string(translations[unit.key])

            new_match = NEW_RE.match(original_line)
            if new_match:
                new_line = new_match.group("indent") + "new " + encoded + new_match.group("suffix")
            else:
                target_match = TARGET_RE.match(original_line)
                if not target_match:
                    continue
                new_line = (
                    target_match.group("indent")
                    + ((target_match.group("speaker") + " ") if target_match.group("speaker") else "")
                    + encoded
                    + target_match.group("suffix")
                )

            if new_line != original_line:
                lines[line_no - 1] = new_line
                changed += 1
                modified = True

        if modified:
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Applied translations to {changed} line(s).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate Ren'Py tl/<language> files with DeepSeek.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    translate = subparsers.add_parser("translate")
    translate.add_argument("--root", type=Path, default=Path("."))
    translate.add_argument("--language", default="schinese")
    translate.add_argument("--dry-run", action="store_true")
    translate.add_argument("--limit", type=int, default=0)
    translate.add_argument("--path-filter", default="")
    translate.add_argument("--batch-size", type=int, default=40)
    translate.add_argument("--concurrency", type=int, default=16)
    translate.set_defaults(func=command_translate)

    apply = subparsers.add_parser("apply")
    apply.add_argument("--root", type=Path, default=Path("."))
    apply.add_argument("--language", default="schinese")
    apply.set_defaults(func=command_apply)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
