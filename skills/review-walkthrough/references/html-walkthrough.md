# HTML Walkthrough Companion — Spec

Authoritative spec for the HTML companion that `review-walkthrough` generates next to the markdown walkthrough (SKILL.md, Section 4d). Read it fully before generating. Content-shaping rules (what goes into each card) live in `review-rubric.md`, Section 4.

**What it is:** a step-by-step, card-based walkthrough of the same content as the markdown. It should feel like a calm developer tool (GitHub / Linear / Vercel docs), not a marketing page. Reading and comprehension come first. Decoration adds nothing.

---

## 1. Output Contract

- One self-contained `.html` file: inline CSS and JS, no external requests, no CDN, no remote fonts.
- The content is a JSON data block at the top of the file. The template (markup, CSS, JS, embedded fonts) is static and is never rewritten per run. `scripts/build-html.py` fills in the JSON from the finished markdown; agents never hand-write it and never open the template in model context.
- Language is the language of the user's first prompt, the same as the markdown, and is declared once in the JSON `lang` field. The template sets `<html lang>` and `dir` from it (RTL for fa, ar, he, ur, ps, ku, yi, dv). All layout uses logical properties, so flipping `dir` still works.
- Without JavaScript the template shows a bilingual (English and Persian) `<noscript>` note pointing to the markdown file next to it (same basename, `.md`).
- The template ships as `assets/walkthrough-template.html` with the Vazirmatn subset already embedded and an empty `{}` data block. The builder script copies it and replaces only the contents of the JSON block; markup, CSS, JS, and fonts are never touched per run. It validates the data (Section 2) and shows an error card instead of a half-built walkthrough. The spec below documents what the template implements and is the reference for changing it.

---

## 2. Data Contract (JSON)

### Placement and safety
- The data lives in `<script type="application/json" id="walkthrough-data">`.
- When serializing, escape `<` as `\u003c`, and escape U+2028 and U+2029, so author text can never close the script tag.
- The renderer builds the DOM with `textContent`. It never assigns author text to `innerHTML`. The only inline markup allowed inside strings is `` `code` `` and `**bold**`, converted by the renderer. Authors never write raw HTML or bidi control characters.
- If `JSON.parse` or validation fails, the page shows a single error card in the document language (Persian: «داده‌های راهنما نامعتبر است») listing the first problem. It never renders a half-built walkthrough.
- The skill validates the JSON against the rules below before writing the file.

### Top level
```
{
  "schemaVersion": 1,
  "lang": "fa",                      // BCP-47 code: the language of the user's first prompt, same as the markdown
  "ui":   optional object of UI strings for languages the template does not include (Section 12)
  "meta": {
    "title":        string, one line: the feature or branch name (page header)
    "branch":       branch being reviewed (Latin, verbatim)
    "base":         base branch or commit (Latin, verbatim)
    "headSha":      short hash of the pinned HEAD
    "stats":        { "files": int, "added": int, "removed": int }
    "markdownPath": optional, absolute path of the markdown walkthrough
  },
  "repo": {
    "root":   absolute path of the working tree on this machine (see Section 3).
              Omit if unknown. Never guess.
    "editor": "vscode" (default) | "vscode-insiders" | "cursor" | "windsurf" | "vscodium"
    "remote": optional, e.g. "wsl+Ubuntu" or "ssh-remote+myhost"
  },
  "steps": [ ...in display order... ]
}
```
Numbers are plain numbers. The renderer converts them to local digits (Persian digits in prose) and shows diff stats as Latin digits inside one LTR isolate.

### Steps (all kinds)
```
"id":      unique kebab-case slug, used for deep links (#step-id)
"kind":    "scope" | "split" | "gotcha" | "reading" | "test"
"section": short label shown beside «گام ۲ از ۷» (no numbers in it)
"title":   one sentence, at most 120 characters
```
Step numbers, «نکتهٔ ۱ از ۳» counters, and progress are computed by the renderer. Never store them in the JSON.

