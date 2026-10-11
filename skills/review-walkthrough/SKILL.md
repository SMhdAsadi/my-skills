---
name: review-walkthrough
description: "Generates an anti-fatigue review walkthrough for a branch diff (a lean markdown file plus a card-based HTML companion with clickable editor links), then stays on standby as an on-demand review co-pilot. Use when the user wants to walk through changes, review a branch, examine a diff, or asks for a guided code review."
license: MIT
compatibility: "git >= 2.0"
metadata:
  author: SMhd
  version: "2.2.0"
  tags:
    - git
    - code-review
    - walkthrough
    - developer-tools
    - html
---

# Review Walkthrough

An **Anti-Fatigue Review Walkthrough Generator and On-Demand Review Co-Pilot** designed to help developers review code better and faster in their native IDE.

Instead of dumping a wall of formal academic text or gating the review behind turn-by-turn chat steps, this skill analyzes the branch diff once, writes a lean, high-signal, engaging **review walkthrough** to an ephemeral markdown artifact (plus a card-based HTML companion of the same content), and then stands by: the human reviews at their own pace in their IDE or diff viewer, and asks the agent questions only when they hit ambiguities, tricky logic, or suspected bugs. Consult [`references/review-rubric.md`](references/review-rubric.md) for layering heuristics, risk-hypothesis formulas, investigation templates, and HTML content-shaping rules. Consult [`references/html-walkthrough.md`](references/html-walkthrough.md) for the full HTML companion spec (design, wording, RTL, data contract, editor links).

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
5. Gauge diff size (files changed, lines changed). This drives the split assessment (Section 2) and the walkthrough's scale (Section 4).
6. Read the changed files and hunk details to understand the core mechanisms before generating the walkthrough.

---

### 2. Split Assessment (Root Cause First)

Large diffs are the primary driver of review fatigue and missed defects. If the diff exceeds the large-diff threshold (rule of thumb: >15 files or >800 changed lines):

- Open the walkthrough with an explicit **Split Recommendation**: state that splitting the change into smaller, independently reviewable units is the superior fix, and suggest a concrete split boundary when one is visible (e.g., schema migration first, then domain logic, then consumers).
- Still generate the full walkthrough — reviewers frequently inherit diffs they cannot split (AI-authored branches, legacy changes, external PRs).

For typical-sized diffs, omit this section entirely.

---

### 3. Gather Structural Intelligence (Progressive Tooling)

Remain portable across harnesses while exploiting graph-based code intelligence when present.

- **Tier 1 (Graph-Powered):** If structural/graph MCP tools (e.g., `search_graph`, `trace_path`, `query_graph`, `get_architecture`) or LSP symbol tools are available:
  - Use them to map dependency layers (separating domain contracts from consumer leaves) and trace inbound callers of changed symbols for a grounded blast radius.
- **Tier 2 (Syntactic Fallback):** If graph tools are unavailable:
  - Degrade gracefully to git commands (`git diff --stat`, `git log`), directory-path heuristics, grep, and file reading.
  - Label any blast-radius or dependency claim as heuristic, or omit it. Never present Tier-2 speculation with Tier-1 confidence.
  - Never crash or fail due to the absence of graph tools.

---

### 4. Generate the Review Walkthrough

Write the complete walkthrough as a single markdown artifact. **One shot** — do not page it through chat. Then generate the HTML companion (Section 4d) from that finished markdown.

#### 4a. Resolve the Storage Path (Ephemeral, Never Git-Tracked)

The walkthrough is a disposable draft. It must never be committed and never live in `.git/`. Resolve the path using this fallback hierarchy:

1. **Agent harness storage (first priority):** the harness's dedicated artifact/scratch directory, if the environment provides one.
2. **Repository temp directory:** a local scratch directory (e.g., `tmp/`, `.tmp/`), but only after verifying with `git check-ignore` that it is excluded from tracking.
3. **System temp directory (final fallback):** e.g., `/tmp/review-walkthrough-<branch>-<timestamp>.md` on Unix.

