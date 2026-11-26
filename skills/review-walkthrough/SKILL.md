---
name: review-walkthrough
description: "Generates an anti-fatigue review walkthrough for a branch diff (a lean markdown file, plus a scrollable HTML companion with clickable editor links), then stays on standby as an on-demand review co-pilot. Use when the user wants to walk through changes, review a branch, examine a diff, or asks for a guided code review."
license: MIT
compatibility: "git >= 2.0"
metadata:
  author: SMhd
  version: "4.2.0"
  tags:
    - git
    - code-review
    - walkthrough
    - developer-tools
    - html
---

# Review Walkthrough

An **Anti-Fatigue Review Walkthrough Generator and On-Demand Review Co-Pilot** designed to help developers review code better and faster in their native IDE.

Instead of dumping a wall of formal academic text or gating the review behind turn-by-turn chat steps, this skill analyzes the branch diff once, writes a structured JSON document (`review-walkthrough.json`, Schema v3), and executes `scripts/build-walkthrough.py` to deterministically generate both a lean, high-signal Markdown walkthrough and a scrollable, single-column HTML companion (with multi-IDE deep links for VS Code, Cursor, Windsurf, Zed, Android Studio, GoLand, and JetBrains, plus a 1-click Copy Path button). The agent executes diff inspection, vertical slice analysis, JSON authoring, and build execution directly in-context using targeted line reads and progressive graph/grep tooling. The reviewer reads at their own pace in their IDE, and asks the agent questions only when they hit ambiguities, tricky logic, or suspected bugs. Consult [`references/review-rubric.md`](references/review-rubric.md) for vertical slicing heuristics, `Heads Up` formulation, and investigation checklists. Consult [`references/html-walkthrough.md`](references/html-walkthrough.md) for the full JSON Schema v3 and HTML companion specification.

---

## Process

### 1. Pin the Base & Inspect the Diff

1. Determine the base reference (`main`, `master`, `develop`, or a specific branch/commit named by the user).
   - If unspecified, resolve it silently: check for an upstream tracking branch, then fall back to `main`, then `master`, then `develop`, in that order.
   - Only ask the user if none of these resolve to a valid ref. Otherwise state the assumed base in the chat briefing (Section 5) rather than interrupting up front.
2. Record the current HEAD commit: `git rev-parse HEAD`. This is the walkthrough's pinned commit — see Section 6 for staleness handling.
3. Inspect the diff and commit history:
   ```bash
   git rev-parse <base>
   git log <base>..HEAD --oneline
   git diff <base>...HEAD --stat
   ```
4. Check that the diff is non-empty. If empty or invalid, report this immediately.
5. Gauge diff size (files changed, lines changed). This drives the split assessment (Section 2) and the walkthrough's proportional depth (Section 4). Both `.md` and `.html` companions are generated together from the structured JSON data.
6. Read only what the diff warrants. Default to `git diff <base>...HEAD` (plus `--stat`) and at most ~3 targeted file reads for context. Do not open every changed file cover to cover on small diffs.

---

### 2. Split Assessment (Root Cause First)

Large diffs are the primary driver of review fatigue and missed defects. If the diff exceeds the large-diff threshold (rule of thumb: >15 files or >800 changed lines): populate `overview.split` with a one-sentence recommendation that splitting is the superior fix plus concrete split boundaries when visible, then still generate the full walkthrough. For all other diffs, omit `overview.split` entirely — no assessment paragraph, no preamble.

---

### 3. Gather Structural Intelligence (Progressive Tooling)

Remain portable across harnesses while exploiting graph-based code intelligence when present.

- **Small diffs (≤5 files and ≤200 lines):** skip graph tools entirely. `git diff` plus file reads are enough.
- **Tier 1 (Graph-Powered):** only for larger or architecturally unclear diffs, and capped at ~3 calls: use `search_graph` / `trace_path` to map dependency paths and trace inbound callers of changed symbols for a grounded blast radius.
- **Tier 2 (Syntactic Fallback):** If graph tools are unavailable:
  - Degrade gracefully to git commands (`git diff --stat`, `git log`), directory-path heuristics, grep, and file reading.
  - Label any blast-radius or dependency claim as heuristic, or omit it. Never present Tier-2 speculation with Tier-1 confidence.
  - Never crash or fail due to the absence of graph tools.