### `scope` (exactly one, always first)
```
"scopeLabel": optional short label, e.g. «دامنه · جدا کردن لازم نیست»
"gist":       array of 1 to 3 short strings (the Gist sentences)
"affects":    one-line string (the Affects line)
```
`title` states the shape of the diff in one sentence (for example "small, self-contained, safe to read in one pass").

### `split` (at most one, directly after `scope`; only when the markdown has a Split Recommendation)
```
"recommendation": string, 1 to 2 sentences
"boundaries":     optional array of strings (suggested split units, in order)
```

### `gotcha` (2 to 4, in markdown order; the template accepts 1 to 4)
```
"category": "edge-case" | "state" | "layout" | "concurrency" | "persistence" | "other"
"body":     1 to 2 sentences, identifiers in `backticks`
"refs":     array, 1 to 3 items (required: the anchoring rule), each:
            { "path": repo-relative, forward slashes, no leading "./" or "/", no "..",
              "startLine": int >= 1,
              "endLine":   optional int >= startLine,
              "status":    optional "modified" (default) | "added" | "deleted" }
"extra":    optional array of at most 1 short paragraph (a real edge case)
"lookFor":  optional, one sentence stating what to verify in the code
```
A gotcha without `body` or without at least one ref is invalid. No severity, fix, snippet, or evidence fields exist on purpose (see `review-rubric.md`, Section 4c).

### `reading` (exactly one)
```
"items": array, in foundation-to-leaf order, each:
         { "role":      short noun phrase,
           "path":      repo-relative path (same rules as refs),
           "startLine": int >= 1,
           "endLine":   optional int >= startLine,
           "summary":   one sentence,
           "status":    optional "modified" | "added" | "deleted" }
"skim":  optional array of bare repo-relative paths
```

### `test` (exactly one, always last)
```
"items": array of 2 to 3 one-line strings, identifiers and commands in `backticks`
```

### Ordering and limits
- Order: `scope`, `split`?, `gotcha` × 2–4, `reading`, `test`.
- `id` values are unique. Strings contain no raw HTML.
- Persian text follows Section 4. Identifiers, paths, and branch names are never translated.
- Checklist state of the reading step is a viewer convenience only (Section 8); it is never stored in the JSON.

### Example (shortened)
```json
{
  "schemaVersion": 1,
  "lang": "fa",
  "meta": {
    "title": "هدر نویسندهٔ ریشهٔ کلاستر در TopBar",
    "branch": "feat/5258-cluster-root-author-header",
    "base": "feat/redesign-post-details-header",
    "headSha": "55c6dcfc9",
    "stats": { "files": 6, "added": 163, "removed": 62 },
    "markdownPath": "/tmp/review-walkthrough-feat-5258-1791699889.md"
  },
  "repo": { "root": "/Users/me/projects/messenger", "editor": "vscode" },
  "steps": [
    {
      "id": "scope", "kind": "scope", "section": "دامنه",
      "title": "تغییر کوچک و یکپارچه است و جداسازی لازم نیست.",
      "scopeLabel": "دامنه · جدا کردن لازم نیست",
      "gist": [
        "این تغییر هدر نویسندهٔ ریشهٔ کلاستر را به TopBar صفحهٔ جزئیات پست می‌آورد.",
        "اسلات وسط حذف شده و اکشن‌های prompt و «بیشتر» به اسلات انتهایی منتقل شده‌اند."
      ],
      "affects": "TopBar صفحهٔ جزئیات پست، اسلات شروع TopBar مشترک و دکمهٔ منوی ردیف."
    },
    {
      "id": "follow-flag", "kind": "gotcha", "section": "پرچم دنبال‌کردن",
      "title": "منطق نمایش دکمهٔ دنبال‌کردن در لایهٔ نادرست قرار دارد.",
      "category": "edge-case",
      "body": "کامپوننت والد فقط بررسی می‌کند که کاربر دنبال نشده باشد و پست شخصی را در نظر نمی‌گیرد. خطا دیده نمی‌شود، چون دکمهٔ فرزند خودش را روی پست شخصی پنهان می‌کند.",
      "refs": [
        { "path": "src/screens/PostDetails/PostDetailsTopBar.tsx", "startLine": 37, "endLine": 38 },
        { "path": "src/components/UserActionButton.tsx", "startLine": 40, "endLine": 41 }
      ],
      "lookFor": "بررسی کنید که پرچم والد `!isMyPostModel(root)` و `!isBlocked` را هم در نظر می‌گیرد."
    },
    {
      "id": "reading-order", "kind": "reading", "section": "ترتیب بررسی",
      "title": "از لایهٔ مشترک شروع کنید و به صفحه برسید.",
      "items": [
        { "role": "منطق پرچم", "path": "src/components/UserActionButton.tsx", "startLine": 30, "endLine": 80, "summary": "شرط نمایش دکمه و رندر Unblock." }
      ],
      "skim": ["src/i18n/fa.json"]
    },
    {
      "id": "what-to-test", "kind": "test", "section": "تست",
      "title": "این سه سناریو را روی دستگاه امتحان کنید.",
      "items": ["پست شخصی با `isMyPostModel` درست.", "کاربر مسدودشده و دنبال‌نشده."]
    }
  ]
}
```

