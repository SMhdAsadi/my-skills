# HTML Walkthrough Companion — Spec

Authoritative spec for the HTML companion that `review-walkthrough` generates next to the markdown walkthrough (`SKILL.md`, Section 4d). Read it fully before generating. Content-shaping rules live in `review-rubric.md`, Section 4.

**What it is:** a scrollable, single-column walkthrough of the same Vertical Slice content as the markdown. It feels like a calm developer tool (GitHub / Linear / Vercel docs), not a marketing page or a cramped wizard. Reading and comprehension come first.

---

## 1. Output Contract

- One self-contained `.html` file: inline CSS and JS, no external requests, no CDN, no remote fonts (~25 KB template size).
- The content is a JSON data block at the top of the file. The template (markup, CSS, JS) is static and is never rewritten per run. The authoring agent writes `review-walkthrough.json` as the single source of truth, and `scripts/build-walkthrough.py` deterministically compiles both `review-walkthrough.md` and `review-walkthrough.html`.
- Language is the language of the user's first prompt, the same as the markdown, and is declared once in the JSON `lang` field. The template sets `<html lang>` and `dir` from it (RTL for `fa`, `ar`, `he`, `ur`, `ps`, `ku`, `yi`, `dv`). All layout uses logical properties, so flipping `dir` works automatically.
- Without JavaScript the template shows a bilingual (English and Persian) `<noscript>` note pointing to the markdown file next to it (same basename, `.md`).
- The template ships as `assets/walkthrough-template.html` with a lean font stack (`local("Vazirmatn")` + system fonts) and an empty `{}` data block. The builder script copies it and replaces only the contents of the JSON block; markup, CSS, JS, and fonts are never touched per run. Both `walkthrough_schema.py` (`validate_walkthrough()`) and the embedded runtime validator `check(d)` enforce the exact same Schema v3 contract and show an error card instead of a half-built walkthrough.

---

## 2. Data Contract (Schema v3)

### Placement and safety
- The data lives in `<script type="application/json" id="walkthrough-data">`.
- When serializing, escape `<` as `\u003c`, and escape U+2028 and U+2029, so author text can never close the script tag.
- The renderer builds the DOM with `textContent`. It never assigns author text to `innerHTML`. The only inline markup allowed inside strings is `` `code` `` and `**bold**`, converted by the renderer. Authors never write raw HTML or bidi control characters.
- If `JSON.parse` or `check(d)` fails, the page shows a single error card in the document language (Persian: «داده‌های راهنما نامعتبر است») listing the first problem. It never renders a half-built walkthrough.

### Top level
```json
{
  "schemaVersion": 3,
  "lang": "fa",
  "meta": {
    "title":        "string, one line: the feature or branch name (page header)",
    "branch":       "branch being reviewed (Latin, verbatim)",
    "base":         "base branch or commit (Latin, verbatim)",
    "headSha":      "short hash of the pinned HEAD",
    "stats":        { "files": 4, "added": 120, "removed": 30 },
    "markdownPath": "optional, absolute path of the markdown walkthrough"
  },
  "repo": {
    "root":          "optional absolute path of the working tree on this machine",
    "defaultEditor": "vscode (default) | cursor | windsurf | zed | android-studio | goland | idea | copy"
  },
  "overview": { ... },
  "slices": [ ... ],
  "crossCutting": { ... }
}
```
Numbers are plain numbers. The renderer formats counts in Persian digits for `fa` and shows diff stats as Latin digits inside one LTR isolate (`<bdi dir="ltr">`).

### `overview` (required)
```
"title":   non-empty string framing the change
"affects": non-empty string listing affected subsystems
"summary": optional array of 0..N non-empty strings (omit on single-slice trivial diffs to avoid duplication)
"split":   optional { "recommendation": non-empty string, "boundaries"?: non-empty string[] }
"skim":    optional array of safe repo-relative paths (renders collapsed by default inside <details>)
```

