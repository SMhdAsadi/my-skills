---
name: better-persian
description: "Activates automatically whenever generating, translating, localizing, or editing Persian (Farsi) text beyond trivial one-line conversational phrases (e.g. skips 'بله درسته'). Enforces natural human phrasing, register calibration, strict ZWNJ orthography, and eliminates robotic AI clichés silently with zero meta-commentary."
license: MIT
compatibility: "Any agent that reads Markdown skills"
metadata:
  author: SMhd
  version: "1.1.0"
---

# Better Persian

## 0. Output Contract: Silent Execution
Emit ONLY the finalized Persian text. Never output preambles, changelogs, rule summaries, or explanations of edits (e.g. never list what was modified). Apply all rules transparently and silently.

## 1. Register Calibration
Determine register strictly from the deliverable, never from the user's conversational prompt tone. Never mix registers.

* **Formal-Human (رسمی-انسانی):** Proposals, reports, B2B copy, docs. Direct active voice (`است/شد/کرد`). Short sentences. Clarity over ornamentation.
* **Technical & UI (رابط کاربری و فنی):** Buttons, toasts, errors, API docs. Concise imperative/infinitive (`ذخیره تغییرات`, not `تغییرات را ذخیره نمایید`). Direct active notifications, zero polite fluff.
* **Administrative (رسمی-اداری):** Official letters. Standard structure (`جناب آقای/سرکار خانم [نام]`, `با سلام و احترام؛`, one concise request, `با احترام`).
* **Colloquial (محاوره):** Casual chat, social copy (`می‌خوام`, `میشه`). **Heksare rule:** Never write `ـه` instead of ezafe kasre (`کتابِ من`, not `کتابه من`).
* **Academic (علمی):** Research papers, theses. Objective, hedged, zero conversational filler or personal pronouns.

## 2. De-AI-ing (Banned Patterns)
* **Copula & Verb Inflation:** Standardize on `است/شد/کرد`. Ban `می‌باشد`, `گردید`, `به شمار می‌رود`, `محسوب می‌شود`, `به عمل آورد`.
* **Calqued Passives:** Convert passives with `توسط` to active voice (`سرور فایل را ذخیره کرد`, not `فایل توسط سرور ذخیره شد`).
* **Nominal & Prepositional Bloat:** Direct adverbs/prepositions (`خودکار` not `به صورت خودکار`; `با` not `از طریق استفاده از`; `برای` not `به منظور` or `در راستای`).
* **Preamble Fillers:** Delete completely: `لازم به ذکر است که`, `شایان ذکر است که`, `همان‌طور که می‌دانید`, `باید خاطرنشان کرد`.
* **Significance & Clichés:** Cut `در دنیای امروز`, `در عصر حاضر`. Replace `نقش بسزایی دارد` or `از اهمیت ویژه‌ای برخوردار است` with concrete outcomes.
* **Empty Hype:** Ban triplets (`سریع، آسان و مطمئن`) and ungrounded superlatives (`بی‌نظیر`).

## 3. Technical Terms & BiDi
* **Software Terms:** Use standard English or natural transliteration (`وب‌هوک / Webhook`, `کش / Cache`, `PR`). Never use awkward literal calques (e.g. ban `قلاب وب`, `حافظه موقت نهان`, `درخواست کشش`).
* **BiDi Spacing:** Always insulate inline code and Latin terms with spaces (`با متد fetch() فراخوانی...`).

## 4. Orthography & Typography
* **ZWNJ (نیم‌فاصله - U+200C):** Enforce in prefixes (`می‌شود`, `نمی‌دانم`), plurals (`کتاب‌ها`, `فایل‌ها`), comparatives (`بزرگ‌تر`, `سریع‌ترین`), prefixes (`بی‌دقت`, `هم‌زمان`), compounds (`وب‌سایت`, `نرم‌افزار`), and suffixes (`خانه‌ام`, `پروژه‌ی من`).
* **Persian Glyphs:** Strictly use Persian `ی` (`U+06CC`) and `ک` (`U+06A9`) — never Arabic `ي` or `ك`. Standardize ezafe on silent `ه` as `ه‌ی` (`پروژه‌ی جدید`).
* **Numerals & Quotes:** Use Persian numerals (`۰-۹`) for body text, dates, and amounts; keep Latin digits (`0-9`) for code, URLs, and versions. Use Persian guillemets `«...»` (never `"..."`). Attach `،` and `؟` to the preceding word without space, followed by one space.

## 5. Factual Integrity
Never invent metrics, customer counts, or partner names. Use explicit placeholders (e.g. `[تعداد کاربران]`) if data is missing.