---

## 3. Editor Links (File References)

### Rendering
- Each ref is ONE anchor `<a href="...">` whose visible text is `path:start-end` (or `path:start` when there is no `endLine`), with `display:block; direction:ltr; unicode-bidi:isolate; width:fit-content`, aligned to the reading start.
- A separate small icon button next to it copies the `path:lines` text (aria-label «کپی مسیر», then «کپی شد» for 1.5 s).
- Link style: `--accent` color, underline on hover and focus, standard focus ring. No pill, no box, no emoji. A small "open" SVG icon follows the text.
- `title` and `aria-label` on the anchor: «باز کردن در ویرایشگر».
- Use a plain anchor. No `window.open`, no JS navigation, no `target="_blank"`. It must work from a `file://` page.
- Reading-order items use the same anchor for their `path:startLine-endLine` text.

### URL construction (in the renderer, from `repo.root`, `repo.editor`, `path`)
- Local: `{editor}://file/{root}/{path}:{startLine}`
  Example: `vscode://file/Users/me/app/src/PostDetailsTopBar.tsx:37`
- Remote (only when `repo.remote` is set): `{editor}://vscode-remote/{remote}/{root}/{path}:{startLine}`
- Normalize `root`: backslashes to forward slashes, strip any trailing slash. A Windows drive keeps its form (`vscode://file/C:/Users/me/app/...`). A POSIX root starts with a single slash after `file`, never doubled.
- Percent-encode each path segment with `encodeURIComponent`, then rejoin with `/`. Do not encode the slashes or the drive colon.
- Only `startLine` goes in the URL (the editor cannot open a range). The visible text still shows the full range.
- Schemes: `vscode`, `vscode-insiders`, `cursor`, `windsurf`, `vscodium`. An unknown editor value is a validation error. Paths containing `..` or control characters are a validation error.

### Fallbacks
- If `repo.root` is missing, or the ref's `status` is `deleted`, render the same text as a non-link `<span>` with the copy button, plus a muted label «حذف‌شده» for deleted files.
- The footer always shows one muted line: line numbers refer to commit `headSha`, and links open the current working tree (Persian: «شمارهٔ خط‌ها به کامیت `headSha` اشاره می‌کنند و فایل‌ها از working tree فعلی باز می‌شوند.»), plus the markdown path when `meta.markdownPath` is set.

### Known limits (mention to the user when relevant)
- The first click on a `vscode://` link makes the browser ask for confirmation; the user can allow it permanently.
- If the working tree has moved off the pinned commit, line numbers can drift. The staleness check in SKILL.md Section 6 covers regeneration.

---

## 4. Language & Wording (Persian)

These rules apply to the HTML text. The markdown walkthrough keeps its own spoken voice.

