# Detailed Workflow

## Contents

1. Project discovery
2. Translation setup
3. Translation units and sample translation
4. Translation and revision passes
5. LLM machine-translation cost control
6. Layout repair
7. Validation
8. Handoff
9. Agent-orchestrated pipeline

## Agent-orchestrated pipeline

When the user asks to localize a game through this skill, use the skill as the controller for the full workflow. Scripts should do the repeatable work; the agent should read each result and make the next decision. The goal is a guided pipeline, not a blind one-command run.

Recommended control loop:

1. Run `scripts/localization_stage_report.py <project-root> --language <language> --stage preflight --pretty` and summarize project state: source availability, archives, existing `tl` layers, bundled Ren'Py runtime, fonts, chapter count, UI bytecode, and likely language identifier.
2. Decide whether to use `chinese` or a clean layer such as `schinese`. If legacy translation files, archived `tl/<language>` bytecode, mojibake, duplicate labels, or polluted `old` keys are present, prefer a clean layer and document why.
3. Run `scripts/prepare_translation_layer.py` as the preparation gate. Let it detect the bundled Ren'Py command, optionally run official `translate <language>`, add CJK setup, and add expected menu/save/history UI strings. Prefer this over hand-built templates whenever the game runtime can generate translations.
4. If official generation is unavailable or incomplete, decompile/extract archives before translating. Prefer established decompilers such as `unrpyc` for `screens.rpyc`/`gui.rpyc`; use `extract_rpyc_translations.py` as a fallback and verify branch traversal includes `block`, `else_`, `Menu.items[*][2]`, and `If.entries[*][1]`.
5. Compare preparation results with `scan_renpy_project.py`: expected UI keys and discovered compiled-screen UI strings should be covered, `old` keys should remain source text, empty target counts should be intentional template blanks rather than missed extraction, and `translation_mode_recommendation` should be understood before choosing official tl, strings, mixed, or inspection.
6. Build translation units from the prepared language layer. Store the JSONL under `localization_work/` so provider state, review, resume, and apply decisions can reference stable unit ids.
7. Create or update `localization_work/glossary.md` from detected characters, UI terms, recurring locations, and the user's name policy. If the user gives no policy, keep character names conservative and record it.
8. Run a sample translation pass before a full paid run. Inspect a mixed sample and, when possible, a script-heavy sample. Proceed only when placeholders, tags, percent tokens, escape sequences, tone, adult vocabulary, and name policy look acceptable.
9. Audit provider output against the unit `preserve_tokens`, apply only accepted translations, then run the Ren'Py translation audit.
10. Run bulk translation with a resumable state file. DeepSeek Flash remains the current bundled bulk backend; raise concurrency empirically after a successful sample. Prefer `--batch-size 40 --concurrency 128`; go higher only when the previous tier is stable and there are enough pending batches.
11. After apply, run validation gates: audit, font coverage if relevant, compile/lint, and a short launch probe that compares `traceback.txt` before and after launch.
12. Use repair scripts only after a gate identifies a concrete defect. If a repair becomes routine, fold it into `prepare_translation_layer.py` or the audit gate instead of expanding the user-facing workflow.
13. Handoff only after reporting translated scope, preparation method, unit counts, scripts run, audit result, compile/launch result, token usage if available, and remaining visual or image-text risks.

Prefer scripts that emit machine-readable JSON or JSONL stage reports. When a script only prints text, the agent must still extract decision signals: counts, errors, warnings, changed files, provider/model, elapsed time, and retry/failure causes.

Use `scripts/localization_stage_report.py` as the default aggregator for non-paid stages:

```powershell
python <skill>/scripts/localization_stage_report.py <project-root> --language chinese --stage preflight --pretty
python <skill>/scripts/localization_stage_report.py <project-root> --language chinese --stage prepare --apply-prepare --update-existing-ui --pretty
python <skill>/scripts/localization_stage_report.py <project-root> --language chinese --stage validate --font <font-path> --pretty
python <skill>/scripts/localization_stage_report.py <project-root> --language chinese --stage handoff --exe <game-exe> --skip-compile --font <font-path> --pretty
```