---

### 4. Generate the Review Walkthrough (JSON-First)

Write the structured review data to `review-walkthrough.json` as the **single source of truth**, then run `scripts/build-walkthrough.py` to deterministically render **both** the Markdown walkthrough and the scrollable HTML companion in milliseconds.

#### 4a. Resolve the Storage Path (Ephemeral, Never Git-Tracked)

The walkthrough deliverables are disposable drafts. They must never be committed and never live in `.git/`. Resolve the target directory using this fallback hierarchy (first match wins):

1. **Repository temp directory (first priority):** a local scratch directory (e.g., `tmp/`, `.tmp/`), after verifying with `git check-ignore` that it is excluded from tracking. This is the preferred home for both deliverables, easily opened in IDE and browser.
2. **Harness artifact directory:** the harness's dedicated artifact/scratch directory (e.g., Antigravity artifact directory).
3. **System temp directory (final fallback):** e.g., `/tmp/review-walkthrough-<branch>-<timestamp>/`.

Write `review-walkthrough.json` into this directory. The generator script outputs `review-walkthrough.md` and `review-walkthrough.html` side-by-side in the same location. Along with `review-walkthrough.json`, initialize `review-concerns.json` in the same directory (pre-populated with walkthrough `Heads Up` items marked `status: "open"`) to track review state across turns and feed Section 7.

#### 4b. Tone & Style Guidelines (Anti-Fatigue)

- **Language Adaptation & Localization:** Always write in the language of the user's first prompt. Detect it once and use it across all fields (`lang: "fa"`, `"en"`, `"de"`, `"es"`).
  - **Full Document Localization:** All section titles, roles, `Heads Up` explanations, and `QA Check` scenarios match the target language.
  - **No Bilingual Tagging:** Write pure native titles. Never append English duplicates in parentheses.
  - **RTL Layout Preservation:** In RTL languages (Persian, Arabic, Hebrew), every line, heading, list item, and metadata label must start with a native RTL word so renderers resolve block direction to RTL.
  - **Pure Human Prose:** `files[*].summary` and `headsUp[*].body` must be 100% natural conversational prose. **Never prepend parenthesized path mentions** (e.g., do NOT start text with `(Bar.tsx:35): ...` or `([Bar.tsx:35](#)): ...`). File references belong exclusively in `files` entries and `headsUp[*].refs`.
  - **Technical Terms & Acronyms in Latin Script:** Code symbols, identifiers, file paths, protocols, and technical acronyms (e.g., WebRTC, REST, API) remain in Latin script verbatim (`backticks` in prose).
- **Unified Conversational Voice:** Use the same natural, everyday spoken developer voice across JSON, Markdown, and HTML (including Persian HTML prose). Write like a sharp colleague sitting right next to the reviewer — punchy, conversational, and direct — while keeping UI chrome labels concise.
- **Qualitative Anti-Fatigue Scaling:** Match depth to the actual diff instead of hitting arbitrary numeric quotas.
  - Omit `overview.summary` on single-slice trivial diffs so the same two sentences are not repeated back-to-back.
  - Omit `headsUp` and `qa` on clean refactors or slices that have no subtle risks or manual test steps — never invent filler warnings or redundant checks.
  - Expand `overview.summary`, `slices`, `headsUp`, and `qa` naturally when a complex change genuinely warrants them; there are no hard numeric item or title-character caps.

#### 4c. Data Contract Cheat-Sheet (Schema v3)

Organize the diff into **Vertical Slices** — cohesive workflow or sub-change units — rather than horizontal technical layers. Each slice pairs its own explanation, ordered reading files, optional `Heads Up` notes, and optional `QA Check` items.