### Register
- Formal but readable (رسمی‌روان): full verb forms, no slang, no colloquial contractions. Write «می‌کند» not «می‌کنه», «بخوانید» not «بخونش».
- Address the reader as «شما» or use impersonal phrasing. Never use «تو».
- Short sentences (about 25 words or fewer), active voice, one idea each. Write original Persian, not literal translations from English. If a sentence reads like a translation, rewrite it.
- No emoji, no exclamation marks, no humor, no filler openings such as «در واقع» or «لازم به ذکر است».

### Orthography
- Persian letters ی and ک only, never Arabic ي and ك.
- ZWNJ (U+200C) in می‌ and نمی‌, and before ها، ای، تر، ترین، تان، شان («فایل‌ها»، «می‌شود»، «بزرگ‌تر»).
- Persian punctuation: ، ؛ ؟ and «guillemets» for quotes. Never straight quotes in Persian text. No tatweel (ـ).
- Digits: Persian digits (۰۱۲۳۴۵۶۷۸۹) in prose, counts, and UI text. Latin digits inside code, paths, line numbers, hashes, and identifiers.

### Terms
- Never translate or transliterate identifiers, file names, paths, branch names, flags, or API names. Keep them in Latin script exactly as in the code.
- Keep these developer words in Latin script: props, state, hook, provider, flag, diff, commit, render. Acronyms (API, REST, WebRTC) stay Latin.
- Use «برنچ» for branch (never «شاخه»), matching the markdown walkthrough.
- Fixed UI strings, with no synonyms:

| English | Persian |
| :--- | :--- |
| Step | گام |
| Scope | دامنه |
| Branch | برنچ |
| Split Recommendation | پیشنهاد تفکیک برنچ |
| The Gist | خلاصه تغییرات |
| Affects | بخش‌های تحت‌تأثیر |
| Heads Up | نکات حساس و ریسک‌ها |
| Gotcha counter | نکتهٔ ۱ از ۳ |
| Check | بررسی کنید |
| Suggested Reading Order | ترتیب پیشنهادی بررسی |
| Skim | بررسی گذرا |
| What to Test | مواردی که باید تست شوند |
| Text version | نسخهٔ متنی |
| Previous / Next | قبلی / بعدی |
| Theme: System / Light / Dark | خودکار / روشن / تیره |
| Open in editor | باز کردن در ویرایشگر |
| Copy path / Copied | کپی مسیر / کپی شد |
| Deleted | حذف‌شده |
| Invalid data | داده‌های راهنما نامعتبر است |

- Gotcha categories: `edge-case` = حالت مرزی | `state` = State و re-render | `layout` = چیدمان و استایل | `concurrency` = همزمانی و ترتیب اجرا | `persistence` = ماندگاری و بازنشانی | `other` = سایر.
- Introduce any other recurring term once as «Persian (English)», then use the Persian form consistently.

---

## 5. Font (Vazirmatn, embedded)

Already embedded in the shipped template (weights 400 and 600, about 70 KB of base64) and applied automatically when `lang` is fa or ar; agents never touch it. This section documents how it was built, for rebuilding the template.

- Embed Vazirmatn as base64 woff2 in `@font-face`, inside the static template. Get it from the npm package `vazirmatn` or its GitHub release.
- Subset with fonttools (`pyftsubset`) to: Basic Latin, U+00A0, U+00AB, U+00BB, U+0600-06FF, U+06F0-06F9, U+FB50-FDFF, U+FE70-FEFF, U+200C-200F, U+2010-2027. Keep layout features `kern, liga, calt, locl, ccmp, init, medi, fina, rlig, mark, mkmk, curs`. Output woff2.
- Only two weights: 400 and 600 (instance the variable font or embed two static files). Target under about 120 KB of base64 in total.
- `font-display: block`. Stack: `"Vazirmatn", Tahoma, system-ui, sans-serif`. Code stack: `ui-monospace, "SF Mono", Menlo, Consolas, monospace`.
- Keep the OFL license notice as a CSS comment next to the `@font-face` rules.
- When rebuilding the template and the font cannot be fetched or subset, do not ship a fallback-font template.

