# Better Persian (`better-persian`)

[![Agent Skills Standard](https://img.shields.io/badge/Agent%20Skills-Standard-0A84FF?style=flat-square&logo=git&logoColor=white)](https://agentskills.io)
[![Vercel Skills CLI](https://img.shields.io/badge/Vercel%20Skills-CLI%20Compatible-000000?style=flat-square&logo=vercel&logoColor=white)](https://github.com/vercel-labs/skills)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](../../LICENSE)

A lightweight, high-signal skill for AI coding agents that enforces natural Persian (Farsi) writing, correct orthography (نیم‌فاصله / ZWNJ), tone-register calibration, UI microcopy standards, and the elimination of robotic AI clichés — silently with zero meta-commentary.

---

## The Problem

When generating Persian text, AI models typically suffer from two distinct failure modes:

1. **The Prose Sounds Machine-Made:** Models default to stiff, bureaucratic government-office phrasing (کتابی), repetitive copula padding (`می‌باشد`, `به شمار می‌رود`), empty announcements (`لازم به ذکر است که`), generic openers (`در دنیای امروز`), and calqued English passives (`توسط`).
2. **The Mechanics Betray the Text:** Missing half-spaces/ZWNJ (`میشود` instead of `می‌شود`, `کتاب ها` instead of `کتاب‌ها`), keyboard contamination from Arabic letters (`ي` and `ك`), English quotes (`"..."`), and broken punctuation spacing.

Most guides attempting to fix this are massive multi-file repositories (~300+ KB) that fill agent context windows and degrade coding performance.

The **`better-persian`** skill (v1.1.0) distills the essential rules into an ultra-compact specification (**~500 tokens**) designed to live in context on non-trivial Persian tasks without degrading reasoning or adding conversational friction.

---

## Installation

### Via Vercel Skills CLI (`npx skills`)

```bash
# Add to your current project
npx skills add SMhdAsadi/my-skills@better-persian

# Or install globally for your user across all projects
npx skills add SMhdAsadi/my-skills@better-persian --global

# Target a specific harness (e.g. Claude Code, Cursor)
npx skills add SMhdAsadi/my-skills@better-persian --agent claude-code
```

### Manual Installation

* **Claude Code:** Copy to `~/.claude/skills/better-persian/SKILL.md`
* **Antigravity / Gemini CLI:** Copy to `~/.gemini/config/skills/better-persian/SKILL.md`
* **Universal Agents (OpenCode, Codex, Cursor):** Copy to `.agents/skills/better-persian/SKILL.md` or reference in your project's `AGENTS.md`.

---

## Design Principles & Output Contract

### Silent Execution (Zero Meta-Commentary)
AI agents often clutter responses with post-hoc summaries of what they edited or why. `better-persian` binds the agent to emit **only** the finished Persian deliverable. No preambles, no edit changelogs, no lists of applied orthography rules.

### Automatic Activation with Trivial-Response Filtering
Activates automatically when writing, editing, localizing, or translating non-trivial Persian text, while intentionally bypassing short conversational turns (e.g. *«بله درسته»*, *«آیا می‌خواهید ادامه دهید؟»*).

---

## What It Enforces

### 1. Register Matching
Classifies text by the deliverable rather than the prompt's conversational tone:
* **Formal-but-human (رسمی-انسانی):** Direct, active, modern professional tone (`است/شد/کرد` instead of `می‌باشد`).
* **Technical & UI Microcopy (رابط کاربری و مستندات فنی):** Concise, imperative button and toast labels, direct active voice without polite fluff.
* **Administrative (رسمی-اداری):** Standard conventions for formal administrative letters.
* **Colloquial (محاوره):** Natural spoken rhythms while strictly avoiding the common *he-kasre* error (`ـه` vs. `ِ`).
* **Academic (علمی):** Measured, objective, and hedged research prose.

### 2. De-AI-ing (Eliminating Robot Tells)
* Bans copula inflation: `می‌باشد`, `گردید`, `به شمار می‌رود` $\rightarrow$ `است`, `شد`.
* Cuts ceremonial filler: `لازم به ذکر است`, `شایان ذکر است`, `باید خاطرنشان کرد`.
* Strips significance inflation: `نقش بسزایی دارد`, `از اهمیت ویژه‌ای برخوردار است`.
* Eliminates cliché openers: `در دنیای امروز`, `در عصر حاضر`.
* Fixes «در راستای» abuse: Replaced with `برای` or active action verbs.
* Eliminates calqued passives: `توسط سرور اجرا شد` $\rightarrow$ `سرور آن را اجرا کرد`.
* Strips nominal fillers: `به صورت خودکار` $\rightarrow$ `خودکار`.

### 3. Technical Terminology & BiDi
* Rejects awkward literal translations of standard tech terms (prefers `وب‌هوک / Webhook`, `کش / Cache`).
* Enforces single-space insulation before and after English words and inline code in RTL markdown.

### 4. Orthography & Typography
* **Zero-Width Non-Joiner (ZWNJ / نیم‌فاصله):** Enforced across verb prefixes (`می‌ـ`), plural markers (`ـ‌ها`), comparatives (`ـ‌تر/ـ‌ترین`), compound nouns (`نرم‌افزار`), and clitics.
* **Persian Glyphs:** Strictly uses Persian `ی` and `ک` (rejects Arabic `ي` and `ك`). Standardizes on `ه‌ی` for ezafe on silent `ه`.
* **Punctuation & Quotes:** Persian guillemets (`«...»`), Persian question marks (`؟`), and commas (`،`) with standard typographical spacing.

---

## Examples

| Before (Generic AI Output) | After (With `better-persian` Skill) |
| :--- | :--- |
| این سرویس نقش بسزایی در ارتقای امنیت ایفا نموده و از قابلیت‌های منحصر‌به‌فردی برخوردار می‌باشد. | این سرویس امنیت سیستم را افزایش می‌دهد و قابلیت‌های متعددی دارد. |
| لازم به ذکر است که پشتیبانی به صورت ۲۴ ساعته ارائه می‌گردد. | پشتیبانی ۲۴ ساعته است. |
| فایل درخواستی توسط وب‌سرور دانلود گردید. | وب‌سرور فایل درخواستی را دانلود کرد. |
| لطفاً جهت ذخیره‌سازی داده‌ها بر روی دکمه زیر کلیک نمایید. | ذخیره تغییرات |
| در دنیای امروز، بهینه‌سازی وب سایت ها از اهمیت ویژه‌ای برخوردار است. | اگر وب‌سایت شما سریع باز نشود، کاربران آن را ترک می‌کنند؛ بهینه‌سازی یعنی همین. |

---

## License

Licensed under the [MIT License](../../LICENSE).
