# HTML Walkthrough Companion — Spec

Authoritative spec for the HTML companion that `review-walkthrough` generates next to the markdown walkthrough (SKILL.md, Section 4d). Read it fully before generating. Content-shaping rules (what goes into each card) live in `review-rubric.md`, Section 4.

**What it is:** a step-by-step, card-based walkthrough of the same content as the markdown. It should feel like a calm developer tool (GitHub / Linear / Vercel docs), not a marketing page. Reading and comprehension come first. Decoration adds nothing.

---

### 1. Output Contract

- One self-contained `.html` file: inline CSS and JS, no external requests, no CDN, no remote fonts (~24 KB total size).
- The content is a JSON data block at the top of the file. The template (markup, CSS, JS) is static and is never rewritten per run. The authoring agent writes `review-walkthrough.json` as the single source of truth, and `scripts/build-walkthrough.py` deterministically compiles both the Markdown walkthrough and the companion HTML file.
- Language is the language of the user's first prompt, the same as the markdown, and is declared once in the JSON `lang` field. The template sets `<html lang>` and `dir` from it (RTL for fa, ar, he, ur, ps, ku, yi, dv). All layout uses logical properties, so flipping `dir` still works.
- Without JavaScript the template shows a bilingual (English and Persian) `<noscript>` note pointing to the markdown file next to it (same basename, `.md`).
- The template ships as `assets/walkthrough-template.html` with a lean font stack (`local("Vazirmatn")` + system fonts) and an empty `{}` data block. The builder script copies it and replaces only the contents of the JSON block; markup, CSS, JS, and fonts are never touched per run. It validates the data against Schema v2 (Section 2) and shows an error card instead of a half-built walkthrough.

---

## 2. Data Contract (JSON)

### Placement and safety
- The data lives in `<script type="application/json" id="walkthrough-data">`.
- When serializing, escape `<` as `\u003c`, and escape U+2028 and U+2029, so author text can never close the script tag.
- The renderer builds the DOM with `textContent`. It never assigns author text to `innerHTML`. The only inline markup allowed inside strings is `` `code` `` and `**bold**`, converted by the renderer. Authors never write raw HTML or bidi control characters.
- If `JSON.parse` or validation fails, the page shows a single error card in the document language (Persian: «داده‌های راهنما نامعتبر است») listing the first problem. It never renders a half-built walkthrough.
- The skill validates the JSON against Schema v2 before writing the file.

### Top level
```json
{
  "schemaVersion": 2,
  "lang": "fa",                      // BCP-47 code: the language of the user's first prompt
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
    "root":          absolute path of the working tree on this machine (see Section 3).
    "defaultEditor": "vscode" (default) | "cursor" | "windsurf" | "zed" | "idea" | "copy"
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
"title":   one sentence, at most 160 characters, synthesized by the builder
           (never a verbatim copy of the first item — see Section 8)
```
Step numbers, «نکتهٔ ۱ از ۳» counters, and progress are computed by the renderer. Never store them in the JSON.

### `scope` (exactly one, always first)
```
"scopeLabel": optional short label, e.g. «دامنه · جدا کردن لازم نیست»
"gist":       array of 1 to 3 short strings (the Gist sentences)
"affects":    one-line string (the Affects line)
```
`title` states the shape of the diff in one sentence (for example "small, self-contained, safe to read in one pass"). The builder synthesizes it from the diff size (small / medium / large), never by copying the first gist sentence.

### `split` (at most one, directly after `scope`; only when the markdown has a Split Recommendation)
```
"recommendation": string, 1 to 2 sentences
"boundaries":     optional array of strings (suggested split units, in order)
```

### `gotcha` (2 to 4, in markdown order; the template accepts 1 to 4)
```
"category": "edge-case" | "state" | "layout" | "concurrency" | "persistence" | "other"
"body":     full prose (1 to 2 sentences, identifiers in `backticks`); never truncated.
            Never contains a parenthesized file:line mention — refs below carry the links.
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
            "summary":   full summary sentence, never truncated,
            "status":    optional "modified" | "added" | "deleted" }
"skim":  optional array of bare repo-relative paths
```
The reading card's `title` is synthesized as `Read in order: role1 → role2 …`
(or the localized equivalent), never a copy of the first item.