The HTML companion lives in the same directory with the same basename and a `.html` extension. Report the resolved absolute path(s) to the user so they can open them directly.

#### 4b. Tone & Style Guidelines (Anti-Fatigue)

These rules govern the **markdown** walkthrough. The HTML companion keeps the same facts but follows its own register rules (see `references/html-walkthrough.md`, "Language & wording").

- **Language Adaptation & Localization:** Always write the review walkthrough in the language of the user's first prompt (the one that triggered this skill). Detect it once and use it for every artifact, including the HTML companion, even if later messages switch language.
  - **Full Document Localization:** Translate all structural section headings, title prefixes, and metadata labels into the active language (`# Review Walkthrough:` → `# راهنمای بررسی:`, `**Affects:**` → `**بخش‌های تحت‌تأثیر:**`, `### The Gist` → `### خلاصه تغییرات`, `### Heads Up` → `### نکات حساس و ریسک‌ها`, `### Suggested Reading Order` → `### ترتیب پیشنهادی بررسی`, `*Skim:*` → `*بررسی گذرا:*`, `### What to Test` → `### مواردی که باید تست شوند`).
  - **No Bilingual Tagging:** Write pure native titles. Never retain hardcoded English headings or append English duplicates in parentheses (e.g., do NOT write `### Heads Up (نکات...)` or `### ترتیب بررسی (Suggested Reading Order)` or `**Affects:**`).
  - **RTL Layout Preservation:** In Right-to-Left (RTL) languages (Persian, Arabic, Hebrew), every line, heading, list item, and metadata label must start with a native RTL word so that markdown renderers resolve the paragraph direction to RTL. Starting lines with English words breaks text alignment and flips punctuation.
  - **Technical Terms & Acronyms in Latin Script:** Code symbols, identifiers, file paths, protocols, and technical acronyms (e.g., WebRTC, ICE, REST, API) must remain in Latin script (use backticks for code symbols, branch names, and file paths; backticks are optional for general acronyms in prose). Never phonetically transliterate them into native script (e.g., do NOT write وب‌آرتی‌سی for WebRTC, or استیل for stale). For terms without a natural localized form in developer speech, use the standard term (e.g., برنچ rather than an unfamiliar translation like شاخه).
- **Everyday Spoken Developer Voice:** Write like a sharp colleague sitting right next to the reviewer. Be punchy, conversational, and direct. Use natural spoken phrasing ("Heads up", "Watch out for", "Check if" in English, or their natural spoken equivalents in the target language).
- **Zero Academic Fluff:** Avoid stiff corporate or academic jargon (e.g., "Executive Context & Invariant Delta", "Topological Itinerary", "Tier-1 Grounded Blast Radius"). Avoid legalistic disclaimer callouts.
- **Fit in 1–2 Screens:** Target roughly 40–60 lines total. High signal density, zero fluff, minimal scrollbar fatigue.

#### 4c. Walkthrough Structure

Render all section titles and labels in the active conversation language (see reference table below).

1. **Header & Quick Scope:**
   - Title: `# <Review Walkthrough Title>: <Branch / Feature Name>`
   - Scope bar (single compact line): `**<Branch Label>:** <branch> → <base> • **<X files> (+Y / -Z)**`
   - Blast Radius: `**<Affects Label>:** <1-line summary of components/state affected>`
   - Do NOT include multi-row tables with 40-character commit hashes, and do NOT include disclaimer callouts.
2. **Split Recommendation:** (Only when Section 2 applies for massive diffs).
   - Heading: `### <Split Recommendation Title>`
3. **The Gist (Core Summary):**
   - Heading: `### <The Gist Title>`
   - 2–3 short sentences in everyday language: what this change actually does, and what must stay untouched.
4. **Heads Up (Key Gotchas & Risks):**
   - Heading: `### <Heads Up / Risks Title>`
   - Placed right after The Gist so the reviewer sees pitfalls *before* diving into the code.
   - 2–4 concrete, line-anchored gotchas.
   - Format: `- **<Gotcha Title in user language>** ([file.ext:line](#)): <1-2 conversational sentences explaining the trap or edge case>.`