### `slices` (required, 1..N)
Each `Vertical Slice` object contains:
```
"id":      unique kebab-case slug (^[a-z0-9]+(-[a-z0-9]+)*$), used for #slice-<id> anchors and localStorage keys
"title":   non-empty string (no numeric character cap)
"summary": non-empty array of 1..N prose paragraphs explaining this slice
"files":   non-empty array of 1..N reading items, each:
           { "role":      non-empty short noun phrase,
             "path":      safe repo-relative path (forward slashes, no "./", "/", or ".."),
             "startLine": int >= 1,
             "endLine":   optional int >= startLine,
             "status":    optional "modified" (default) | "added" | "deleted",
             "summary":   non-empty pure prose (never starts with parenthesized path) }
"headsUp": optional array of 0..N items, each:
           { "title":   non-empty string,
             "body":    non-empty pure prose (never starts with parenthesized path),
             "refs":    non-empty array (1..N) of { path, startLine, endLine?, status? },
             "extra":   optional array of non-empty strings,
             "lookFor": optional non-empty string }
"qa":      optional array of 0..N non-empty strings (manual QA Check scenarios)
```
Note:
- The same `path` may appear in multiple slices with distinct `startLine`–`endLine` ranges when it serves distinct workflows.
- Schema v3 has no `category` field on `headsUp` and imposes no numeric caps on `slices`, `files`, `headsUp`, `qa`, or title lengths.

### `crossCutting` (optional, 0..1)
When present, must contain at least one item in `headsUp` or `qa`:
```
"title":   optional non-empty localized section title (defaults to localized "Cross-Cutting")
"headsUp": optional array of 0..N items (same shape as slice headsUp, except "refs" may be empty [])
"qa":      optional array of 0..N non-empty strings
```

### Example (shortened)
```json
{
  "schemaVersion": 3,
  "lang": "fa",
  "meta": {
    "title": "هدر نویسندهٔ ریشهٔ کلاستر در TopBar",
    "branch": "feat/5258-cluster-root-author-header",
    "base": "feat/redesign-post-details-header",
    "headSha": "55c6dcfc9",
    "stats": { "files": 2, "added": 48, "removed": 12 },
    "markdownPath": "/tmp/review-walkthrough.md"
  },
  "repo": { "root": "/Users/me/projects/messenger", "defaultEditor": "vscode" },
  "overview": {
    "title": "انتقال هدر نویسندهٔ کلاستر به TopBar",
    "summary": [
      "این تغییر هدر نویسندهٔ ریشهٔ کلاستر را به TopBar صفحهٔ جزئیات پست می‌آورد و اسلات وسط را حذف می‌کنه."
    ],
    "affects": "TopBar صفحهٔ جزئیات پست و دکمهٔ دنبال‌کردن",
    "skim": ["src/i18n/fa.json"]
  },
  "slices": [
    {
      "id": "follow-button-visibility",
      "title": "شرط نمایش دکمهٔ دنبال‌کردن روی پست شخصی",
      "summary": [
        "والد و فرزند هر دو وضعیت دنبال‌کردن را چک می‌کنند، اما والد پست شخصی را فیلتر نمی‌کنه."
      ],
      "files": [
        {
          "role": "منطق پرچم",
          "path": "src/components/UserActionButton.tsx",
          "startLine": 30,
          "endLine": 80,
          "status": "modified",
          "summary": "شرط نمایش دکمه و رندر Unblock را کنترل می‌کنه."
        },
        {
          "role": "هدر صفحهٔ جزئیات",
          "path": "src/screens/PostDetails/PostDetailsTopBar.tsx",
          "startLine": 32,
          "endLine": 48,
          "status": "modified",
          "summary": "پرچم نمایش دکمه را به کامپوننت فرزند پاس می‌ده."
        }
      ],
      "headsUp": [
        {
          "title": "منطق نمایش دکمهٔ دنبال‌کردن در والد ناقصه",
          "body": "کامپوننت والد فقط چک می‌کنه کاربر دنبال نشده باشه و پست شخصی را در نظر نمی‌گیره. خطا دیده نمی‌شه، چون دکمهٔ فرزند خودش را روی پست شخصی پنهان می‌کنه.",
          "refs": [
            { "path": "src/screens/PostDetails/PostDetailsTopBar.tsx", "startLine": 37, "endLine": 38 },
            { "path": "src/components/UserActionButton.tsx", "startLine": 40, "endLine": 41 }
          ],
          "lookFor": "ببین پرچم والد `!isMyPostModel(root)` و `!isBlocked` را هم در نظر می‌گیره یا نه."
        }
      ],
      "qa": [
        "پست شخصی با `isMyPostModel` درست و کاربر مسدودشده را بررسی کن."
      ]
    }
  ]
}
```

---

## 3. Editor Links & Multi-IDE Support