Write `review-walkthrough.json` following Schema v3:

```json
{
  "schemaVersion": 3,
  "lang": "fa",
  "meta": {
    "title": "عنوان کوتاه تغییر",
    "branch": "feat/my-branch",
    "base": "main",
    "headSha": "abc1234",
    "stats": { "files": 4, "added": 85, "removed": 20 }
  },
  "repo": {
    "root": "/path/to/repo/root",
    "defaultEditor": "vscode"
  },
  "overview": {
    "title": "عنوان کلی تغییر",
    "summary": ["یک یا چند پاراگراف خلاصه (در تغییرهای تک‌بخشِ ساده می‌توانی حذفش کنی)."],
    "affects": "بخش‌های تحت‌تأثیر در سیستم",
    "skim": ["README.md", "package-lock.json"]
  },
  "slices": [
    {
      "id": "job-activation-flow",
      "title": "جریان فعال‌سازی جاب و قفل همزمانی",
      "summary": [
        "این بخش منطق فعال‌سازی جاب را از کنترلر به سرویس منتقل می‌کنه و چک همزمانی اضافه می‌کنه."
      ],
      "files": [
        {
          "role": "مدل داده",
          "path": "src/models/job.ts",
          "startLine": 1,
          "endLine": 40,
          "status": "modified",
          "summary": "تعریف فیلدهای جدید وضعیت جاب و تایپ‌های ورودی."
        },
        {
          "role": "سرویس فعال‌سازی",
          "path": "src/services/job.ts",
          "startLine": 35,
          "endLine": 72,
          "status": "modified",
          "summary": "پیاده‌سازی قفل همزمانی و ثبت وضعیت در دیتابیس."
        }
      ],
      "headsUp": [
        {
          "title": "پنجرهٔ رقابت در چک اولیهٔ فعال‌بودن",
          "body": "قفل بعد از خواندن `is_active` گرفته می‌شه. اگه دو درخواست هم‌زمان برسن، هر دو از شرط رد می‌شن قبل از اینکه یکی قفل رو بگیره.",
          "refs": [
            { "path": "src/services/job.ts", "startLine": 42, "endLine": 50, "status": "modified" }
          ],
          "lookFor": "ببین قفل قبل از خواندن `is_active` گرفته می‌شه یا نه."
        }
      ],
      "qa": [
        "دو درخواست هم‌زمان برای یک جاب بفرست و مطمئن شو فقط یکی اجرا می‌شه."
      ]
    }
  ],
  "crossCutting": {
    "title": "نکات مشترک بین بخش‌ها",
    "headsUp": [
      {
        "title": "هماهنگی میگریشن با سرویس‌های قدیمی",
        "body": "ستون جدید مقدار پیش‌فرض نداره؛ اگه سرویس قدیمی هم‌زمان بالا باشه ممکنه insert خطا بده.",
        "refs": []
      }
    ],
    "qa": [
      "کل جریان از ساخت جاب تا نمایش وضعیت نهایی در داشبورد رو تست کن."
    ]
  }
}
```

Key Schema v3 rules:
- `overview`: requires `title` and `affects`. `summary` (`0..N` strings), `split` (`{ recommendation, boundaries? }`), and `skim` (bare repo-relative paths) are optional.
- `slices` (`1..N`): each slice requires a unique kebab-case `id`, `title`, `summary` (`1..N` paragraphs), and `files` (`1..N` reading items). The same file may appear in multiple slices with distinct `startLine`–`endLine` ranges when it serves distinct workflows.
- `slices[*].headsUp` (`0..N`): each item requires `title`, pure prose `body`, and `refs` (`1..N` verifiable `file:line` refs); `extra` and `lookFor` are optional. No `category` field exists.
- `slices[*].qa` (`0..N`): practical manual `QA Check` scenarios for that slice.
- `crossCutting` (`0..1`): optional closing section for multi-slice `headsUp` (where `refs` may be empty) and end-to-end `qa`. When present, it must contain at least one `headsUp` or `qa` item.
- **RTL directional arrows:** In RTL languages (e.g. Persian/Farsi), progression flows strictly right-to-left. Always use leftwards arrow `←` (`U+2190`) in titles and flows (e.g. `مدل داده ← سرویس ← کنترلر`). Never use `→` in RTL flows.

