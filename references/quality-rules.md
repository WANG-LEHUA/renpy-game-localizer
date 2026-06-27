# Chinese Quality Rules

## Contents

1. Syntax preservation
2. Natural Chinese
3. Character voice
4. Adult content
5. Terminology
6. Layout

## 1. Syntax preservation

Preserve exactly:

- `[name]`, `[value!t]`, `[value:.2f]`;
- `{i}`, `{/i}`, `{b}`, `{color=...}`, `{size=...}`, `{w}`, `{p}`;
- speaker identifiers such as `p`, `b`, `narrator`;
- escaped quotes and apostrophes;
- Python, labels, jumps, menu conditions, paths, and image names.

Translate visible text inside interpolation only when Ren'Py marks it translatable. Never translate variable names.

## 2. Natural Chinese

- Prefer short, spoken clauses for dialogue.
- Drop redundant subjects when Chinese naturally permits it.
- Replace literal connective chains with natural pacing.
- Preserve uncertainty when the source is intentionally ambiguous.
- Avoid adding explanatory text that spoils a clue.
- Use Chinese punctuation consistently, while preserving code delimiters.
- Translate ordinary uppercase emphasis words (`ME`, `YOU`, `DID`, `THIS`, `REALLY`) into Chinese emphasis; do not preserve them unless they are confirmed names, acronyms, UI keys, or brands.

Bad:

> 我不能够相信你做出了像这样的一个事情。

Better:

> 真不敢相信你会干出这种事。

## 3. Character voice

Maintain a stable voice sheet:

- formal or casual address;
- favorite insults or pet names;
- confidence, hesitation, education level, and emotional rhythm;
- whether a character speaks clinically, vulgarly, teasingly, or evasively.

Do not make every speaker sound like the same translator.

## 4. Adult content

When full localization is requested:

- translate explicit consensual adult content directly and coherently;
- preserve intensity, power dynamics, humor, discomfort, and character intent;
- keep anatomy vocabulary consistent within the game's tone;
- do not sanitize language into vague euphemisms;
- do not make neutral source text more graphic;
- distinguish dirty talk from narrative description;
- keep intentionally grotesque or surreal terminology understandable.
- preserve visible pure-symbol or short UI strings intentionally: `Off` should not become blank, and `<`, `>`, `...` should remain meaningful controls or punctuation.

If source wording is clumsy, improve the Chinese while preserving the actual action and meaning.

## 5. Terminology

Use one canonical Chinese rendering for each:

- character and place name;
- special substance, ritual, organization, or supernatural entity;
- recurring body-modification term;
- achievement and gallery title;
- relationship title and nickname.

When a term is a deliberate clue, search all chapters before revising it.

## 6. Layout

Chinese usually occupies fewer characters but CJK glyphs are visually denser. Judge layout by rendered lines, not source character count.

Targets:

- ordinary dialogue: preferably 1–3 lines;
- no clipping below the textbox;
- choice text remains readable without overlapping;
- names fit the namebox;
- history entries do not collide;
- chapter titles do not exceed the screen width.

Shorten the translation only when doing so improves prose without losing meaning. Otherwise fix the language-specific style.
