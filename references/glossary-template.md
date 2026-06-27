# Glossary Template

Create this before bulk translation as `localization_work/glossary.md`. Keep it compact but specific enough to constrain the model.

```markdown
# <Game Title> Simplified Chinese Localization Glossary

## Global Style

- Simplified Chinese.
- Natural spoken dialogue; avoid literal English word order.
- Keep visible UI concise.
- Adult content: faithful, direct, natural; do not censor or intensify.
- Preserve `[variables]`, `{tags}`, file paths, labels, screen names, and Python expressions.
- Translate ordinary uppercase emphasis words such as `ME`, `YOU`, `DID`, `THIS`, and `REALLY`.

## Name Policy

- Character names: <English / transliterated / translated>.
- Place names: <English / translated>.
- Relationship titles: <kinship patch or non-kinship mode>.

## Do Not Translate

- Variables:
- Speaker identifiers:
- Text tags:
- Paths and filenames:
- Engine/UI framework names:
- Brands or proper nouns:

## Characters and Address

| English | Chinese / Policy | Notes |
| --- | --- | --- |
| MC / [player_name] | 主角 / [player_name] | Preserve variable. |
| Name | Name | Voice, relationship, title. |

## Locations

| English | Chinese |
| --- | --- |
| Home | 家 |
| School / College / Campus | 学校 / 大学 / 校园 |

## UI and System

| English | Chinese |
| --- | --- |
| Start | 开始 |
| Load | 读取 |
| Save | 保存 |
| Preferences | 设置 |
| Off | 关 |
| < | < |
| > | > |

## Items and Mechanics

| English | Chinese |
| --- | --- |
| Inventory | 物品栏 |
| Relation points | 关系点数 |

## Adult Vocabulary

| English | Chinese Guidance |
| --- | --- |
| fuck | 按语境译为“操/干/做爱”等 |
| cock / dick | 鸡巴 / 阴茎，按语气 |
| blowjob | 口交 / 吹箫，按语气 |
| orgasm / climax | 高潮 |

## Character Voices

- Character A:
- Character B:

## Branching Notes

- If the game has family and non-family patches, record both address styles.
- Record any terms that change by route or state.
```

Update this file after sample translation. The bulk pass should use the final glossary, not a draft with unresolved name policy.