### Rendering & Reference Pills
- **Dedicated Reference Pills:** References in `Heads Up` items are rendered in a clean row of pills (`.ref-pill`) under the item header. Reading `Files` items render their reference pill directly beside their role inside `.role-row`.
- **Pure Prose Guarantee:** `files[*].summary` and `headsUp[*].body` are 100% natural conversational prose. They never include leading parenthesized path mentions (e.g. no `(Bar.tsx:35): ...`).
- **Display Label:** File links display the file's base name plus lines (`Bar.tsx:35-40`, or `Bar.tsx:35` when there is no `endLine`), with `direction:ltr; unicode-bidi:isolate`. The full `path:lines` text goes in the anchor's `title` and `aria-label`. The `href` always targets the full repo-relative path.
- **Disambiguation:** When two refs across `slices` or `crossCutting` share a base name, the renderer displays the parent directory too (`…/topBar/TopBar.tsx:76`) to keep them immediately distinct.
- **Status Dots:** A small status dot precedes the link for `added` (green, `--add`) and `deleted` (red, `--del`) files; `modified` shows no dot.
- **1-Click Copy Path (`.cp-btn`):** Every reference pill includes a dedicated copy button that copies the repo-relative `path:startLine` (or `path:startLine-endLine`) directly to the clipboard.

### Multi-IDE Header Selector
The top header includes an editor selector dropdown allowing reviewers to choose their active IDE at any time:
- **VS Code** (`vscode`)
- **Cursor** (`cursor`)
- **Windsurf** (`windsurf`)
- **Zed** (`zed`)
- **Android Studio** (`android-studio`)
- **GoLand** (`goland`)
- **JetBrains / IntelliJ** (`idea`)
- **Copy Only** (`copy`)

The selected editor is saved across sessions in `localStorage["rw-editor"]`. Initial default is loaded from `repo.defaultEditor` (or falls back to `vscode`).

### URL Construction (by Editor)
- **VS Code / Cursor / Windsurf:** `{editor}://file/{root}/{path}:{startLine}`
- **Zed:** `zed://file/{root}/{path}:{startLine}`
- **GoLand:** `goland://open?file={root}/{path}&line={startLine}`
- **Android Studio / JetBrains (IntelliJ):** `idea://open?file={root}/{path}&line={startLine}`
- **Copy Only:** No link is rendered; clicking `.cp-btn` copies the relative path to clipboard.
- **Normalization:** Root path backslashes convert to forward slashes; trailing slashes are stripped. Each path segment is percent-encoded via `encodeURIComponent` and rejoined with `/`. Only `startLine` is included in the URL.

### Fallbacks & Staleness
- If `repo.root` is missing or the ref's `status` is `deleted`, the file renders as a non-link `<span>` with a muted label («حذف‌شده» / «Deleted»).
- The top header displays the pinned `headSha` with a tooltip (`shaHint`) reminding the reviewer that line numbers refer to commit `headSha` while editor links open the current working tree. There is no bottom `<footer>`.

---

## 4. Language & Wording (Persian)

### Register (Unified Conversational Voice)
- Both `review-walkthrough.md` and `review-walkthrough.html` use the same **natural conversational Persian developer voice**: everyday spoken verb forms (`می‌کنه`, `ببین`, `چک کن`, `رد می‌شه`), direct peer-to-peer phrasing, no stiff academic filler («در واقع»، «لازم به ذکر است»).
- Keep UI chrome labels concise and consistent with the template's built-in strings (`I.fa`).
- Short sentences, active voice, one idea each. Write original Persian, not literal translations from English. No emoji or exclamation marks in prose.

### Orthography
- Persian letters ی and ک only, never Arabic ي and ك.
- ZWNJ (U+200C) in می‌ and نمی‌, and before ها، ای، تر، ترین، تان، شان («فایل‌ها»، «می‌شه»، «بزرگ‌تر»).
- Persian punctuation: ، ؛ ؟ and «guillemets» for quotes when quoting. No tatweel (ـ).
- Digits: Persian digits (۰۱۲۳۴۵۶۷۸۹) in prose, counts, and slice numbers. Latin digits inside code, paths, line numbers, hashes, and diff stats (`+N / −N`).

### Terms
- Never translate or transliterate identifiers, file names, paths, branch names, flags, or API names. Keep them in Latin script verbatim.
- Keep developer words in Latin script when natural in speech (props, state, hook, provider, flag, diff, commit, render, API, REST, WebRTC).
- Use «برنچ» for branch (never «شاخه»), matching the markdown walkthrough.
- Built-in UI strings (`I.fa`):