The aggregator must not make paid LLM calls. It runs deterministic probes, normalizes their output, and emits `agent_decisions`. The agent reads those decisions and chooses the next action instead of treating the script as an autopilot.

Automation boundary:

- Script discovery, archive detection, language-layer inspection, UI-key coverage checks, CJK font setup, deterministic UI string insertion, structural audit, font coverage, compile/launch probe, and stage JSON summaries.
- Script resumable LLM batching, retry/backoff, state files, usage accounting, and applying accepted translation targets.
- Let the agent decide the active language layer, whether a dirty layer should be rebuilt, whether the sample translation is acceptable, whether to raise or lower concurrency, whether warnings are false positives, whether a compile timeout is benign, and whether visual QA is sufficient.
- Never let a script automatically start a full paid translation, delete legacy translation layers, accept visual layout risk, or hand off completion without agent review.

Useful stage decisions:

- `scan`: choose language layer, archive strategy, runtime generation path, and whether a decompile/extract step is required.
- `prepare`: decide whether official generation succeeded, whether UI/font setup was written, and whether helper repairs should be promoted into the preparation gate.
- `build_units`: confirm target counts, pending counts, source/target pairing, and preserve-token coverage before provider translation.
- `sample_translate`: approve bulk run, adjust glossary/prompt, lower/raise concurrency, or stop for user policy.
- `bulk_translate`: resume, reduce concurrency on 429/timeouts, or proceed to apply when the state file covers the expected units.
- `audit_apply`: verify provider output keeps unit tokens, apply only accepted targets, and keep rejected units pending.
- `renpy_audit`: auto-fix known structural issues, route suspicious English to targeted repair, or inspect false positives.
- `compile_launch`: distinguish compile-time syntax errors from runtime startup errors; always check `traceback.txt` after string-block edits.
- `visual_qa`: fix fonts/styles first, then shorten translations only when the Chinese itself is verbose.

## 1. Project discovery

Start with fast file discovery:

```powershell
rg --files game | rg "\.(rpy|rpa|ttf|otf|ttc)$"
rg -n "^define .*Character|^default |^label |^\s*menu\b" game -g "*.rpy"
```

Identify:

- original chapter and UI scripts;
- `game/tl/<language>` coverage;
- `.rpa` archive contents, especially archived `tl/<language>/*.rpyc`;
- character names and speaker identifiers;
- fonts with Chinese glyph support;
- dialogue, choice, history, notification, and achievement styles;
- unusual interpolation, custom tags, Python blocks, and dynamically generated text.

If translation files do not exist, use Ren'Py's Generate Translations function when the bundled SDK, launcher, or game runtime command is available. Do not fabricate translation labels if Ren'Py can generate stable identifiers.

Run the preparation entrypoint before paid translation:

```powershell
python <skill>/scripts/prepare_translation_layer.py <project-root> --language schinese --pretty
python <skill>/scripts/prepare_translation_layer.py <project-root> --language schinese --generate-official --apply --update-existing-ui --pretty
```

The preparation stage should handle the repeatable front matter: official template generation when possible, CJK font/style setup, menu/save/history UI strings, and a JSON report of next gates. Treat this as the normal path. Use extractor and repair scripts only when this stage reports that official generation is unavailable or incomplete.

When `.rpa` archives contain source bytecode or legacy translations, read [archive-workflow.md](archive-workflow.md). Extract/decompile before translating if needed; for screen/UI bytecode, prefer a proven decompiler path before relying on source-key guesses.

### Compiled script and branch coverage

When source `.rpy` files are incomplete and translations are generated from `.rpyc`, verify the extractor traverses all Ren'Py AST branch containers, not just top-level `Translate.block` nodes.

Required traversal targets:

- ordinary node `block` and `else_` lists;
- `Menu.items[*][2]` blocks;
- `If.entries[*][1]` blocks.

After changing an extractor, compare generated template counts and file-level block counts against the previous run. A large jump often means conditional branch dialogue was previously invisible and would appear in English at runtime. Append or rebuild missing templates in `game/tl/<language>` rather than editing original story scripts.

For `translate <language> strings`, keep every `old` line as the exact source key from the generated template. Only translate `new`. Ren'Py registers string translations globally by language; translated or duplicate `old` keys can crash startup with `A translation for ... already exists`.

