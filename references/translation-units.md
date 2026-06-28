# Translation Units

Use translation units as the auditable boundary between Ren'Py template preparation, LLM/provider translation, apply, and QA.

## Build Units

After `prepare_translation_layer.py` creates or updates `game/tl/<language>`, export units before paid translation:

```powershell
python <skill>/scripts/build_translation_units.py <project-root> --language schinese --output localization_work/translation_units_schinese.jsonl
python <skill>/scripts/build_translation_units.py <project-root> --language schinese --pending-only --output localization_work/translation_units_pending_schinese.jsonl
```

The script is read-only. It never edits `.rpy` files.

## Unit Schema

Each JSONL row is one writable Ren'Py translation target:

- `id`: stable hash id derived from schema version, language, kind, file, label, speaker, source, and occurrence.
- `kind`: `dialogue` for source-comment/target-line pairs, or `string` for `translate <language> strings` `old/new` pairs.
- `file`: project-relative `.rpy` path.
- `line`: writable target line number, meaning the dialogue target line or `new` line.
- `language`: language layer under `game/tl/`.
- `source`: decoded source text from the generated comment or `old`.
- `target`: decoded current target text from the writable line.
- `speaker`: dialogue say prefix when present; empty for strings.
- `label`: active `translate <language> ...:` label, or `strings`.
- `preserve_tokens`: variables, tags, percent formats, and escape sequences that must survive translation.
- `status`: `empty`, `source_copy`, or `translated`.

The exporter may include extra diagnostic fields such as `source_line`; consumers should ignore unknown fields.

## Preserve Tokens

Treat every `preserve_tokens[*].value` as a contract. Before applying provider output, compare source and translation for:

- Ren'Py interpolation variables such as `[player_name]`, `[score!q]`, and `[name!t]`;
- text tags such as `{i}`, `{/i}`, `{color=#fff}`, `{image=...}`, and hidden tags;
- percent tokens such as `%s`, `%(name)s`, `%02d`, and `%%`;
- escaped sequences such as `\n`, `\"`, `\\`, `\u3000`, and `\N{...}`.

If a provider changes any required token, retry that unit or keep the previous target. Do not silently write a structurally unsafe translation.

## Incremental Flow

1. Prepare templates with Ren'Py official generation or the preparation fallback.
2. Build JSONL units and store them under `localization_work/`.
3. Translate a representative sample from the JSONL, preserving `id` values.
4. Audit provider output against `preserve_tokens`.
5. Apply accepted translations to only the writable target lines.
6. Rebuild units after edits; unchanged source units keep stable `id` values, while changed source text naturally becomes new work.

DeepSeek remains the current bundled bulk backend through `scripts/deepseek_renpy_tl_translate.py`. Prefer the translation-unit JSONL boundary for new provider contracts, resumable state files, review exports, and future Excel/CSV round trips.

## Filtering Rules

The exporter reads only `game/tl/<language>/*.rpy` and emits only targets that Ren'Py expects to be translated:

- dialogue target lines paired with generated source comments;
- `new` values paired with `old` keys in `translate <language> strings:`.

It does not export labels, Python, screen actions, style blocks, paths, images, audio files, fonts, or hidden tag-only strings as translation work. When in doubt, inspect the unit source and its `file:line` before sending it to a provider.