| English | Persian |
| :--- | :--- |
| Branch | برنچ |
| Split recommendation | پیشنهاد تفکیک برنچ |
| Overview | خلاصه تغییرات |
| Affects | بخش‌های تحت‌تأثیر |
| Heads up | نکات حساس و ریسک‌ها |
| Check | بررسی کنید |
| Files | فایل‌ها |
| Skim | بررسی گذرا |
| What to test | مواردی که باید تست شوند |
| Cross-cutting | نکات مشترک بین بخش‌ها |
| Slices | بخش‌ها |
| Collapse slice / Expand slice | بستن بخش / باز کردن بخش |
| Theme: System / Light / Dark | پوسته: خودکار / روشن / تیره |
| Open in editor | باز کردن در ویرایشگر |
| Copy path / Copied! | کپی مسیر / کپی شد! |
| Deleted | حذف‌شده |
| Invalid walkthrough data | داده‌های راهنما نامعتبر است |

---

## 5. Font (Vazirmatn & System UI Stack)

The template delivers an ultra-lean footprint (~25 KB total file size) with zero remote CDN dependencies and zero embedded base64 font blobs.

- **Persian (`html:lang(fa)`):** Uses `@font-face` referencing local installations of Vazirmatn (`400` and `600`), with seamless fallback to native Arabic/Persian system fonts (`"Vazirmatn", system-ui, -apple-system, "Segoe UI", Tahoma, sans-serif`).
- **Strict Language Scoping:** The Vazirmatn declaration is scoped strictly to `html:lang(fa)`.
- **English & LTR Languages:** `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`.
- **Code Stack:** `ui-monospace, "SF Mono", Menlo, Consolas, monospace`.

---

## 6. RTL Layout Rules

### Direction
- Logical properties only: `margin-inline`, `padding-inline`, `inset-inline-start`, `border-inline-start`. No hardcoded `left` or `right` in layout rules.
- The collapse chevron rotates direction-aware when collapsed (`-90deg` in LTR, `90deg` in RTL).
- Directional flow in RTL: Any textual progression arrow (`→`, `➔`, `➜`, `->`) outside code spans is automatically normalized to `←` (`U+2190`) when `dir="rtl"`. The branch header arrow renders direction-aware (`←` in RTL, `→` in LTR).

### Bidi (mixed Persian and Latin)
- Every Latin run (identifier, path, flag, branch, hash, version, code) is wrapped by the renderer in `<bdi>` or `<code dir="ltr">` with `unicode-bidi: isolate`, so punctuation never scrambles.
- Diff stats (`+120 / −30`) render as `<bdi dir="ltr">` isolates with Latin digits.

### Typography
- No `text-transform: uppercase` and no `letter-spacing` anywhere (it breaks letter joining). No italics.
- Persian body: `17px` with `line-height: 1.9` (`h1`: `28px`, `h2`: `23px`). Max paragraph width: `70ch`.
- Callout and `Heads Up` borders use `border-inline-start: 3px solid ...`.

---

## 7. Color & Theming

- Default: follow the OS via `prefers-color-scheme`, no flash of the wrong theme (inline script in `<head>` reads `localStorage["rw-theme"]` before first paint). A three-state icon control in the top header (System / Light / Dark) lets the reviewer override and persist in `localStorage["rw-theme"]`.
- Every color is a CSS variable. Light theme follows One Light; dark theme follows One Dark Pro:

| Token | Light (One Light) | Dark (One Dark Pro) | Use |
| :--- | :--- | :--- | :--- |
| `--bg` | `#fafafa` | `#282c34` | page background |
| `--surface` | `#fff` | `#2c313c` | cards and quick-jump pills |
| `--border` | `#e4e4e7` | `#3e4451` | 1px borders and dividers |
| `--text` | `#383a42` | `#dcdfe4` | titles and body |
| `--text-2` | `#696c77` | `#abb2bf` | quick-jump pill text |
| `--text-muted` | `#6e7177` | `#939cb0` | labels, hints, badges |
| `--accent` | `#4078f2` | `#61afef` | links, checkboxes, focus ring |
| `--accent-contrast` | `#fff` | `#282c34` | text selection contrast |
| `--warn` | `#c18401` | `#e5c07b` | `Heads Up` marker/border, split callout border |
| `--code-bg` | `#f0f0f1` | `#21252b` | inline code, tags, badges |
| `--add` | `#50a14f` | `#98c379` | added-lines stats, added dot, copied state |
| `--del` | `#e45649` | `#e06c75` | removed-lines stats, deleted dot |