---

## 6. RTL Layout Rules

### Direction
- Logical properties only: `margin-inline`, `padding-inline`, `inset-inline-*`, `border-inline-*`, `text-align: start/end`. No `left`, `right`, `margin-left`, `padding-right`, or `text-align:left` anywhere, except inside LTR code spans.
- Flex and grid rows follow the page direction. Keep DOM order Previous, then Next (in RTL, Previous sits on the right and Next on the left). No `row-reverse` or manual swaps.
- The theme toggle sits at `inset-inline-end` of the top corner.

### Arrows and icons
- Never use text arrows (← →) in labels. Use inline SVG chevrons.
- A chevron follows reading direction: Next points toward inline-end (LEFT in RTL), Previous toward inline-start (RIGHT in RTL). Draw icons for LTR and add `[dir="rtl"] .dir-icon { transform: scaleX(-1); }`.
- The icon sits after the text in Next and before the text in Previous.
- Keyboard: in RTL, ArrowLeft goes to the NEXT step and ArrowRight to the PREVIOUS step (reversed in LTR). Home goes to the first step, End to the last. The `<kbd>` hints must match.

### Bidi (mixed Persian and Latin)
- Every Latin run (identifier, path, flag, branch, hash, version, code) is wrapped by the renderer in `<bdi>` or `<code dir="ltr">` with `unicode-bidi: isolate`, so punctuation never scrambles.
- Authors write code in backticks; the renderer escapes it and converts it. Punctuation (. ، ) :) stays outside the LTR wrapper.
- Diff stats ("+163 / −62") and ranges ("A → B") render as one LTR isolate with Latin digits, never as loose text in the RTL flow.
- File references: see Section 3.

### Typography
- No `text-transform: uppercase` and no `letter-spacing` anywhere (it breaks letter joining). No italics. Labels use weight 600 and the muted color.
- Persian needs more vertical room: body 16–17px with line-height 1.9, titles 24px with line-height 1.5. Scale: 13 / 15 / 17 / 24 / 30 px. Max line length about 70ch.
- Visual cues use inline-start/end: callout borders use `border-inline-start`, and the progress bar fills from the inline-start edge.

---

## 7. Color & Theming

- Default: follow the OS via `prefers-color-scheme`, no flash of the wrong theme. A three-state control in the top corner: System / Light / Dark (خودکار / روشن / تیره), with System selected by default. A manual choice overrides the OS and is saved in `localStorage` (wrap reads and writes in try/catch, fall back to System).
- Define light tokens on `:root`. Define dark tokens twice: once in `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {...} }` and once in `:root[data-theme="dark"] {...}`. A tiny inline script in `<head>` sets `data-theme` before first paint. Set `color-scheme` per theme. The System option tracks OS changes without a reload.
- Every color is a CSS variable. No hex values outside the token block.

Tokens (names are fixed; values may move ±5% lightness, never hue):

| Token | Light | Dark | Use |
| :--- | :--- | :--- | :--- |
| `--bg` | #fafafa | #0b0b0d | page background |
| `--surface` | #ffffff | #141416 | the card |
| `--border` | #e4e4e7 | #27272a | 1px borders and dividers |
| `--text` | #18181b | #fafafa | titles and body |
| `--text-2` | #52525b | #a1a1aa | secondary prose |
| `--text-muted` | #71717a | #8b8b94 | labels, hints |
| `--accent` | #2563eb | #60a5fa | buttons, focus, progress, links, checkboxes |
| `--accent-contrast` | #ffffff | #0b0b0d | text on a solid accent button |
| `--warn` | #b45309 | #fbbf24 | gotcha marker dot, split callout border |
| `--code-bg` | #f4f4f5 | #1c1c1f | inline code |

- Accent is for interactive state only. `--warn` is used only for the gotcha marker and the split callout. Text colors must pass WCAG AA (4.5:1) on `--surface` in BOTH themes.
- No gradients, glows, colored backgrounds, or neon. Dark is neutral near-black, not navy or purple. No box-shadows beyond 1px borders.
- Focus ring: 2px `--accent` with 2px offset, visible on both surfaces.

