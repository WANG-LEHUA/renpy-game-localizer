---
name: renpy-game-localizer
description: Localize Ren'Py visual novels and games into Simplified Chinese, including adult games. Use when Codex must inspect a Ren'Py project, generate or repair game/tl/chinese translations, build auditable translation units, translate dialogue and UI, preserve variables and text tags, standardize names and terminology, improve weak machine translations, fix Chinese fonts or overflowing dialogue, validate chapter coverage, and perform final localization QA.
---

# Ren'Py Game Localizer

Localize the game completely, preserving executable Ren'Py syntax and the author's intended tone.

## Workflow

Use a front-loaded, auditable pipeline. Prevent missing text, bad UI coverage, token drift, and font failures before paid translation instead of relying on repair passes.

1. Run `scripts/scan_renpy_project.py` and choose the language layer. Use `schinese` when `chinese` is polluted by legacy files, archived bytecode, duplicate labels, or mojibake.
2. Run `scripts/prepare_translation_layer.py` before any bulk translation. Prefer Ren'Py's own `translate <language>` command when the bundled runtime is detected; use decompile/runtime extraction only as fallbacks for compiled or archived projects.
3. Build JSONL translation units with `scripts/build_translation_units.py`. Use the units as the review, provider, apply, resume, and audit boundary.
4. Confirm preparation and unit gates: generated templates exist, expected menu/save/history UI keys are present, a CJK font/style setup exists, `old` string keys remain source text, and unit `preserve_tokens` cover placeholders/tags/percent/escapes.
5. Create or update `localization_work/glossary.md` from characters, UI terms, recurring locations, adult vocabulary, and do-not-translate rules. If the user gives no name policy, keep names conservative and record it.
6. Translate a representative sample before bulk work. Translate only writable targets from units: dialogue target lines and `new` values. Never send `old`, labels, screen actions, variables, Python, file paths, or image names as targets.
7. Audit provider output against unit `preserve_tokens`, apply only accepted translations, then run `scripts/audit_renpy_translation.py`.
8. For DeepSeek-compatible bulk translation, read `references/llm-bulk-translation.md`; treat it as the current bundled backend and keep its sample-first, resumable high-concurrency flow.
9. Validate before handoff: run audit, font coverage when relevant, compile/launch probe, and sample visual surfaces including dialogue, choices, history, save/load, preferences, achievements/gallery, and chapter titles.

Keep repair scripts as fallback tools. If a repair pattern becomes common, move it into `prepare_translation_layer.py` or validation gates rather than adding more ad hoc workflow steps.

Read [references/workflow.md](references/workflow.md) for detailed project discovery, batching, and repair procedures.
Read the "Agent-orchestrated pipeline" section in [references/workflow.md](references/workflow.md) when the user wants the whole localization flow driven through this skill. Use `scripts/localization_stage_report.py` as the stage aggregator when you need a machine-readable status report and next-step signals.
Read [references/translation-units.md](references/translation-units.md) before exporting JSONL units, designing provider state, or applying translated output.
Read [references/quality-rules.md](references/quality-rules.md) before translating dialogue or changing text layout.
Read [references/archive-workflow.md](references/archive-workflow.md) when `.rpa` archives or legacy archived translations are present.
Read [references/llm-bulk-translation.md](references/llm-bulk-translation.md) before using a paid LLM API for bulk translation.
Read [references/glossary-template.md](references/glossary-template.md) when drafting or repairing a project glossary.
Use `scripts/audit_font_coverage.py` when CJK text renders as missing-glyph boxes or when choosing a Chinese font.

## Helper Scripts

- Primary: `scripts/localization_stage_report.py`, `scripts/scan_renpy_project.py`, `scripts/prepare_translation_layer.py`, `scripts/build_translation_units.py`, `scripts/deepseek_renpy_tl_translate.py`, `scripts/audit_renpy_translation.py`, and `scripts/renpy_compile_launch_probe.py`.
- Preparation helpers used by the primary flow: `scripts/add_ui_string_overrides.py`, `scripts/extract_rpyc_translations.py`, `scripts/extract_rpa.py`, and `scripts/audit_font_coverage.py`.
- Repair fallbacks: `scripts/repair_renpy_translation.py`, `scripts/rebuild_string_blocks.py`, and `scripts/repack_rpa_without_paths.py`. Use them only after a validation gate identifies a concrete issue.

## Editing Rules

- Use `apply_patch` for manual file edits.
- Preserve user changes and unrelated files.
- Never edit `.rpyc`; edit `.rpy` and let Ren'Py regenerate compiled files.
- Do not translate identifiers inside `[variables]`, `{tags}`, Python expressions, file paths, image names, labels, or screen actions.
- Preserve intentional formatting such as `{i}`, `{b}`, `{color}`, `{size}`, escaped quotes, and interpolation conversions.
- Keep source comments when Ren'Py generated them; they are useful for pairing originals with translations.
- Check actual usage before changing a shared GUI style.
- When writing Ren'Py string literals, escape backslashes, quotes, and real newline characters as `\n`.
- Do not leave visible source strings untranslated simply because they contain no Latin letters; handle `Off`, `<`, `>`, `...`, and already-Chinese legacy text deliberately.

## Completion Standard

Consider the localization complete only when:

- every requested chapter and UI surface is covered;
- no significant untranslated prose remains;
- no empty translated strings remain except intentionally hidden Ren'Py tags;
- placeholders and text tags match their sources;
- names and terminology are consistent;
- representative long lines fit the textbox;
- the active CJK font covers all translated CJK characters, or known missing glyphs are documented;
- Ren'Py reports no new script errors and no legacy translation layer is polluting the active language;
- the final handoff names changed files, validation performed, and any untestable visual risks.
