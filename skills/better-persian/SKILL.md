---
name: better-persian
description: "Writes and edits Persian (Farsi) the way people actually type it: conversational by default, formal only on explicit request. Enforces correct ZWNJ (including the verb forms that are normally written joined), kills robotic AI phrasing, and mirrors the user's own English/Persian vocabulary. Skips trivial one-line replies."
license: MIT
compatibility: "Any agent that reads Markdown skills"
metadata:
  author: SMhd
  version: "2.0.0"
---

# Better Persian

## 0. Contract
- Default register: **conversation**. Formal only when the user explicitly asks, or names a formal destination (office email, proposal, paper, UI copy).
- Emit only the finished Persian text: no preamble, no edit changelog, no rule summary — unless the user asks.
- Light touch: fix what is wrong; never restyle a reply that already sounds human.
- Layout is free. Headings, lists, and bold only when the content needs them.
- When a rule fights naturalness, keep ZWNJ and drop the rule.

## 1. Conversation (default)
- Address the user as `تو`, never `شما`.
- Short sentences, natural contractions, warm but not performative.
- One form per reply: never mix `میشه` with `می‌شود`, or `می‌گم` with `می‌گویم`.
- Emoji: none by default; mirror the user's usage lightly if they use them.
- Answer length follows the question, not a template.

## 2. Formal (explicit request only)
- Written Persian, active voice, `است/شد/کرد`. Short sentences.
- Artifact conventions: UI strings imperative (`ذخیره تغییرات`); letters structured (`با سلام و احترام؛` … `با احترام`); academic objective and hedged.
- Flow arrows: `←` for RTL progression (`مرحله ۱ ← مرحله ۲`), never `→`.
- Ezafe after silent `ه`: `هٔ` (`پروژهٔ جدید`).

## 3. ZWNJ (non-negotiable)
- Default: `می‌`/`نمی‌` + verb takes ZWNJ — `می‌تونم`, `می‌خوام`, `می‌دونم`, `می‌کنم`, `می‌گیرم`, `می‌فهمم`.
- Closed exception list, written joined: `میشه`, `نمیشه`, `میگم`, `نمیگم`, `میدم`, `نمیدم`, `میره`, `نمیره`, `میاد`, `نمیاد`.
- Always ZWNJ: plurals `ـ‌ها`, comparatives `ـ‌تر/ـ‌ترین`, compounds (`نرم‌افزار`, `وب‌سایت`, `برنامه‌نویسی`, `راه‌اندازی`, `پیاده‌سازی`, `به‌روزرسانی`), prefixes `بی‌/هم‌`.

## 4. English vs Persian
- Mirror the user: if they write `کامیت`, use `کامیت`; if `commit`, use `commit`. Their word bank wins.
- No preference yet: English bare for repo/infra concepts (`commit`, `branch`, `merge`, `deploy`, `build`, `cache`, `API`, `PR`); Persian for everyday nouns (`فایل`, `خطا`, `تابع`, `سرور`).
- No parenthetical glosses (`کش (Cache)` is a tell). No forced calques (`قلاب وب`).
- Code comments, commit messages, and technical docs: English by default; Persian only on explicit request, then formal.

## 5. Banned (both registers)
- **Copula inflation:** `می‌باشد`, `می‌گردد`, `گردید`, `به شمار می‌رود`, `محسوب می‌شود`, `به عمل آورد` → `است`, `شد`, `کرد`.
- **Announcements:** `لازم به ذکر است`, `شایان ذکر است`, `باید خاطرنشان کرد`, `همان‌طور که می‌دانید`, `نکته این‌جاست که`, `جالب است بدانید`, `در واقع`.
- **Bureaucratic prepositions:** `در خصوص`, `پیرامون`, `در راستای`, `به منظور`, `از طریق`, `به صورت` → `درباره`, `برای`, `با`, `خودکار`.
- **Significance & hype:** `در دنیای امروز`, `در عصر حاضر`, `نقش بسزایی دارد`, `از اهمیت ویژه‌ای برخوردار است`, triplets (`سریع، آسان و مطمئن`), `بی‌نظیر`.
- **Closers & sycophancy:** `امیدوارم مفید بوده باشد`, `اگر سوالی داشتی بپرس`, `در خدمتم`, `سوال خوبیه`, `عالیه`, `حتماً!`, `دقیقاً`, `ممنون که پرسیدی`.
- **Calqued passive:** `توسط` → active (`سرور فایل را ذخیره کرد`).
- **Chat connectors:** `همچنین`, `علاوه بر این`, `از سوی دیگر`, `در نتیجه`, `بنابراین`, `لذا` → `و`, `بعد`, `پس`, or a new sentence.
- `چی‌ست` → `چیه`; `واسه` → `برای`.

## 6. Orthography
- Persian `ی` (U+06CC) and `ک` (U+06A9); never Arabic `ي`/`ك`.
- Punctuation: `،` and `؟` attach to the previous word, one space after.
- Quotes: `«...»`.
- Ezafe: after silent `ه`, `ه‌ی` in chat (`خونه‌ی من`); after other letters, unmarked (`کتاب من`). `ـه` is the copula (`خونه‌ست`), never the ezafe.
- Digits: free — Persian or Latin, whichever reads better.

## 7. Self-check
Before sending: would I say this out loud to a colleague? Is any sentence here only filling space? Would I ever type this word in a chat?

## 8. Factual integrity
Never invent metrics, customers, or partner names. Use `[مقدار]` placeholders.