### Screen UI coverage

Do not rely only on a fixed list of default Ren'Py menu labels. Tools such as RenpyTranslator reduce menu misses by unpacking archives and decompiling `screens.rpyc`/screen folders before extraction, which exposes project-specific strings such as `Textbox Opacity`, `Quick Menu`, and custom quick-menu/help text.

Use that strategy conservatively:

1. Prefer official `translate <language>` generation or decompiled screen sources when available.
2. Run `scan_renpy_project.py` after preparation and check `missing_discovered_ui_keys`. This gate scans compiled screen payloads for actual `_("<text>")` keys in `screens.rpyc`, `gui.rpyc`, and related UI bytecode.
3. Add missing keys through `add_ui_string_overrides.py` or `--extra`, generating only `translate <language> strings:` blocks.
4. Avoid translating or rewriting whole decompiled `screen` definitions unless a targeted code change is required; direct screen-source translation can cover more UI but has a higher syntax-breakage risk.

## 2. Translation setup

Use `chinese` as the language directory unless the project already expects another identifier or `chinese` is polluted by broken legacy translations.

If `chinese` is polluted by mojibake, archived `.rpyc`, or broken existing files, generate a clean identifier such as `schinese`, add a late `config.language` override, and document the choice.

Create or verify:

```text
game/tl/chinese/
鈹溾攢鈹€ script.rpy
鈹溾攢鈹€ gui.rpy
鈹溾攢鈹€ screens.rpy
鈹斺攢鈹€ scripts/
    鈹溾攢鈹€ chapter1.rpy
    鈹斺攢鈹€ ...
```

Translate character display names in a strings block. Keep internal identifiers unchanged.

Before bulk translation, build `localization_work/glossary.md`. Use [glossary-template.md](glossary-template.md) when drafting it. At minimum include:

- character names;
- kinship and forms of address;
- locations and organizations;
- recurring mechanics and supernatural terms;
- recurring adult/anatomical vocabulary;
- verbal habits unique to each character.

Also record a do-not-translate list for variables, UI framework names, fonts, engine names, key names, and any proper names the user wants to keep in English.

For LLM-assisted translation, read [llm-bulk-translation.md](llm-bulk-translation.md). Do not start with a full-project paid pass. First translate a representative sample of 80-300 entries containing ordinary dialogue, UI, choices, adult content, and terminology-heavy text. Review the sample for:

- whether names should be English, translated, or transliterated;
- whether adult vocabulary matches the requested tone;
- whether recurring setting terms are stable;
- whether placeholders, text tags, percent signs, and escaped quotes survive.

Update the glossary and prompt before bulk translation. The glossary may remain in working notes unless the user asks for it as an artifact, but a reusable project should keep it as a checked-in or workspace artifact.

## 3. Translation units and sample translation

Build units after preparation and before paid or bulk translation:

```powershell
python <skill>/scripts/build_translation_units.py <project-root> --language chinese --output localization_work/translation_units_chinese.jsonl
python <skill>/scripts/build_translation_units.py <project-root> --language chinese --pending-only --output localization_work/translation_units_pending_chinese.jsonl
```

Read [translation-units.md](translation-units.md) before designing provider state, review exports, or apply logic. Unit rows are the stable audit surface: each row points to one writable dialogue target line or one `new` string value, includes the source/target pair, and records `preserve_tokens`.

Use the JSONL file to choose a representative sample before bulk work:

- include dialogue, choices, UI strings, adult content, long lines, and lines with `[variables]`, `{tags}`, percent formats, and escapes;
- keep provider responses keyed by `id`, not by line number alone;
- reject or retry translations whose variables, tags, percent tokens, or escapes differ from the source;
- keep rejected units pending instead of writing unsafe output.

The current DeepSeek backend (`scripts/deepseek_renpy_tl_translate.py`) has its own resumable collector/apply flow. It remains usable for bulk translation, but new provider contracts and review/apply tooling should prefer the translation-unit JSONL boundary.

## 4. Translation and revision passes

### Pass A: structural translation

