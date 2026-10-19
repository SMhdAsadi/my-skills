# Review Walkthrough Rubric & Reference

Supplementary heuristics for executing the `review-walkthrough` skill: practical sequencing, punchy gotcha formulation, neutral-investigation templates, and content-shaping rules for the HTML companion.

---

## 1. Suggested Reading Order (Foundation to Leaf)

Sequence the files by architectural dependency. Leaf nodes (UI components, API routes) cannot be properly evaluated without first understanding the underlying data contracts and domain rules.

### Core Order Principle
1. **Data Models & Types** (`*.types.ts`, schemas, migrations) — Defines data shapes and invariants.
2. **Core Domain Logic & State** (`services/`, state reducers, business rules) — Algorithms and logic independent of I/O.
3. **Side Effects & I/O** (`controllers/`, HTTP clients, DB queries, workers) — External integration.
4. **Presentation & UI** (`components/`, views, styling) — Visual rendering and state binding.
5. **Tests & Tooling** (`*.test.ts`, configs, scripts) — Verification of the layers above.

### Anti-Fatigue Rules for the Reading Order:
- **Role-First Format:** Begin each checklist item with a concise bold role or component name in the conversation language, followed by the file link and summary: `- [ ] **<Role>** ([file.ext:line](#)): <Summary>`. In RTL languages, this ensures the line starts with native text so the list item renders right-to-left.
- **Group by File:** Consolidate multiple changes in the same file into a single checklist entry with a range (e.g., `VSlider.tsx:49-180`). Never fragment one file into 4 separate bullets for scattered lines.
- **Omit ASCII Diagrams:** Do not include ASCII tree diagrams unless the diff is massive (>20 files) and has complex branching. For typical diffs, a simple numbered list is faster to parse and saves vertical space.
- **Merge Skimmables:** List boilerplate, documentation, lockfiles, and generated files as a single footer note (`*Skim: ...*` or its localized equivalent like `*بررسی گذرا: ...*`) rather than wasting vertical space on a separate table.

---

## 2. Heads Up (Gotchas & Risks) Formulation

Gotchas must be line-anchored, practical, and written in direct spoken developer language matching the user's conversational language. They highlight potential traps, regressions, or subtle edge cases before the reviewer begins reading the diff.

### Localization & RTL Guidelines
- **Pure Localization:** Translate the section header (`### Heads Up` → `### نکات حساس و ریسک‌ها`, `### Achtung: Risiken`, etc.) and gotcha titles without bilingual English tagging (avoid `### Heads Up (نکات...)` or `(Suggested Reading Order)`).
- **RTL Integrity:** In RTL languages (Persian, Arabic, Hebrew), ensure titles, bullets, and checklist items start with native text rather than English prefixes, allowing the markdown renderer to set right-to-left block direction naturally.
- **Technical Terms & Acronyms in Latin Script:** Code symbols, identifiers, file paths, protocols, and technical acronyms (e.g., WebRTC, ICE, `mutex.Lock()`, `flexDirection`) remain in Latin script (backticks for code/identifiers/paths; optional for general acronyms in prose). Never phonetically transliterate them into native script (e.g., do NOT write وب‌آرتی‌سی for WebRTC, or استیل for stale). For terms without a natural localized form in developer speech, use the standard term (e.g., برنچ rather than an unfamiliar translation like شاخه).

### Tone & Style: Direct vs. Academic

| Style | Don't Do This (Academic & Stiff) | Do This (Conversational & Punchy) |
| :--- | :--- | :--- |
| **Header** | `### 1. Concurrency Invariant & Race Window In Worker` | `- **Potential race condition** ([worker.ts:130](#)):` |
| **Body** | `Question: Is mutex.Lock() acquired before checking is_active (worker.ts:130), or does a race window exist where two concurrent routines evaluate the predicate simultaneously?` | `Lock is checked after \`is_active\`. If two jobs arrive at once, both might pass before either locks.` |
| **Layout Flip** | `Question: Within an LTR-directed container, will Yoga layout the video control bar in reverse order when isRTL() evaluates to false?` | `The container forces \`ltr\`, but line 85 still flips \`flexDirection\`. In LTR mode, this might reverse the buttons (fullscreen on left, play on right).` |

