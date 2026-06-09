---
name: polish-light-novel
description: Deep-polish the Chinese translation of the light novel 谁が勇者を殺したか / 是谁杀死了勇者. Use when revising chapters for natural Chinese prose, character voice consistency, dialogue punctuation, bilingual output, or translation QA in this project.
disable-model-invocation: true
---

# Polish Light Novel

## Scope

Use this skill for `output_cn/translated/chapter_*_cn.md` and generated bilingual files in `output_cn/bilingual/`.

Preserve plot facts, paragraph order, chapter titles, translator disclaimers, source URLs, and established terms from `notes/glossary.md`, `notes/character_names.md`, `notes/style_guide.md`, and `notes/translation_rules.md`.

## Chinese prose

- Rewrite stiff literal translation into natural Chinese light-novel prose.
- Split or reorder Japanese long sentences when needed, but do not add new facts or remove foreshadowing.
- Keep narration restrained, clear, and suspenseful. Do not over-explain jokes, secrets, or later revelations.
- Fix obvious pronoun, subject, tense, repetition, and semantic break errors.
- Keep HTML spacer blocks and chapter disclaimer structure intact.

## Dialogue

- Direct speech in Chinese uses Chinese curved quotation marks: `“……”`.
- Do not use Japanese brackets `「」` / `『』` or ASCII quotes for Chinese dialogue.
- Interview questions beginning with `——` may remain unquoted.
- Inner thoughts may use Chinese parentheses `（……）` when already presented that way.
- For quoted speech inside dialogue, prefer single Chinese quotation marks `‘……’`.
- Repair missing dialogue quotes only when the line is clearly direct speech.

## Character voices

- 亚雷斯：冷静、早熟、判断利落；情绪压住，不夸张。
- 扎克：温和、谦逊、坚韧；即使痛苦也不卖惨。
- 阿蕾克西亚：聪慧率直，有王族自觉；第一人称用“我”。
- 雷昂：直率、自信、豪爽，偶尔高傲但正直。
- 玛丽亚：表面温柔，带恶作剧和轻微毒舌；“试炼”保留玩笑感。
- 索隆：刻薄、暴躁、别扭；关心藏在冲话里。
- 希拉：温柔克制，悲伤不外放。
- 王妃/巫女：冷淡疲惫，带自责。

## Bilingual output

After Chinese chapters are polished, regenerate bilingual chapters from Japanese source and polished Chinese paragraphs.

Format each pair as:

```markdown
日文段落
中文段落


下一段日文
下一段中文
```

Do not include `**原文：**` or `**译文：**`. Do not insert blank lines between the Japanese paragraph and its Chinese paragraph. Keep visible spacing only between paragraph pairs.