- No gradients, glows, or box-shadows beyond 1px borders. Focus ring: `2px solid var(--accent)` with `2px` offset.

---

## 8. Layout & Components

- **Single-Column Scrollable Layout:** Centered container (`.wrap`, `max-width: 780px`), **zero `position: sticky` or `position: fixed` elements anywhere**, and **no bottom `<footer>`**.
- **Consolidated Top Header (`.hdr`):** Contains `meta.title`, IDE selector (`.ed-sel`), theme toggle (`.seg`), branch tags (`branch ←/→ base`), diff stats, pinned `headSha` (with staleness tooltip), and `markdownPath` basename. Scrolls off-screen naturally as the reviewer reads.
- **Overview Card (`.card.ov`):** Renders `overview.title`, optional `overview.summary` paragraphs, `affects`, optional `--warn`-bordered `split` callout (plus optional `boundaries` list), and a collapsed-by-default `<details class="skim">` for `overview.skim`.
- **Quick-Jump Strip (`.qj`):** Rendered directly below `Overview` only when `slices.length > 2`; displays clickable `#slice-<id>` anchor pills and scrolls away naturally.
- **Collapsible Vertical Slices (`.card.slice`):** All slices render expanded on load for continuous reading and `Ctrl+F` search.
  - Slice header (`.sl-hdr`): slice number + title, live completion badge (`.sl-prog`, e.g., `2/4` checked files + QA), and manual collapse toggle button (`.sl-tog` with `aria-expanded`).
  - Manual collapse state persists in `localStorage["rw-collapsed:" + headSha]` as an array of collapsed slice IDs. Checking off files or QA items **never** auto-collapses a slice.
  - Inside each slice (`.sl-body`): prose `summary` → `Files` checklist (`localStorage["rw-files:" + headSha]` keyed by `"<sliceId>:<idx>"`) → optional `Heads Up` list (`.hu-item` with `--warn` inline-start border, dot, title, `.ref-row` pills, prose `body`, optional `extra`, optional `lookFor` callout — no `category` label) → optional `QA Check` checklist (`localStorage["rw-qa:" + headSha]` keyed by `"<sliceId>:<idx>"`).
- **Cross-Cutting Card (`.card.cc`):** Rendered at the bottom only when `crossCutting` is present, containing its `Heads Up` items and/or `QA Check` checklist (persisted in `localStorage["rw-qa:" + headSha]` keyed by `"cross-cutting:<idx>"`).
- **Print Stylesheet (`@media print`):** Forces light tokens, hides interactive chrome (`.seg`, `.ed-sel`, `.cp-btn`, `.qj`, `.sl-tog`), and forces all collapsed slice bodies (`.sl-body[hidden]`) and `<details class="skim">` open.

---

## 9. Accessibility

- Visible focus rings (`:focus-visible`), `aria-expanded` and `aria-controls` on slice collapse buttons, `aria-pressed` on theme buttons, semantic `<header>` / `<main>` / `<section>` / `<nav>` landmarks, `lang` and `dir` on `<html>`, and localized `aria-label`s on icon buttons.

---

## 10. Don't

No `position: sticky` or `position: fixed`, no bottom `<footer>`, no `category` badges, no auto-collapse on checkbox toggle, no more than 2 font weights (`400` and `600`), no emoji, no shadows beyond a 1px border, no hardcoded left/right, no uppercase or letter-spacing, no code snippets or diff hunks, no severity labels.

---

## 11. Verification (Deterministic Generator)

- `scripts/build-walkthrough.py` exits 0: the input JSON parses and strictly validates against Schema v3 (`walkthrough_schema.py`), all referenced paths are resolved against `git diff --name-only`, and both `review-walkthrough.md` and `review-walkthrough.html` are compiled cleanly.

---

## 12. Other Languages

The template has built-in UI strings for English (`en`) and Persian (`fa`). Direction, Persian digits (`fa`), and the Vazirmatn font follow `lang`. Other languages fall back to `en` UI labels unless extended in the template (`I` object in `walkthrough-template.html`); built-in keys are `branch`, `split`, `overview`, `affects`, `headsUp`, `check`, `filesSec`, `skim`, `test`, `crossCutting`, `slices`, `collapse`, `expand`, `theme`, `sys`, `light`, `dark`, `open`, `copy`, `copied`, `deleted`, `invalid`, `files`, `file`, and `shaHint`.