### Key Gotcha Categories
- **Edge cases & boundary traps:** Zero values, empty slices, null handling, division by zero.
- **State & re-render fan-out:** Broad reactive state selectors that trigger unnecessary renders on idle components.
- **Layout & styling collisions:** Competing CSS/flex properties (e.g., forced LTR container with inline RTL direction flip).
- **Concurrency & ordering:** Missing mutexes, non-atomic multi-step operations, lifecycle race conditions.
- **Persistence & reset surprises:** Values unintentionally reset on track/page switches, or stale cached values.

---

## 3. Neutral Investigation Protocol & Review State

When the reviewer asks an ad-hoc question during standby, investigate without a thumb on the scale.

### 3a. Investigation Checklist
1. Restate the question as two competing hypotheses (e.g., "protected against duplicates" vs. "a duplicate path exists").
2. Read the target code and its real callers — prefer graph tools (`trace_path`, `search_graph`) when available, grep otherwise.
3. Collect concrete evidence for **both** sides: `file:line` references and actual execution paths.
4. Report which way the evidence points, with the evidence. Keep the explanation direct and conversational. If unresolved, say so and name what would resolve it.

### 3b. Investigator Subagent Dispatch (Tier S Harnesses)

When running in a multi-agent harness, dispatch an isolated investigator subagent for questions that warrant real investigation. Subagents communicate naturally and thoroughly with the primary agent without artificial line caps:

> **Role:** `Code Review Investigator`
> **Prompt Template:**
> Investigate a code-review question in `<repo>`. Context: branch `<branch>` (HEAD: `<headSha>`, base: `<base>`); inspect the diff with `git diff <base>...HEAD`.
> Target symbols/lines: `<symbols, file:line ranges>`.
>
> Question under review: `<user's question>`.
>
> Evaluate BOTH hypotheses neutrally:
> 1. The code handles this correctly: identify the protections that exist, contracts enforced, and where they live. Cite exact `file:line` locations.
> 2. The code can fail here: identify concrete edge cases, callers, or execution paths that defeat those protections. Cite exact `file:line` locations.
>
> Do not try to confirm a predetermined answer. Trace real callers and execution flow using graph or grep tools. Communicate your full findings, evidence, and code context freely and thoroughly, concluding with a clear statement on where the evidence points.

When subagents are unavailable (Tier C), the primary agent runs the identical investigation itself under the same both-hypotheses mandate, using targeted line reads (`view_file` with `StartLine`/`EndLine`) to protect context headroom.

### 3c. The Discretion Filter

Do not spawn subagents indiscriminately for every interaction:
- **Answer directly (in-context):** Simple syntax or code questions where the answer is visible in the diff, clarifications of the walkthrough cards or chat briefing, or quick single-file checks.
- **Dispatch Investigator Subagent:** Multi-file execution paths, concurrency/race-condition invariants, caller blast-radius inquiries across the repository, or git-history archaeology to determine why a pattern was established.

### 3d. Persistent Review Concerns Store (`review-concerns.json`)

To prevent loss of review findings during long conversations or session compactions, the agent maintains `<storage-dir>/review-concerns.json` as a structured single source of truth.

