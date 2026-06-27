# LLM Bulk Translation

Use this reference before paid or rate-limited LLM translation.

## Required Order

1. Build `localization_work/glossary.md`.
2. Run `scripts/prepare_translation_layer.py` so official templates, UI strings, and CJK font/style setup exist before any API call.
3. Run `scripts/scan_renpy_project.py` and confirm there are no preparation-blocking UI/string-key signals.
4. Run a small sample pass of 80-300 entries covering UI, ordinary dialogue, choices, adult scenes, and terminology-heavy text.
5. Review the sample and update the glossary/prompt.
6. Run bulk translation with a resumable state file.
7. Apply translations.
8. Audit, lint/compile, launch probe, and visually sample.

## Prompt Rules

Require structured output, for example:

```json
{"translations":[{"id":"...","text":"..."}]}
```

Prompt requirements:

- Preserve `[variables]`, Ren'Py text tags, interpolation conversions, and escaped line breaks exactly.
- Translate ordinary uppercase emphasis words such as `ME`, `YOU`, `DID`, `THIS`, and `REALLY`; do not preserve them as if they were names.
- Keep glossary-listed names and brands in the chosen form.
- Translate adult content directly and naturally without censoring or intensifying.
- Keep UI and choices short.
- Infer intended English from mojibake apostrophes before translating.

## API Discipline

- Use cost-effective fast models for bulk work.
- Disable thinking/reasoning modes unless the user explicitly asks otherwise.
- Keep concurrency configurable. For providers that support large parallel request counts, high concurrency is expected after the sample pass succeeds; raise it gradually and keep the run resumable.
- Record provider, model, phase, batch count, and token usage when available.
- Write every successful batch to a state file such as `localization_work/deepseek_<language>.jsonl` so interrupted runs resume without paying twice.

The bundled `scripts/deepseek_renpy_tl_translate.py` is an example implementation for DeepSeek-compatible APIs. Adapt model, endpoint, and headers when using another provider.
## DeepSeek Flash High-Concurrency Workflow

Use this path when the user wants fast paid bulk translation with DeepSeek Flash or a DeepSeek-compatible API.

1. Confirm the key without printing it. Look for `DEEPSEEK_API_KEY` in the environment and only report a masked prefix/suffix.
2. Use `https://api.deepseek.com/chat/completions` with `deepseek-v4-flash`, JSON output, and `thinking: {"type":"disabled"}` unless the user asks for reasoning.
3. Run a dry run to count entries and confirm paths before spending API calls.
4. Translate a small mixed sample first: `--limit 200 --batch-size 40 --concurrency 16`.
5. If that sample mostly covers UI/common strings, run a representative script sample too: `--path-filter "scripts/" --limit 200 --batch-size 40 --concurrency 16`.
6. Review the sample for name policy, tone, placeholder preservation, adult vocabulary, and visible UI length. Update the glossary/prompt before the full run.
7. For the full pass, use resumable JSONL state and raise concurrency aggressively but empirically. A practical ladder is `16 -> 64 -> 128 -> 256+`; stop increasing when batches are saturated or 429/timeouts appear.
8. Prefer `--batch-size 40 --concurrency 128` as a proven starting point for a several-thousand-line Ren'Py project. Higher advertised provider limits, such as thousands of concurrent requests, only help when there are enough pending batches and the previous tier is stable.
9. Re-run the same command after any interruption. The state file should prevent paying twice for completed batches.
10. Apply translations only after the state file covers the expected entry count, then audit and compile/lint.

Example commands:

```powershell
python <skill>/scripts/deepseek_renpy_tl_translate.py translate --root <project-root> --language schinese --dry-run
python <skill>/scripts/deepseek_renpy_tl_translate.py translate --root <project-root> --language schinese --limit 200 --batch-size 40 --concurrency 16
python <skill>/scripts/deepseek_renpy_tl_translate.py translate --root <project-root> --language schinese --path-filter "scripts/" --limit 200 --batch-size 40 --concurrency 16
python <skill>/scripts/deepseek_renpy_tl_translate.py translate --root <project-root> --language schinese --batch-size 40 --concurrency 128
python <skill>/scripts/deepseek_renpy_tl_translate.py apply --root <project-root> --language schinese
```

Operational notes:

- Terminal output on Windows can display UTF-8 Chinese as mojibake even when files are correct. Verify actual bytes with Python `encoding="utf-8"` or codepoint/ascii inspection before assuming corruption.
- Record actual provider, model, endpoint, batch count, elapsed time, and token usage in the handoff. Do not hardcode one project's token count as a future estimate.
- After apply, deterministically fill visible pure-symbol or short UI entries that may have been skipped by translation filters, such as `...`, `...!`, `(...)`, `<`, `>`, and `Off`.
- If Ren'Py lint crashes while writing old Windows console/log output, run Ren'Py `compile` as a cleaner syntax validation and still perform the script audit.


## Ren'Py strings safety

For `translate <language> strings`, never send or apply translations to the `old` side. Treat `old` as an immutable source key and `new` as the only writable target. If a cleanup pass scans target lines for English, restrict fixes to dialogue target lines and `new` lines; never rewrite `old`.

If a post-processing script accidentally translates `old` keys:

1. Stop translating further.
2. Rebuild the affected strings blocks from a clean generated template.
3. Globally deduplicate `old` keys across the language layer.
4. Preserve or regenerate Chinese only in `new`.
5. Launch the game briefly and check `traceback.txt`; duplicate `old` keys can pass compile but fail startup.

## Validation Before Apply

For every returned line:

- If variables differ from source, fall back to source or retry.
- If text tag shapes differ from source, fall back to source or retry.
- Escape backslashes, quotes, and actual newline characters before writing `.rpy`.
- Never write raw multiline strings unless the source also uses valid Ren'Py multiline syntax.

After apply, run:

```powershell
python <skill>/scripts/audit_renpy_translation.py <project-root> --language <language>
renpy lint
```

Also scan for empty targets and suspicious leftovers:

```powershell
rg -n 'new ""|^\s*[A-Za-z_][A-Za-z0-9_]*\s+""|^\s*""$' game/tl/<language> -g "*.rpy"
rg -n '^\s*(new|[A-Za-z_][A-Za-z0-9_]*)\s+".*[A-Za-z]{4}' game/tl/<language> -g "*.rpy"
```

Review false positives for names, variables, file paths, key names, and brands.
