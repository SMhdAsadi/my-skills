---
name: review-walkthrough
description: "Generates an anti-fatigue review walkthrough for a branch diff (a lean markdown file, plus a card-based HTML companion with clickable editor links), then stays on standby as an on-demand review co-pilot. Use when the user wants to walk through changes, review a branch, examine a diff, or asks for a guided code review."
license: MIT
compatibility: "git >= 2.0"
metadata:
  author: SMhd
  version: "3.3.0"
  tags:
    - git
    - code-review
    - walkthrough
    - developer-tools
    - html
---

# Review Walkthrough

An **Anti-Fatigue Review Walkthrough Generator and On-Demand Review Co-Pilot** designed to help developers review code better and faster in their native IDE.

Instead of dumping a wall of formal academic text or gating the review behind turn-by-turn chat steps, this skill analyzes the branch diff once, writes a structured JSON document (`review-walkthrough.json`), and executes `scripts/build-walkthrough.py` to deterministically generate both a lean, high-signal Markdown walkthrough and an interactive card-based HTML companion (with multi-IDE deep links for VS Code, Cursor, Windsurf, Zed, Android Studio, GoLand, and JetBrains, plus a 1-click Copy Path button). The reviewer reads at their own pace in their IDE, and asks the agent questions only when they hit ambiguities, tricky logic, or suspected bugs. Consult [`references/review-rubric.md`](references/review-rubric.md) for layering heuristics, risk-hypothesis formulas, and investigation templates. Consult [`references/html-walkthrough.md`](references/html-walkthrough.md) for the full JSON Schema v2 and HTML companion specification.

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
5. Gauge diff size (files changed, lines changed). This drives the split assessment (Section 2) and the walkthrough's scale (Section 4). Both `.md` and `.html` companions are generated together from the structured JSON data.
6. Read only what the diff warrants. Default to `git diff <base>...HEAD` (plus `--stat`) and at most ~3 targeted file reads for context. Do not open every changed file cover to cover on small diffs.

---

### 2. Split Assessment (Root Cause First)

Large diffs are the primary driver of review fatigue and missed defects. If the diff exceeds the large-diff threshold (rule of thumb: >15 files or >800 changed lines): state in one sentence that splitting is the superior fix plus one concrete split boundary when visible, then still generate the full walkthrough. For all other diffs, omit this section entirely — no assessment paragraph, no preamble.

---

### 3. Gather Structural Intelligence (Progressive Tooling)

Remain portable across harnesses while exploiting graph-based code intelligence when present.

- **Small diffs (≤5 files and ≤200 lines):** skip graph tools entirely. `git diff` plus file reads are enough.
- **Tier 1 (Graph-Powered):** only for larger or architecturally unclear diffs, and capped at ~3 calls: use `search_graph` / `trace_path` to map dependency layers and trace inbound callers of changed symbols for a grounded blast radius.
- **Tier 2 (Syntactic Fallback):** If graph tools are unavailable:
  - Degrade gracefully to git commands (`git diff --stat`, `git log`), directory-path heuristics, grep, and file reading.
  - Label any blast-radius or dependency claim as heuristic, or omit it. Never present Tier-2 speculation with Tier-1 confidence.
  - Never crash or fail due to the absence of graph tools.

---

### 4. Generate the Review Walkthrough (JSON-First)

Write the structured review data to `review-walkthrough.json` as the **single source of truth**, then run `scripts/build-walkthrough.py` to deterministically render **both** the Markdown walkthrough and the card-based HTML companion in milliseconds.

#### 4a. Resolve the Storage Path (Ephemeral, Never Git-Tracked)

The walkthrough deliverables are disposable drafts. They must never be committed and never live in `.git/`. Resolve the target directory using this fallback hierarchy (first match wins):

1. **Repository temp directory (first priority):** a local scratch directory (e.g., `tmp/`, `.tmp/`), after verifying with `git check-ignore` that it is excluded from tracking. This is the preferred home for both deliverables, easily opened in IDE and browser.
2. **Harness artifact directory:** the harness's dedicated artifact/scratch directory (e.g., Antigravity artifact directory).
3. **System temp directory (final fallback):** e.g., `/tmp/review-walkthrough-<branch>-<timestamp>/`.

Write `review-walkthrough.json` into this directory. The generator script outputs `review-walkthrough.md` and `review-walkthrough.html` side-by-side in the same location.

#### 4b. Tone & Style Guidelines (Anti-Fatigue)

- **Language Adaptation & Localization:** Always write in the language of the user's first prompt. Detect it once and use it across all fields (`lang: "fa"`, `"en"`, `"de"`, `"es"`).
  - **Full Document Localization:** All section titles, roles, and gotcha explanations match the target language.
  - **No Bilingual Tagging:** Write pure native titles. Never append English duplicates in parentheses.
  - **RTL Layout Preservation:** In RTL languages (Persian, Arabic, Hebrew), every line, heading, list item, and metadata label must start with a native RTL word so renderers resolve block direction to RTL.
  - **Pure Human Prose:** Body text and summaries must be 100% natural conversational prose. **Never prepend parenthesized path mentions** (e.g., do NOT start text with `(Bar.tsx:35): ...` or `([Bar.tsx:35](#)): ...`). File references belong exclusively in the structured `refs` arrays.
  - **Technical Terms & Acronyms in Latin Script:** Code symbols, identifiers, file paths, protocols, and technical acronyms (e.g., WebRTC, REST, API) remain in Latin script verbatim (`backticks` in prose).
- **Everyday Spoken Developer Voice:** Write like a sharp colleague sitting right next to the reviewer. Be punchy, conversational, and direct.
- **Fit in 1–2 Screens:** Target roughly 40–60 lines total in Markdown; compact auto-sized cards in HTML.