#### Data Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "version": 1,
  "headSha": "short HEAD commit hash",
  "baseRef": "main",
  "updatedAt": "ISO-8601 timestamp",
  "concerns": [
    {
      "id": "c1",
      "source": "gotcha | qa | reviewer",
      "gotchaId": "optional-link-to-walkthrough-gotcha-id",
      "ref": {
        "path": "src/services/worker.ts",
        "startLine": 130,
        "endLine": 142
      },
      "topic": "Potential race window in job activation check",
      "status": "open | action-needed | resolved | accepted-risk",
      "findings": "Full evidence summary detailing evaluated protections and failure modes.",
      "resolution": "Agreed conclusion or recommended fix.",
      "suggestedComment": "Markdown PR comment ready for posting (populated for action-needed items)."
    }
  ]
}
```

#### Status Lifecycle
- **`open`**: Initial state for walkthrough gotchas or newly raised reviewer questions awaiting investigation.
- **`action-needed`**: Confirmed defect, subtle bug, or agreed code change that should be addressed before merging.
- **`resolved`**: Investigated and verified safe (false alarm dismissed with concrete code evidence).
- **`accepted-risk`**: Genuine trade-off or technical debt explicitly acknowledged by the reviewer as acceptable for this PR.

#### Compiling to PR Review Comments (Section 7)
When the user explicitly asks to format PR comments, read `review-concerns.json`, filter for items where `status == "action-needed"`, and emit a clean, ready-to-post markdown block grouped by file and line anchor. Never output unsolicited review comments.

---

## 4. Structured Walkthrough: Content-Shaping Rules

The walkthrough is authored JSON-first (`review-walkthrough.json`), from which both the Markdown walkthrough and the card-based HTML companion are deterministically compiled by `scripts/build-walkthrough.py`. The structured JSON is the single source of truth. These rules keep the contents inside the anti-fatigue budget. The full technical spec lives in [`html-walkthrough.md`](html-walkthrough.md).

### 4a. Pure Prose Bodies & Structured Anchors
- **Pure Conversational Prose:** Body text in gotchas and summaries in reading items must be 100% natural conversational prose. **Never prepend parenthesized path mentions** (e.g., do NOT write `(Bar.tsx:35): ...` or `([Bar.tsx:35](#)): ...`).
- **Structured References:** File references live strictly inside structured `refs` arrays (or `items` for reading order) with `path`, `startLine`, and optional `endLine`.
- The generator/renderer automatically constructs file links and 1-click Copy Path pills (`.ref-pill`) in HTML, and clean links alongside bold roles in Markdown.

### 4b. Card Budget (Anti-Fatigue)
- Every card must read without scrolling on a phone-sized viewport (about 375×667) at normal text size.
- Step title: one sentence, at most 160 characters (scope = diff shape, reading = `Read in order: role1 → role2 …` or in RTL `ترتیب بررسی: نقش ۱ ← نقش ۲ …`, test = generic count-based line). Never copy item text into a title.
- Gotcha body: 1 to 2 sentences, full text, never truncated. `lookFor`: at most 1 sentence. `extra`: at most 1 short paragraph, only for a real edge case.
- Gotchas: 1–4 (rule of thumb: 2–4).
- Test items: 2–3, each one line, full text.

### 4c. Do Not Invent Structure the Walkthrough Doesn't Have
- No severity levels, no "must fix / should fix" labels, no ready-made fixes, no pass/fail verdicts. The walkthrough orients the reviewer; it does not judge.
- No code snippets or diff hunks in the HTML. The reviewer reads real, untrimmed code in the IDE, and the editor links / copy buttons are the bridge to it.
- No `evidence` or "why it matters" blocks unless the review findings specifically call for that explanation.
- A gotcha without at least one verifiable `file:line` ref is invalid (anchoring rule). Ensure every gotcha anchors to actual changed code.

### 4d. Gotcha Category Mapping
Pick exactly one `category` per gotcha, from the Key Gotcha Categories in Section 2:

| Key Gotcha Category | `category` value |
| :--- | :--- |
| Edge cases & boundary traps | `edge-case` |
| State & re-render fan-out | `state` |
| Layout & styling collisions | `layout` |
| Concurrency & ordering | `concurrency` |
| Persistence & reset surprises | `persistence` |
| Anything else | `other` |

### 4e. Reading-Order Items
- One item per file, with the consolidated range, exactly as in the markdown. `role` is a short noun phrase, not a sentence.
- Keep the foundation-to-leaf order from Section 1.
- The skimmable files go in `skim` as bare paths, never as separate items.