### `test` (exactly one, always last)
```
"items": array of 2 to 3 one-line strings, full text, identifiers and commands in `backticks`
```
The test card's `title` is a generic count-based line (e.g. "Run these 3 checks on a device.",
or the localized equivalent) — never words copied from the items.

### Ordering and limits
- Order: `scope`, `split`?, `gotcha` × 2–4, `reading`, `test`.
- `id` values are unique. Strings contain no raw HTML.
- Persian text follows Section 4. Identifiers, paths, and branch names are never translated.
- Checklist state of the reading step is a viewer convenience only (Section 8); it is never stored in the JSON.

### Example (shortened)
```json
{
  "schemaVersion": 2,
  "lang": "fa",
  "meta": {
    "title": "هدر نویسندهٔ ریشهٔ کلاستر در TopBar",
    "branch": "feat/5258-cluster-root-author-header",
    "base": "feat/redesign-post-details-header",
    "headSha": "55c6dcfc9",
    "stats": { "files": 6, "added": 163, "removed": 62 },
    "markdownPath": "/tmp/review-walkthrough-feat-5258-1791699889.md"
  },
  "repo": { "root": "/Users/me/projects/messenger", "defaultEditor": "vscode" },
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

## 3. Editor Links & Multi-IDE Support

### Rendering & Reference Pills
- **Dedicated Reference Pills:** References in gotchas are rendered in a clean row of pills (`.ref-pill`) under the gotcha title/body. Reading items render their deep links directly beside their role and summary.
- **Pure Prose Guarantee:** Body text and summaries are 100% natural conversational prose. They never include leading parenthesized path mentions (e.g. no `(Bar.tsx:35): ...`). All path references are handled by the structured refs.
- **Display Label:** File links display the file's base name plus lines (`Bar.tsx:35-40`, or `Bar.tsx:35` when there is no `endLine`), with `display:inline-flex; direction:ltr; unicode-bidi:isolate`. The full `path:lines` text goes in the anchor's `title` and `aria-label`. The `href` always targets the full repo-relative path.
- **Disambiguation:** When two refs share a base name, the builder displays the parent directory too (`…/topBar/TopBar.tsx:76`) to keep them immediately distinct.
- **Status Dots:** A small status dot precedes the link for `added` (green) and `deleted` (red) files; `modified` shows no dot.
- **1-Click Copy Path (`.cp-btn`):** Every reference pill includes a dedicated copy button that copies the repo-relative `path:startLine` (or `path:startLine-endLine`) directly to the clipboard, providing an immediate fallback for terminal workflows or editors without URL scheme handlers.

### Multi-IDE Header Selector
The HTML header includes an editor selector dropdown allowing reviewers to choose their active IDE at any time:
- **VS Code** (`vscode`)
- **Cursor** (`cursor`)
- **Windsurf** (`windsurf`)
- **Zed** (`zed`)
- **JetBrains / IntelliJ** (`idea`)
- **Copy Only** (`copy`)

The selected editor is saved across sessions in `localStorage["rw-editor"]`. Initial default is loaded from `repo.defaultEditor` (or falls back to `vscode`).

### URL Construction (by Editor)
- **VS Code / Cursor / Windsurf:**
  `{editor}://file/{root}/{path}:{startLine}`
  Example: `vscode://file/Users/me/app/src/PostDetailsTopBar.tsx:37`
- **Zed:**
  `zed://file/{root}/{path}:{startLine}`
- **JetBrains:**
  `idea://open?file={root}/{path}&line={startLine}`
- **Copy Only:**
  Clicking the link copies the relative path to clipboard and shows copied feedback without opening a URL handler.
- **Normalization:** Root path backslashes convert to forward slashes; trailing slashes are stripped. Each path segment is percent-encoded via `encodeURIComponent` and rejoined with `/`. Only `startLine` is included in the URL (editors cannot navigate to a range).