#### 4d. Deterministic Build (`build-walkthrough.py`)

Run the forward generator:

```bash
python3 scripts/build-walkthrough.py <path/to/review-walkthrough.json>
```

The script:
1. Validates the JSON against Schema v3 (`walkthrough_schema.py`).
2. Enriches git metadata and resolves bare basenames against changed files in `git diff --name-only` across `overview.skim`, `slices[*].files`, `slices[*].headsUp[*].refs`, and `crossCutting.headsUp[*].refs`.
3. Deterministically renders `review-walkthrough.md` with localized headings, anchors, and collapsed `<details>` for `Skim List`.
4. Deterministically renders `review-walkthrough.html` (~25 KB, single-column scrollable layout with a non-sticky global header, sticky collapsible section headers, default-collapsed `Vertical Slices`, multi-IDE selector for VS Code, Cursor, Windsurf, Zed, Android Studio, GoLand, JetBrains, 1-click Copy Path, pure prose, and local Vazirmatn font support).
5. Exits 0 and reports both file paths.

---

### 5. Chat Briefing

After running the generator, reply concisely in the walkthrough language:

- The absolute paths to both deliverables (`review-walkthrough.md` and `review-walkthrough.html`).
- A 1-line recap of the branch and diff size.
- The split recommendation, if one was issued.
- A compact list of the `Vertical Slices` (with `Heads Up` counts where present, e.g., `1. <Slice Title> (2 Heads Up)` or localized equivalent).

Then stop. Do not walk through slices in chat, do not pull `Heads Up` prose ahead of the code, and do not ask the user to type `next`.

---

### 6. Passive Standby & Emergent Q&A (Turns 2..N)

The human drives pacing. The agent answers questions and otherwise stays out of the way.

- **Staleness check:** if the user mentions pushing, amending, or rebasing — or a long gap has passed — re-run `git rev-parse HEAD` and compare to the pinned commit. If it changed, flag it and offer to re-diff and regenerate the walkthrough (markdown and HTML together) rather than answering against stale content. Editor links open the working tree, so after a HEAD change their line numbers may no longer match.
- **Concern logging & persistent state:** silently record substantive concerns, todos, and open questions into `<storage-dir>/review-concerns.json` (see `references/review-rubric.md` Section 3b). Keep status updated (`open`, `action-needed`, `resolved`, `accepted-risk`). Never rely on reconstructing findings from chat scrollback. This persistent store feeds Section 7.
- **Answering technical questions** (e.g., *"In the job activation slice, does `processOrder` handle concurrent duplicate requests?"*):
  - **Direct in-context answer & investigation:** Answer directly for simple clarifications, code visible in the diff, or questions already answered by the walkthrough. When deeper investigation is warranted — multi-file execution paths, concurrency/race-condition edge cases, caller blast radius across the codebase, or git-history excavations — investigate directly in-context using targeted line reads (`view_file` ranges rather than reading whole files) and progressive graph/grep tooling (see `references/review-rubric.md` Section 3a).
  - **Neutral Both-Hypotheses Mandate:** Evaluate what protections exist *and* what edge cases could defeat them. Report concrete evidence (`file:line`, caller traces) and state plainly which way the evidence points without bias.
  - Update `review-concerns.json` with the findings and agreed resolution.

---

### 7. Strictly On-Demand Outputs

- **Never** generate an unsolicited sign-off recap, approval summary, or PR comment block.
- Only when the user explicitly asks (e.g., *"Format our findings into a PR review comment"*), read `review-concerns.json`, filter for items marked `action-needed` (and optionally summarize `accepted-risk` items as non-blocking notes), and compile them into a ready-to-post markdown block grouped by file and line anchor.