5. **Suggested Reading Order:**
   - Heading: `### <Suggested Reading Order Title>`
   - Foundation first, then UI/consumers.
   - **Group by file:** Do not create separate bullet points for multiple small line ranges in the same file. Use a consolidated range (e.g., `VSlider.tsx:49-180`) with a brief summary of changes in that file.
   - Format: `- [ ] **<File / Component Role in user language>** ([file.ext:line](#)): <Brief summary of changes>.` Checkboxes must have direct, clickable `file:line` links.
   - **Skimmable files:** Do NOT create a separate table for boilerplate or docs. Add a single line at the end: `*<Skim Label>: <file1>, <file2>*`.
   - Do NOT include ASCII box diagrams unless the diff is massive (>20 files) with complex multi-branching.
6. **What to Test:**
   - Heading: `### <What to Test Title>`
   - 2–3 quick bullet points naming practical test cases, device scenarios, or automated test commands.

##### Heading & Label Reference by Language
| Element | English | Persian (فارسی) | German | Spanish |
| :--- | :--- | :--- | :--- | :--- |
| **Title Prefix** | `# Review Walkthrough:` | `# راهنمای بررسی:` | `# Review-Überblick:` | `# Guía de Revisión:` |
| **Branch Label** | `**Branch:**` | `**برنچ:**` | `**Branch:**` | `**Rama:**` |
| **Affects Label** | `**Affects:**` | `**بخش‌های تحت‌تأثیر:**` | `**Betrifft:**` | `**Afecta:**` |
| **Split Section** | `### Split Recommendation` | `### پیشنهاد تفکیک برنچ` | `### Aufteilungsempfehlung` | `### Sugerencia de División` |
| **Gist Section** | `### The Gist` | `### خلاصه تغییرات` | `### Das Wichtigste` | `### En Resumen` |
| **Gotchas Section** | `### Heads Up` | `### نکات حساس و ریسک‌ها` | `### Achtung: Risiken & Fallstricke` | `### Puntos Críticos y Riesgos` |
| **Reading Order** | `### Suggested Reading Order` | `### ترتیب پیشنهادی بررسی` | `### Empfohlene Lesereihenfolge` | `### Orden de Lectura Sugerido` |
| **Skim Label** | `*Skim:*` | `*بررسی گذرا:*` | `*Überfliegen:*` | `*Vistazo rápido:*` |
| **Test Section** | `### What to Test` | `### مواردی که باید تست شوند` | `### Was getestet werden sollte` | `### Qué Probar` |

*(For languages not listed, translate the concepts idiomatically using the same natural, non-bilingual pattern).*

**Anchoring rule:** every substantive claim or gotcha must reference a verifiable `file:line`. If a mechanism cannot be anchored, flag it explicitly or omit it.

**Do not include:** paged diff hunks, lint/formatting nits, generic checklist questions ("is this secure?"), or pass/fail approval badges.

#### 4d. Generate the HTML Companion

After the markdown is written, generate a self-contained, card-based **HTML companion**: one card per step, light/dark theme following the OS, full RTL support, and every `file:line` reference opening the user's editor (VS Code by default).

Generate it by default. Skip it only when the user asks for markdown only or says they don't want HTML.

1. **Read the spec first.** Read [`references/html-walkthrough.md`](references/html-walkthrough.md) in full before generating anything. It is authoritative for design tokens, wording and register, fonts, RTL rules, the JSON data contract, editor links, and verification. Do not work from memory.
2. **The markdown is the single source of truth.** Build the HTML data from the finished markdown walkthrough: same gotchas, same files, same order, same `file:line` anchors. Never add a claim the markdown does not make, and never drop one. Wording may be re-expressed in the HTML's register; facts may not change. Apply the content-shaping rules in `references/review-rubric.md` (Section 4).
3. **Map sections to steps:**

   | Markdown section | HTML step (`kind`) |
   | :--- | :--- |
   | Header & Quick Scope + The Gist | `scope` (always first) |
   | Split Recommendation | `split` (only when the markdown has one) |
   | Each Heads Up bullet | one `gotcha` step each |
   | Suggested Reading Order + Skim line | one `reading` step |
   | What to Test | one `test` step |