### Fallbacks & Staleness
- If `repo.root` is missing or the ref's `status` is `deleted`, the file renders as a non-link `<span>` with a muted label («حذف‌شده» / «deleted»).
- The footer shows a reminder that line numbers refer to commit `headSha` and links open the current working tree.

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
| Copy path | رونوشت |
| Copied | کپی شد! |
| Deleted | حذف‌شده |
| Invalid data | داده‌های راهنما نامعتبر است |

- Gotcha categories: `edge-case` = حالت مرزی | `state` = State و re-render | `layout` = چیدمان و استایل | `concurrency` = همزمانی و ترتیب اجرا | `persistence` = ماندگاری و بازنشانی | `other` = سایر.
- Introduce any other recurring term once as «Persian (English)», then use the Persian form consistently.

---

## 5. Font (Vazirmatn & System UI Stack)

The template delivers an ultra-lean footprint (~23.7 KB total file size) with zero remote CDN dependencies and zero embedded base64 font blobs.

- **Persian (`lang="fa"`):** Uses `@font-face` referencing local installations of Vazirmatn, with seamless fallback to native Arabic/Persian system fonts:
  ```css
  @font-face {
    font-family: 'Vazirmatn';
    src: local('Vazirmatn'), local('Vazir');
    font-weight: 400 700;
    font-display: swap;
  }
  :root[lang="fa"] {
    --sans: "Vazirmatn", "SF Arabic", "Segoe UI", system-ui, -apple-system, sans-serif;
  }
  ```
- **Strict Language Scoping:** The Vazirmatn declaration is scoped strictly to `lang="fa"`. Arabic (`ar`) and other languages use their native platform font stacks.
- **English & LTR Languages:** Use modern system UI typography (`system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`).
- **Code Stack:** Monospace fallback stack (`ui-monospace, "SF Mono", Menlo, Consolas, monospace`).

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
- Keyboard: in RTL, ArrowLeft goes to the NEXT step and ArrowRight to the PREVIOUS step (reversed in LTR). Home goes to the first step, End to the last.

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

- Default: follow the OS via `prefers-color-scheme`, no flash of the wrong theme. A three-state icon control in the top corner (System / Light / Dark as monitor / sun / moon icons with tooltips: خودکار / روشن / تیره), with System selected by default. A manual choice overrides the OS and is saved in `localStorage` (wrap reads and writes in try/catch, fall back to System).
- Define light tokens on `:root`. Define dark tokens twice: once in `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {...} }` and once in `:root[data-theme="dark"] {...}`. A tiny inline script in `<head>` sets `data-theme` before first paint. Set `color-scheme` per theme. The System option tracks OS changes without a reload.
- Every color is a CSS variable. No hex values outside the token block.
- Light theme follows One Light; dark theme follows One Dark Pro.

Tokens (names are fixed; values may move ±5% lightness, never hue):

| Token | Light (One Light) | Dark (One Dark Pro) | Use |
| :--- | :--- | :--- | :--- |
| `--bg` | #fafafa | #282c34 | page background |
| `--surface` | #ffffff | #2c313c | the card |
| `--border` | #e4e4e7 | #3e4451 | 1px borders and dividers |
| `--text` | #383a42 | #dcdfe4 | titles and body |
| `--text-2` | #696c77 | #abb2bf | secondary prose |
| `--text-muted` | #6e7177 | #939cb0 | labels, hints |
| `--accent` | #4078f2 | #61afef | buttons, focus, progress, links, checkboxes |
| `--accent-contrast` | #ffffff | #282c34 | text on a solid accent button |
| `--warn` | #c18401 | #e5c07b | gotcha marker dot, split callout border |
| `--code-bg` | #f0f0f1 | #21252b | inline code, branch tags |
| `--add` | #50a14f | #98c379 | added-lines stats |
| `--del` | #e45649 | #e06c75 | removed-lines stats |

- Diff stats render as one LTR isolate: `+N` in `--add`, `−N` in `--del`. Accent is for interactive state only. `--warn` is used only for the gotcha marker and the split callout. Text colors must pass WCAG AA (4.5:1) on `--surface` in BOTH themes.
- No gradients, glows, colored page backgrounds, or neon. No box-shadows beyond 1px borders.
- Focus ring: 2px `--accent` with 2px offset, visible on both surfaces.