- Fill all generated dialogue and string blocks.
- Preserve code, tags, variables, and indentation.
- Work by scene or chapter rather than isolated lines.
- Keep menu choices concise enough for buttons.
- Use the approved glossary and do-not-translate list during bulk machine translation.

### Pass B: deterministic cleanup

Before asking an LLM to rewrite translations, run cheap deterministic cleanup where possible:

- normalize known name and terminology variants to the glossary;
- escape literal percent signs as `%%` in Ren'Py strings;
- escape real newline characters as `\n` before writing Ren'Py strings;
- repair obvious punctuation spacing and mojibake;
- skip entries whose source or target is only a hidden Ren'Py tag such as `{#weekday}`;
- fill visible pure-symbol or short UI strings such as `<`, `>`, `Off`, and `...` instead of leaving them blank.

This pass reduces unnecessary paid polishing and makes later audit output easier to interpret.

### Pass C: scene-level prose revision

Read each scene continuously and repair:

- literal English syntax;
- inconsistent pronouns or gender references;
- names transliterated in multiple ways;
- dialogue that does not match the speaker;
- accidental censorship or added explicitness;
- mistranslated jokes, insults, sound effects, or sexual terminology;
- plot clues whose wording must remain consistent across chapters.

When later chapters are much weaker than the first, extract the first chapter's conventions and revise all later chapters against that benchmark.

### Pass D: branch and state review

Search menus, conditions, and persistent flags. Compare translations on both sides of branches so repeated facts and terminology remain consistent.

```powershell
rg -n "^\s*menu\b|events\.append|if .*score|if darkness|if pills" game -g "*.rpy"
```

Prioritize optional scenes because they are commonly skipped by linear proofreading.

## 5. LLM machine-translation cost control

When using paid LLM or machine-translation APIs:

- Disable thinking/reasoning modes for routine translation and polishing unless the provider requires them. Reasoning tokens can greatly increase billed output without improving simple line-by-line localization enough to justify the cost.
- Prefer a cost-effective fast model for bulk initial translation after the glossary is approved.
- Do not default to a premium model for a full-project polishing pass. Full polishing often touches nearly as many entries as initial translation because each translated line must be read and rewritten.
- Use premium models for small style samples, difficult scenes, files that fail audit, plot-critical passages, and representative QA batches.
- Prefer audit-driven polishing when budget matters: prioritize placeholder/tag problems, untranslated English not explained by the glossary, terminology mismatches, very long lines, adult scenes with awkward tone, choices, and chapter titles.
- If doing a full-project light polish, use the cheaper model first and keep a resumable state log so interrupted work does not restart from the beginning.
- Record token usage when possible, separated by model and phase, so the user can compare future workflows.

Recommended order:

1. Project scan and glossary draft.
2. Small sample translation and review.
3. Bulk translation with glossary using a cost-effective model.
4. Deterministic glossary normalization.
5. Audit.
6. Targeted polishing from audit and samples.
7. Optional full light polish with a cost-effective model.
8. Premium-model pass only for selected difficult or important text.

## 6. Layout repair

Prefer language-specific overrides in `game/tl/chinese/gui.rpy`.

Typical pattern:

```renpy
translate chinese style window:
    ysize 260

translate chinese style say_dialogue:
    font "fonts/CJKFont.ttf"
    size 38
    xsize 1260
    line_spacing 2

translate chinese style say_label:
    font "fonts/CJKFont.ttf"
    size 46

translate chinese style choice_button_text:
    font "fonts/CJKFont.ttf"
    size 40
    line_spacing 2
```

Values must be adapted to the game's resolution and textbox geometry.

Fix in this order:

1. use a proper CJK font;
2. reduce Chinese dialogue size moderately;
3. widen the usable dialogue area where safe;
4. increase textbox height;
5. tighten line spacing slightly;
6. shorten an unnaturally verbose translation.

Do not insert manual line breaks throughout the script unless the UI cannot wrap correctly; they are brittle across resolutions.

### Missing-glyph boxes and font coverage

If Chinese text appears but some characters render as square boxes, treat it as a font coverage issue before touching translations. A font with `TC` or `JP` in the name can still miss Simplified Chinese glyphs used by the translated script.

Recommended workflow:

1. Identify the active text fonts in `gui.rpy`, `screens.rpy`, and any localization override such as `game/aa_chinese_defaults.rpy`.
2. Prefer a known Simplified Chinese font bundled with the game. If none exists and the user is on Windows, copying a local CJK font such as `C:\Windows\Fonts\msyh.ttc`, `simhei.ttf`, or `simsun.ttc` into `game/` is usually safer than relying on a Traditional Chinese subset.
3. Override all visible text surfaces, not only dialogue:

```renpy
init -1 python:
    gui.text_font = "msyh.ttc"
    gui.name_text_font = "msyh.ttc"
    gui.button_text_font = "msyh.ttc"
    gui.choice_button_text_font = "msyh.ttc"
    gui.interface_text_font = "msyh.ttc"

init 2 python:
    for style_name in (
        "default", "say_dialogue", "say_label", "input",
        "button_text", "choice_button_text", "label_text",
        "prompt_text", "notify_text", "gui_text",
    ):
        try:
            getattr(style, style_name).font = "msyh.ttc"
        except Exception:
            pass
```

4. Compile the game so `.rpyc` files refresh.
5. Run the font coverage audit against the actual translated text:

```powershell
python <skill>/scripts/audit_font_coverage.py <game-root> --language chinese --font game/msyh.ttc
```

The audit should report `missing=0`. If glyphs are still missing, switch fonts and rerun the audit. Keep large system fonts inside `game/` only when the user accepts the extra size.

## 7. Validation

Run:

```powershell
python scripts/audit_renpy_translation.py <game-root> --language chinese
```

Then manually inspect reported files and search for:

```powershell
rg -n 'new ""|锟絴閳閵唡閿泑棣億脗|脙|芒鈧? game/tl/chinese -g "*.rpy"
rg -n '^\s*(new|[a-zA-Z_][a-zA-Z0-9_]*)\s+".*[A-Za-z]{4}' game/tl/chinese -g "*.rpy"
```

The second search produces false positives for names and variables; review rather than mass-replacing.

Also inspect blank translations whose source has no Latin letters. These are often UI arrows, `Off`, ellipses, or already-Chinese legacy strings. They still need deliberate targets.

If the game bundles Ren'Py, run its lint command or launcher lint. Launch representative scenes when practical.


### Startup and string-key validation

`renpy --compile` or the game executable's `--compile` is necessary but not sufficient: it may not catch duplicate `translate strings` keys that crash during startup. After editing string blocks, also launch the game briefly and check whether `traceback.txt` was updated.

Some packaged Windows executables accept `--compile` but never exit cleanly. When compile times out with no stdout/stderr diagnostics, a clean short launch probe with unchanged `traceback.txt` can be treated as a non-fatal compile timeout; report it explicitly. If the timeout includes stderr/stdout diagnostics such as permission errors or tracebacks, fix or rerun with the required permissions instead of accepting it. Use `renpy_compile_launch_probe.py --strict-compile` when a hard compile pass is required.

Before handoff, verify string keys:

```powershell
python scripts/audit_renpy_translation.py <game-root> --language <language>
```

The audit must report zero errors. In particular, it should catch:

- `old` keys containing CJK text, which usually means source keys were accidentally translated;
- duplicate `old` keys in the same language layer;
- empty `new` targets, placeholder drift, tag drift, and mojibake.

If `old` keys are polluted, rebuild affected `translate <language> strings:` blocks from a clean generated template: preserve template `old` values, keep one global copy of each `old` key, and carry over or regenerate only the `new` translations.

Visual QA sample:

- one ordinary dialogue scene per chapter;
- the longest dialogue found by audit;
- a menu with long choices;
- an adult scene with many short rapid lines;
- history screen;
- save/load and preferences;
- achievements or gallery;
- chapter title and end title.
- scenes containing rare Simplified Chinese characters reported by font coverage checks.

## 8. Handoff

Report:

- translated/revised chapter range;
- UI and font changes;
- validation commands and results;
- remaining untranslated image text or inaccessible archived content;
- whether conflicting legacy translation layers were retained, moved, deleted, or repacked out of archives;
- whether visual launch testing was performed.

Do not claim completion based only on file counts.