4. **Fill `repo`.** Run `git rev-parse --show-toplevel` in the reviewed checkout (use the worktree path if the review ran in a git worktree) for `repo.root`. Never guess it; omit it if git cannot provide it. Default `repo.editor` to `vscode` unless the user named another editor.
5. **Write only the data.** Copy `assets/walkthrough-template.html` from this skill folder and replace only the contents of the `<script type="application/json" id="walkthrough-data">` block (the template ships with an empty `{}`). Never edit the template's markup, CSS, JS, or embedded fonts. If the template is missing, skip the HTML and say so in the briefing.
6. **Validate before writing.** Check the JSON against the validation rules in the spec. Write the file to the same directory and basename as the markdown, with `.html`.
7. **Verify what you can.** Run the verification checklist in the spec as far as the environment allows. List the checks you could not run in the chat briefing instead of claiming them.
8. **Fail safe.** If the HTML cannot be produced correctly (validation fails, or the template is missing), do not ship a half-built or fallback-font file. The markdown remains the deliverable; say in the briefing that the HTML was skipped and why.

The HTML uses the same language as the markdown (the first prompt's language) and declares it in the JSON `lang` field. The template has built-in UI strings for English and Persian and sets direction and font automatically; for any other language, supply a complete `ui` object (see the spec's "Other languages" section).

---

### 5. Chat Briefing

After writing the walkthrough, reply concisely in the walkthrough language (3–6 lines max):

- The absolute path to the review walkthrough artifact, and to the HTML companion when one was generated (or one line saying it was skipped and why).
- A 1-line recap of the branch and diff size.
- The split recommendation, if one was issued.
- The top 2 gotchas from the walkthrough in one line each.
- Any HTML verification checks that could not be run.

Then stop. Do not walk through steps, do not ask the user to type `next`.

---

### 6. Passive Standby & Emergent Q&A (Turns 2..N)

The human drives pacing. The agent answers questions and otherwise stays out of the way.

- **Staleness check:** if the user mentions pushing, amending, or rebasing — or a long gap has passed — re-run `git rev-parse HEAD` and compare to the pinned commit. If it changed, flag it and offer to re-diff and regenerate the walkthrough (markdown and HTML together) rather than answering against stale content. Editor links open the working tree, so after a HEAD change their line numbers may no longer match.
- **Concern logging:** silently record substantive concerns, todos, and open questions raised during the conversation. Never rely on reconstructing them from scrollback later. The log feeds Section 7.
- **Answering technical questions** (e.g., *"In Layer 2, does `processOrder` handle concurrent duplicate requests?"*):
  - Investigate neutrally: read the target code, trace real execution paths and callers, and evaluate **both hypotheses** — what protections exist *and* what edge cases could defeat them.
  - Never set out to "confirm" the user's suspicion; never set out to dismiss it either. Report concrete evidence (`file:line`, caller traces) and state plainly which way the evidence points.
  - **Delegation (when subagents are supported):** for questions needing broad multi-file investigation, the primary agent may orchestrate an ephemeral research subagent. The dispatch prompt must carry sufficient context (branch diff location, target symbols, line ranges) while remaining strictly neutral — instruct the subagent to evaluate both hypotheses and gather execution paths, never to confirm a specific bug. Synthesize the subagent's findings into a direct, concise answer.
  - **Fallback (no subagent support):** the primary agent performs the same investigation itself under the identical both-hypotheses rule.

---

### 7. Strictly On-Demand Outputs

- **Never** generate an unsolicited sign-off recap, approval summary, or PR comment block.
- Only when the user explicitly asks (e.g., *"Format our findings into a PR review comment"*), compile the logged concerns, agreements, and open questions from Section 6 into a ready-to-post markdown block.