---

## 8. Layout & Components

- Single centered column, max-width about 760px. One card = one step.
- ONE level of container: the card. No nested boxes. Separate sections with spacing and thin dividers.
- Callouts (`lookFor`, split recommendation): a 3px inline-start border plus a small bold label, no filled background. `lookFor` uses a muted border; the split callout uses `--warn`.
- The card uses auto height with a small min-height (~180px); the nav buttons sit in a sticky footer area. Nothing jumps between steps.
- Only the `scope` step may be centered. Everything else aligns to the reading start.
- Page header: `meta.title`, then a branch line with each branch as a tag (`from-tag → to-tag`), then a stats line (`N files · +added (green) / −removed (red)`), the IDE selector dropdown, then «گام ۲ از ۷» with the current `section`.
- Gotcha card, top to bottom: quiet category label with a `--warn` dot and counter («نکتهٔ ۱ از ۳ · حالت مرزی»), title, pure human prose body, reference pill row with deep links and 1-click copy buttons, optional `extra`, optional «بررسی کنید» callout.
- Reading step: a native `<input type="checkbox">` list, one item per file (role in weight 600, summary, then the editor link with copy button). Checkbox inputs are unblocked from card key traps so reviewers can toggle them using Space. For lists with >6 files, `.chk-list` enables a clean vertical scroll area. Checked state is saved per `headSha` in `localStorage` (key `review-walkthrough:<headSha>`). The `skim` line follows the list as plain muted text.
- Progress: a thin segmented bar (one segment per step) with a 24px touch target per segment, filling from inline-start. No dot row.
- Buttons: Previous is ghost, Next is solid `--accent`, same height, one SVG chevron each as in Section 6. No `<kbd>` hints — arrow keys still work and are documented in the button tooltip.
- Inline code: monospace with a subtle `--code-bg` tint, no border. Branch names use the same tag style.
- Deep links: `#step-id` selects a step; handle `hashchange`.
- Print: force the light tokens, show all steps in sequence, hide navigation and the theme control.

---

## 9. Motion & Accessibility

- Only a quick fade or slide of 150 ms or less between steps. In RTL the slide moves along the reading direction. Respect `prefers-reduced-motion`. No ambient animation.
- Full keyboard support (Section 6), visible focus rings, `aria-current="step"` on the active segment, `aria-live="polite"` for step changes, semantic headings, `lang` on the root, and localized aria-labels on icon buttons.

---

## 10. Don't

No more than 2 font weights, no emoji, no pill badges except the branch tags and reference pills, no shadows beyond a 1px border, no fixed pixel widths, no hardcoded left/right, no text arrows, no uppercase or letter-spacing, no code snippets or diff hunks, no severity labels.

---

## 11. Verification (Deterministic Generator)

- `scripts/build-walkthrough.py` exits 0: the input JSON parses and strictly validates against Schema v2 (`walkthrough_schema.py`), all referenced paths are resolved against `git diff --name-only`, and both the Markdown walkthrough and the companion HTML file are compiled. This single command serves as the complete verification.

---

## 12. Other Languages

The template has built-in UI strings for English (`en`) and Persian (`fa`). Direction, digits (Persian digits only for `fa`), and the font follow `lang`.

- **Any other language** (German, Spanish, Arabic, ...): set `lang` and provide a complete `ui` object in the JSON. Missing keys fall back to English, so omit none. Translate idiomatically using the headings and labels in the SKILL.md reference table, with no bilingual tagging. Keys: `step, of, scope, branch, split, gist, affects, heads, check, reading, skim, test, text, prev, next, theme, sys, light, dark, open, copy, copied, deleted, invalid, files, foot, nav` and `cat` (an object with `edge-case, state, layout, concurrency, persistence, other`). `foot` must contain `{sha}`, and `heads` is the word before the counter («Heads up 1 of 3»).
- **LTR languages** use a system sans stack, a right-pointing chevron for Next, and ArrowRight advances.
- **Other RTL languages** (Arabic, Hebrew, ...) get Sections 6 to 9 unchanged using their platform system fonts.
- The register rules in Section 4 are Persian-specific; for other languages use a neutral, professional tone.