---

## 8. Layout & Components

- Single centered column, max-width about 760px. One card = one step.
- ONE level of container: the card. No nested boxes. Separate sections with spacing and thin dividers.
- Callouts (`lookFor`, split recommendation): a 3px inline-start border plus a small bold label, no filled background. `lookFor` uses a muted border; the split callout uses `--warn`.
- The card has a fixed min-height; the nav buttons sit in a sticky footer area. Nothing jumps between steps and there is no dead space below.
- Only the `scope` step may be centered. Everything else aligns to the reading start.
- Page header: `meta.title`, then one muted line with `branch → base`, the stats isolate, and «گام ۲ از ۷» with the current `section`.
- Gotcha card, top to bottom: quiet category label with a `--warn` dot and counter («نکتهٔ ۱ از ۳ · حالت مرزی»), title, body, file references, optional `extra`, optional «بررسی کنید» callout.
- Reading step: a native `<input type="checkbox">` list, one item per file (role in weight 600, summary, then the editor link). Checked state is saved per `headSha` in `localStorage` (try/catch, key `review-walkthrough:<headSha>`). The `skim` line follows the list as plain muted text.
- Progress: a thin segmented bar (one segment per step), filling from inline-start. No dot row.
- Buttons: Previous is ghost, Next is solid `--accent`, same height, SVG chevrons as in Section 6, `<kbd>` hints shown.
- Inline code: monospace with a subtle `--code-bg` tint, no border. No pill chips anywhere.
- Deep links: `#step-id` selects a step; handle `hashchange`.
- Print: force the light tokens, show all steps in sequence, hide navigation and the theme control.

---

## 9. Motion & Accessibility

- Only a quick fade or slide of 150 ms or less between steps. In RTL the slide moves along the reading direction. Respect `prefers-reduced-motion`. No ambient animation.
- Full keyboard support (Section 6), visible focus rings, `aria-current="step"` on the active segment, `aria-live="polite"` for step changes, semantic headings, `lang` on the root, and localized aria-labels on icon buttons.

---

## 10. Don't

No more than 2 font weights, no emoji, no pill badges, no shadows beyond a 1px border, no fixed pixel widths, no hardcoded left/right, no text arrows, no uppercase or letter-spacing, no code snippets or diff hunks, no severity labels.

---

## 11. Verification (one check, no browser pass)

- `scripts/build-html.py` exits 0: the JSON parses, step order/counts match the markdown (`scope` first, `test` last, `reading` after the last `gotcha`), and every gotcha carries at least one `file:line` ref. That is the entire verification — there is deliberately no light/dark screenshot pass, no font proof, and no editor-link click-through. Those checks cost minutes on every run and were always skipped in practice.

---

## 12. Other Languages

The template has built-in UI strings for English (`en`) and Persian (`fa`). Direction, digits (Persian digits only for `fa`), and the font follow `lang`.

- **Any other language** (German, Spanish, Arabic, ...): set `lang` and provide a complete `ui` object in the JSON. Missing keys fall back to English, so omit none. Translate idiomatically using the headings and labels in the SKILL.md reference table, with no bilingual tagging. Keys: `step, of, scope, branch, split, gist, affects, heads, check, reading, skim, test, text, prev, next, theme, sys, light, dark, open, copy, copied, deleted, invalid, files, foot, nav` and `cat` (an object with `edge-case, state, layout, concurrency, persistence, other`). `foot` must contain `{sha}`, and `heads` is the word before the counter («Heads up 1 of 3»).
- **LTR languages** use a system sans stack, a right-pointing chevron for Next, and ArrowRight advances.
- **Other RTL languages** (Arabic, Hebrew, ...) get Sections 6 to 9 unchanged. Arabic uses the embedded Vazirmatn; Hebrew and others fall back to the system stack.
- The register rules in Section 4 are Persian-specific; for other languages use a neutral, professional tone.