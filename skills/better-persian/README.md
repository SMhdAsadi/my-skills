# Better Persian (`better-persian`)

[![Agent Skills Standard](https://img.shields.io/badge/Agent%20Skills-Standard-0A84FF?style=flat-square&logo=git&logoColor=white)](https://agentskills.io)
[![Vercel Skills CLI](https://img.shields.io/badge/Vercel%20Skills-CLI%20Compatible-000000?style=flat-square&logo=vercel&logoColor=white)](https://github.com/vercel-labs/skills)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](../../LICENSE)

A lightweight, high-signal skill for AI coding agents that makes Persian (Farsi) output sound like a person typed it: conversational by default, correct on نیم‌فاصله (ZWNJ), and free of robotic AI phrasing — silently, with zero meta-commentary.

---

## The Problem

When generating Persian, models fail in three separate ways:

1. **It sounds like a memo.** Chat replies arrive in written Persian: `می‌باشد`, `شما`, `لازم به ذکر است`, `در نتیجه`, closing offers, and a tidy three-point structure for a two-sentence answer. Grammatically fine, socially wrong.
2. **It sounds machine-made.** Copula padding, calqued English passives (`توسط`), bureaucratic prepositions (`در خصوص`, `در راستای`), significance inflation (`نقش بسزایی دارد`), and sycophantic openers (`سوال خوبیه!`).
3. **The mechanics betray it.** Random half-spaces (`میشود`, `کتاب ها`), Arabic keyboard contamination (`ي`, `ك`), and inconsistent forms — `میشه` in one sentence and `می‌شود` in the next.

Most guides that try to fix this are multi-file repositories (~300+ KB) that flood the context window. This skill distills the rules into a compact spec (**~1.3k tokens**, measured) that can live in context on every non-trivial Persian task.

**v2.0.0 changed the default.** Earlier versions treated every deliverable as a formal document and produced exactly the memo voice described above. Conversation is now the default; formal Persian is opt-in.

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

## Design Principles

### Conversation Is the Default
Register is chosen by request, not guessed from the deliverable. Unless the user asks for formal text — or names a formal destination like an office email, a proposal, a paper, or a UI string — the skill writes the way the user talks: `تو`, contractions, short sentences.

### Silent Execution
The agent emits only the finished Persian text. No preambles, no edit changelogs, no rule summaries — unless asked.

### Light Touch
The skill fixes what is wrong and leaves the rest alone. A reply that already sounds human is not restyled, shortened, or "improved".

### Word-Level ZWNJ
A blanket "always put a half-space after می" rule produces `می‌شه`, which nobody types. v2.0.0 keeps the default but carves out a closed list of exceptions that are written joined: `میشه`, `میگم`, `میدم`, `میره`, `میاد`. Half-spaces are non-negotiable everywhere else: plurals, comparatives, compounds, and `بی‌/هم‌`.

### Mirror the User's Vocabulary
The skill follows the user's own word bank. Someone who says `کامیت` gets `کامیت`; someone who says `commit` gets `commit`. Absent a signal, infrastructure concepts stay English (`cache`, `deploy`, `PR`) and everyday nouns stay Persian (`فایل`, `خطا`, `سرور`). No parenthetical glosses: `کش (Cache)` is itself a tell.

---

## What It Enforces

### Conversation (default)
* `تو`, short sentences, natural contractions.
* One form per reply — never `میشه` and `می‌شود` in the same answer.
* No sycophantic openers, no closing offers, no connector chains.
* Emoji only mirrored from the user.

### Formal (on request)
* Written Persian, active voice, `است/شد/کرد`.
* `هٔ` for ezafe, `←` for RTL flow, imperative UI strings.
* Standard structure for letters, objective hedging for papers.

### Both
* Copula inflation, ceremonial filler, bureaucratic prepositions, significance inflation, calqued passives, and empty hype are banned.
* Persian `ی`/`ک`, `«...»`, and correct comma/question-mark spacing.
* No invented metrics or customers.

---

## Examples

| Before (typical AI output) | After (with `better-persian`) |
| :--- | :--- |
| لازم به ذکر است که این تغییر ممکن است باعث بروز خطا در سرویس شود. | این تغییر ممکنه سرویس رو خراب کنه. |
| می‌شه یه نگاه به لاگ‌ها بندازی؟ | میشه یه نگاه به لاگ‌ها بندازی؟ |
| نتیجه‌ها را در کش (Cache) نگه دار. | نتیجه‌ها رو توی cache نگه دار. |
| سوال خوبیه! حتماً کمکت می‌کنم. | آره، اون فایل رو باید قبل از build پاک کنی. |
| همچنین لازم است تست‌ها را اجرا کنید. علاوه بر این، مستندات را به‌روزرسانی نمایید. | تست‌ها رو هم اجرا کن، مستندات رو هم آپدیت کن. |
| فایل درخواستی توسط سرور دانلود گردید. | سرور فایل رو دانلود کرد. |
| مشکل چی‌ست؟ | مشکل چیه؟ |

More pairs, including a formal contrast, live in [`references/examples.md`](references/examples.md).

---

## License

Licensed under the [MIT License](../../LICENSE).