#### 4c. Data Contract Cheat-Sheet (Schema v2)

Write `review-walkthrough.json` following this structure:

```json
{
  "schemaVersion": 2,
  "lang": "fa",
  "meta": {
    "title": "Short descriptive title of the change",
    "branch": "feat/my-branch",
    "base": "main",
    "headSha": "short HEAD commit hash",
    "stats": { "files": 3, "added": 45, "removed": 12 }
  },
  "repo": {
    "root": "/path/to/repo/root",
    "defaultEditor": "vscode"
  },
  "steps": [
    {
      "id": "scope",
      "kind": "scope",
      "section": "دامنه",
      "title": "تغییر کوچک و یکپارچه — در یک نگاه بخوانید.",
      "gist": ["جمله اول خلاصه تغییرات.", "جمله دوم."],
      "affects": "بخش‌های تحت‌تأثیر در سیستم"
    },
    {
      "id": "my-gotcha-slug",
      "kind": "gotcha",
      "section": "نکات حساس و ریسک‌ها",
      "title": "عنوان کوتاه ریسک یا باگ احتمالی",
      "category": "concurrency | edge-case | state | layout | persistence | other",
      "body": "متن روان و انسانی بدون ذکر نام فایل در ابتدای جمله.",
      "refs": [
        { "path": "src/services/job.ts", "startLine": 42, "endLine": 50 }
      ],
      "lookFor": "بررسی کنید که فلان شرط رعایت شده باشد."
    },
    {
      "id": "reading-order",
      "kind": "reading",
      "section": "ترتیب پیشنهادی بررسی",
      "title": "ترتیب بررسی: لایه پایه ← لایه واسط",
      "items": [
        {
          "role": "مدل داده",
          "path": "src/models/user.ts",
          "startLine": 1,
          "endLine": 40,
          "summary": "تعریف ساختار داده و تایپ‌ها."
        }
      ],
      "skim": ["README.md", "package.json"]
    },
    {
      "id": "what-to-test",
      "kind": "test",
      "section": "مواردی که باید تست شوند",
      "title": "این ۲ مورد را روی دستگاه بررسی کنید.",
      "items": [
        "تست سناریوی اول.",
        "تست سناریوی دوم."
      ]
    }
  ]
}
```

- Steps order is strictly: `scope`, `split`? (only for massive diffs >15 files), `gotcha` × 1–4, `reading`, `test`.
- Every gotcha requires 1–3 structured `refs` with repo-relative `path` and `startLine` (supports any file: `Dockerfile`, `.env`, `Makefile`, etc.).
- Titles ≤160 characters.
- **RTL directional arrows:** In RTL languages (e.g. Persian/Farsi), reading and process flows go strictly right-to-left. Always use leftwards arrow `←` (`U+2190`) for progression in titles and reading orders (e.g. `ترتیب بررسی: لایه پایه ← لایه واسط`). Never use rightwards arrow `→` in RTL flows as it points backwards to earlier steps.

#### 4d. Deterministic Build (`build-walkthrough.py`)

Run the forward generator:

```bash
python3 scripts/build-walkthrough.py <path/to/review-walkthrough.json>
```

The script:
1. Validates the JSON against Schema v2.
2. Enriches git metadata and resolves bare basenames against changed files in `git diff --name-only`.
3. Deterministically renders `review-walkthrough.md` with localized headings and anchors.
4. Deterministically renders `review-walkthrough.html` (~24 KB, multi-IDE selector for VS Code, Cursor, Windsurf, Zed, Android Studio, GoLand, JetBrains, 1-click Copy Path, pure prose, and local Vazirmatn font support).
5. Exits 0 and reports both file paths.

---

### 5. Chat Briefing

After running the generator, reply concisely in the walkthrough language (3–6 lines max):

- The absolute paths to both deliverables (`review-walkthrough.md` and `review-walkthrough.html`).
- A 1-line recap of the branch and diff size.
- The split recommendation, if one was issued.
- The top 2 gotchas from the walkthrough in one line each.

Then stop. Do not walk through steps, do not ask the user to type `next`.

---

### 6. Passive Standby & Emergent Q&A (Turns 2..N)

The human drives pacing. The agent answers questions and otherwise stays out of the way.

- **Staleness check:** if the user mentions pushing, amending, or rebasing — or a long gap has passed — re-run `git rev-parse HEAD` and compare to the pinned commit. If it changed, flag it and offer to re-diff and regenerate the walkthrough (markdown and HTML together) rather than answering against stale content. Editor links open the working tree, so after a HEAD change their line numbers may no longer match.
- **Concern logging:** silently record substantive concerns, todos, and open questions raised during the conversation. Never rely on reconstructing them from scrollback later. The log feeds Section 7.
- **Answering technical questions** (e.g., *"In Layer 2, does `processOrder` handle concurrent duplicate requests?"*):
  - Investigate neutrally: read the target code, trace real execution paths and callers, and evaluate **both hypotheses** — what protections exist *and* what edge cases could defeat them.
  - Never set out to "confirm" the user's suspicion; never set out to dismiss it either. Report concrete evidence (`file:line`, caller traces) and state plainly which way the evidence points.
  - For broad multi-file questions, dispatch one neutral research subagent per the template in `references/review-rubric.md` (Section 3b); without subagent support, run the same investigation directly.

---

### 7. Strictly On-Demand Outputs

- **Never** generate an unsolicited sign-off recap, approval summary, or PR comment block.
- Only when the user explicitly asks (e.g., *"Format our findings into a PR review comment"*), compile the logged concerns, agreements, and open questions from Section 6 into a ready-to-post markdown block.