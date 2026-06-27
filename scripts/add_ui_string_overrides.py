#!/usr/bin/env python3
"""Add missing Ren'Py UI string translations without duplicating old keys."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


OLD_RE = re.compile(r'^\s*old\s+(?P<quote>"(?:\\.|[^"\\])*")')
NEW_RE = re.compile(r'^(?P<indent>\s*)new\s+(?P<quote>"(?:\\.|[^"\\])*")')

DEFAULT_UI_TRANSLATIONS = {'Start': '开始',
 'Load': '读取',
 'Save': '保存',
 'Preferences': '设置',
 'Settings': '设置',
 'Prefs': '设置',
 'About': '关于',
 'Help': '帮助',
 'Quit': '退出',
 'Return': '返回',
 'Back': '返回',
 'Main Menu': '主菜单',
 'New Game': '新游戏',
 'Continue': '继续',
 'Gallery': '画廊',
 'Achievements': '成就',
 'Extras': '额外内容',
 'Credits': '制作人员',
 'History': '历史',
 'Menu': '菜单',
 'Auto': '自动',
 'Quick': '快速',
 'Q.Save': '快存',
 'Q.Load': '快读',
 'Page': '页',
 'Page {}': '第 {} 页',
 'File': '存档',
 'Empty Slot.': '空存档位。',
 'Empty Slot': '空存档位',
 'Next': '下一页',
 'Previous': '上一页',
 'Newest': '最新',
 'Oldest': '最旧',
 'Yes': '是',
 'No': '否',
 'On': '开',
 'Off': '关',
 'Confirm': '确认',
 'Cancel': '取消',
 'Delete': '删除',
 'Auto Save': '自动存档',
 'Quick Save': '快速存档',
 'Quick Load': '快速读取',
 'Display': '显示',
 'Window': '窗口',
 'Fullscreen': '全屏',
 'Rollback Side': '回滚区域',
 'Disable': '禁用',
 'Left': '左侧',
 'Right': '右侧',
 'Skip': '快进',
 'Unseen Text': '未读文本',
 'After Choices': '选项后继续',
 'Transitions': '转场效果',
 'Text Speed': '文字速度',
 'Auto-Forward Time': '自动前进时间',
 'Music Volume': '音乐音量',
 'Sound Volume': '音效音量',
 'Voice Volume': '语音音量',
 'Mute All': '全部静音',
 'Test': '测试',
 'Language': '语言',
 'English': '英文',
 'Chinese': '中文',
 'English Mode': '英文模式',
 'Chinese Mode': '中文模式',
 'Windowed': '窗口模式',
 'Full Screen': '全屏',
 'Fullscreen Mode': '全屏模式',
 'Window Mode': '窗口模式',
 'Accessibility': '无障碍',
 'Accessibility Menu': '无障碍菜单',
 'Self-voicing': '自助朗读',
 'Self-Voicing': '自助朗读',
 'Clipboard voicing': '剪贴板朗读',
 'Debug voicing': '调试朗读',
 'Font Override': '字体覆盖',
 'Default': '默认',
 'OpenDyslexic': 'OpenDyslexic 字体',
 'High Contrast Text': '高对比度文字',
 'Text Size Scaling': '文字大小缩放',
 'Line Spacing Scaling': '行距缩放',
 'Reset': '重置',
 'Done': '完成',
 'Quick Menu': '快捷菜单',
 'Textbox Opacity': '文本框透明度',
 'Automatic saves': '自动存档',
 'Quick saves': '快速存档',
 'End Replay': '结束回放',
 'Hide': '隐藏',
 'Skipping': '快进中',
 'The dialogue history is empty.': '对话历史为空。',
 'Accesses the game menu.': '打开游戏菜单。',
 'Hides the user interface.': '隐藏用户界面。',
 'Skips dialogue while held down.': '按住时快进对话。',
 'Toggles dialogue skipping.': '切换对话快进。',
 'Advances dialogue and activates the interface.': '推进对话并激活界面。',
 'Advances dialogue without selecting choices.': '推进对话，不选择选项。',
 'Rolls back to earlier dialogue.': '回滚到之前的对话。',
 'Rolls forward to later dialogue.': '前进到后续对话。',
 'Takes a screenshot.': '截取屏幕。',
 'Navigate the interface.': '在界面中导航。',
 'Toggles assistive {a=https://www.renpy.org/l/voicing}self-voicing{/a}.': '切换辅助{a=https://www.renpy.org/l/voicing}自动朗读{/a}。',
 'Keyboard': '键盘',
 'Mouse': '鼠标',
 'Gamepad': '手柄',
 'Calibrate': '校准',
 'Enter': '回车',
 'Space': '空格',
 'Arrow Keys': '方向键',
 'Escape': 'Esc',
 'Ctrl': 'Ctrl',
 'Tab': 'Tab',
 'Page Up': '上一页',
 'Page Down': '下一页',
 'Left Click': '左键点击',
 'Middle Click': '中键点击',
 'Right Click': '右键点击',
 'Mouse Wheel Down': '鼠标滚轮向下',
 'Mouse Wheel Up\nClick Rollback Side': '鼠标滚轮向上\n点击回滚区域',
 'D-Pad, Sticks': '方向键、摇杆',
 'Start, Guide': 'Start/Guide',
 'Y/Top Button': 'Y/顶部按钮',
 'Right Trigger\nA/Bottom Button': '右扣机\nA/底部按钮',
 'Left Trigger\nLeft Shoulder': '左扣机\n左肩键',
 'Right Shoulder': '右肩键',
 'Version [config.version!t]\n': '版本 [config.version!t]\n',
 "Made with Ren'Py": "使用 Ren'Py 制作",
 'Patreon': 'Patreon',
 'Opens {u}https://patreon.com/grymgudinnagames{/u} in your browser': '在浏览器中打开 '
                                                                      '{u}https://patreon.com/grymgudinnagames{/u}',
 '{#auto_page}A': '自',
 '{#quick_page}Q': '快',
 '{#file_time}%A, %B %d %Y, %H:%M': '%%Y-%%m-%%d %%H:%%M',
 '<': '<',
 '>': '>',
 'empty slot': '空存档位'}



def project_root(root: Path) -> Path:
    root = root.resolve()
    if (root / "game").is_dir():
        return root
    if root.name == "game":
        return root.parent
    raise SystemExit(f"Could not find project root for: {root}")


def decode_quote(quote: str) -> str:
    try:
        return ast.literal_eval(quote)
    except Exception:
        return bytes(quote[1:-1], "utf-8").decode("unicode_escape", errors="replace")


def encode_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"') + '"'


def collect_old_keys(language_root: Path) -> set[str]:
    keys: set[str] = set()
    for path in sorted(language_root.rglob("*.rpy")):
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            match = OLD_RE.match(line)
            if match:
                keys.add(decode_quote(match.group("quote")))
    return keys


def update_existing_targets(language_root: Path, translations: dict[str, str]) -> list[str]:
    updated: set[str] = set()
    for path in sorted(language_root.rglob("*.rpy")):
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        changed = False
        index = 0
        while index < len(lines):
            old = OLD_RE.match(lines[index])
            if not old:
                index += 1
                continue
            source = decode_quote(old.group("quote"))
            if source not in translations:
                index += 1
                continue
            for next_index in range(index + 1, min(index + 6, len(lines))):
                new = NEW_RE.match(lines[next_index])
                if not new:
                    continue
                replacement = f'{new.group("indent")}new {encode_quote(translations[source])}'
                if lines[next_index] != replacement:
                    lines[next_index] = replacement
                    changed = True
                    updated.add(source)
                break
            index += 1
        if changed:
            path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return sorted(updated)


def parse_extra(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"--extra must use SOURCE=TARGET form: {value}")
        source, target = value.split("=", 1)
        if not source:
            raise SystemExit("--extra source cannot be empty")
        parsed[source] = target
    return parsed


def render_block(language: str, items: dict[str, str]) -> str:
    lines = [
        f"translate {language} strings:",
        "",
        "    # Added by renpy-game-localizer: UI strings missing from archived screens.",
    ]
    for source, target in sorted(items.items()):
        lines.append(f"    old {encode_quote(source)}")
        lines.append(f"    new {encode_quote(target)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Ren'Py project root or game directory")
    parser.add_argument("--language", default="chinese")
    parser.add_argument("--output-name", default="zz_ui_strings.rpy")
    parser.add_argument("--only", action="append", default=[], help="Only include this source key; repeatable")
    parser.add_argument("--extra", action="append", default=[], help="Additional SOURCE=TARGET entry; repeatable")
    parser.add_argument("--apply", action="store_true", help="Write the override file; default is dry-run")
    parser.add_argument("--update-existing", action="store_true", help="Also replace existing new targets for known UI keys")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    root = project_root(args.root)
    language_root = root / "game" / "tl" / args.language
    if not language_root.is_dir():
        raise SystemExit(f"Translation layer does not exist: {language_root}")

    translations = dict(DEFAULT_UI_TRANSLATIONS)
    translations.update(parse_extra(args.extra))
    if args.only:
        requested = set(args.only)
        translations = {key: value for key, value in translations.items() if key in requested}

    existing = collect_old_keys(language_root)
    missing = {key: value for key, value in translations.items() if key not in existing}
    output_path = language_root / args.output_name
    updated_existing: list[str] = []

    if args.apply and missing:
        if output_path.exists():
            current = output_path.read_text(encoding="utf-8-sig", errors="replace").rstrip()
            addition = render_block(args.language, missing).strip()
            output_path.write_text(current + "\n\n" + addition + "\n", encoding="utf-8", newline="\n")
        else:
            output_path.write_text(render_block(args.language, missing), encoding="utf-8", newline="\n")
    if args.apply and args.update_existing:
        updated_existing = update_existing_targets(language_root, translations)

    report: dict[str, Any] = {
        "root": str(root),
        "language": args.language,
        "output": str(output_path),
        "applied": args.apply,
        "existing_requested_keys": sorted(set(translations) & existing),
        "missing_keys": sorted(missing),
        "updated_existing_keys": updated_existing,
        "added": missing if args.apply else {},
        "would_add": missing if not args.apply else {},
    }
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
