# Review Walkthrough Rubric & Reference

Supplementary heuristics for executing the `review-walkthrough` skill: vertical slicing heuristics, punchy `Heads Up` formulation, neutral-investigation templates, and qualitative content-shaping rules for Schema v3.

---

## 1. Vertical Slicing Heuristics

Organize every walkthrough into cohesive **Vertical Slices** — workflow or sub-change units that each tell a complete story — rather than grouping the entire diff into horizontal technical layers.

### How to Slice a Diff
1. **Slice by Workflow or Sub-Change:** Group changes that serve the same user flow, feature behavior, or refactor goal into one `Vertical Slice` (e.g., `auth-token-refresh`, `checkout-validation`, `settings-modal`).
2. **Sequence Files Within Each Slice:** Inside a slice's `files` array, order files logically from contract/data to behavior to caller/UI to tests so the reviewer builds context as they read.
3. **Allow a File in Multiple Slices with Distinct Ranges:** When one file serves two unrelated workflows, include it in both corresponding slices with its distinct `startLine`–`endLine` range in each. Within a single slice, consolidate scattered edits in the same file into one entry rather than fragmenting it into multiple bullets.
4. **Reserve `Cross-Cutting` for Multi-Slice Concerns:** Put `Heads Up` notes or end-to-end `QA Check` scenarios in `crossCutting` only when they genuinely span multiple slices (such as shared migrations, global state interactions, or end-to-end flows). Never force a slice-specific risk into `Cross-Cutting` or a cross-slice risk into an arbitrary slice.
5. **Tuck Boilerplate into `Skim List`:** Put lockfiles, generated artifacts, pure documentation, and mechanical renames in `overview.skim` as bare repo-relative paths. They render collapsed by default inside `Overview`.

### Anti-Fatigue Rules for Slices & Files
- **Role-First Format:** Begin each file item's `role` with a concise noun phrase in the conversation language (which renders as `- [ ] **<Role>** ([file.ext:line](#)): <Summary>` in Markdown). In RTL languages, starting with native text ensures the list item renders right-to-left.
- **Omit ASCII Diagrams:** Do not include ASCII tree diagrams unless the diff is massive (>20 files) and has complex branching. Vertical slices with ordered file lists are faster to parse and avoid visual clutter.
- **Omit Duplicate `Overview` Prose on Single-Slice Trivial Diffs:** When a diff has only one simple slice, omit `overview.summary` so the `Overview` only shows title, metadata, `affects`, and optional `Skim List` without repeating the slice summary back-to-back.
- **Qualitative Anti-Fatigue Scaling:** Match depth to the actual diff. Small, clean refactors can have 1 slice, 0 `Heads Up`, and 0 `QA Check` items. Complex diffs can include as many slices, paragraphs, `Heads Up` notes, and `QA Check` items as the code genuinely warrants — never pad with filler or squeeze real risks to hit a numeric quota.

---

## 2. Heads Up (Risks & Edge Cases) Formulation

`Heads Up` items must be line-anchored (inside a `Vertical Slice`), practical, and written in direct spoken developer language matching the user's conversational language. They sit directly below the slice's `Files` list so the reviewer sees warnings right after reading the code they apply to.

### Localization & RTL Guidelines
- **Pure Localization:** Translate section headers (`### Heads Up` → `### نکات حساس و ریسک‌ها`, `### Achtung: Risiken`, etc.) and titles without bilingual English tagging (avoid `### Heads Up (نکات...)`).
- **RTL Integrity:** In RTL languages (Persian, Arabic, Hebrew), ensure titles, bullets, and checklist items start with native text rather than English prefixes, allowing renderers to set right-to-left block direction naturally.
- **Technical Terms & Acronyms in Latin Script:** Code symbols, identifiers, file paths, protocols, and technical acronyms (e.g., WebRTC, ICE, `mutex.Lock()`, `flexDirection`) remain in Latin script (backticks for code/identifiers/paths; optional for general acronyms in prose). Never phonetically transliterate them into native script (e.g., do NOT write وب‌آرتی‌سی for WebRTC, or استیل for stale). For terms without a natural localized form in developer speech, use the standard term (e.g., برنچ rather than an unfamiliar translation like شاخه).

### Tone & Style: Direct vs. Academic

| Style | Don't Do This (Academic & Stiff) | Do This (Conversational & Punchy) |
| :--- | :--- | :--- |
| **Title** | `Concurrency Invariant & Race Window In Worker` | `پنجرهٔ رقابت در چک اولیهٔ فعال‌بودن` / `Potential race condition in worker activation` |
| **Body** | `Question: Is mutex.Lock() acquired before checking is_active (worker.ts:130), or does a race window exist where two concurrent routines evaluate the predicate simultaneously?` | `Lock is checked after \`is_active\`. If two jobs arrive at once, both might pass before either locks.` |
| **Layout Flip** | `Question: Within an LTR-directed container, will Yoga layout the video control bar in reverse order when isRTL() evaluates to false?` | `The container forces \`ltr\`, but line 85 still flips \`flexDirection\`. In LTR mode, this might reverse the buttons (fullscreen on left, play on right).` |

### Common Risk Patterns to Watch For
Schema v3 does not use `category` badges; use these patterns purely as review prompts when scanning a slice:
- **Edge cases & boundary traps:** Zero values, empty lists, null handling, division by zero.
- **State & re-render fan-out:** Broad reactive state selectors that trigger unnecessary renders on idle components.
- **Layout & styling collisions:** Competing CSS/flex properties (e.g., forced LTR container with inline RTL direction flip).
- **Concurrency & ordering:** Missing mutexes, non-atomic multi-step operations, lifecycle race conditions.
- **Persistence & reset surprises:** Values unintentionally reset on track/page switches, or stale cached values.

---

## 3. Neutral Investigation Protocol & Review State

When the reviewer asks an ad-hoc question during standby, investigate without a thumb on the scale.

### 3a. Investigation Checklist
1. Restate the question as two competing hypotheses (e.g., "protected against duplicates" vs. "a duplicate path exists").
2. Read the target code and its real callers using targeted line reads (`view_file` with `StartLine`/`EndLine` rather than reading whole files) to protect context headroom — prefer graph tools (`trace_path`, `search_graph`) when available, grep otherwise.
3. Collect concrete evidence for **both** sides: `file:line` references and actual execution paths.
4. Report which way the evidence points, with the evidence. Keep the explanation direct and conversational. If unresolved, say so and name what would resolve it.

### 3b. Persistent Review Concerns Store (`review-concerns.json`)

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
      "source": "headsUp | qa | reviewer",
      "sliceId": "optional-link-to-walkthrough-slice-id",
      "headsUpId": "optional-link-to-heads-up-item",
      "gotchaId": "optional-legacy-alias-for-headsUpId",
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
- **`open`**: Initial state for walkthrough `Heads Up` items or newly raised reviewer questions awaiting investigation.
- **`action-needed`**: Confirmed defect, subtle bug, or agreed code change that should be addressed before merging.
- **`resolved`**: Investigated and verified safe (false alarm dismissed with concrete code evidence).
- **`accepted-risk`**: Genuine trade-off or technical debt explicitly acknowledged by the reviewer as acceptable for this PR.

#### Compiling to PR Review Comments (Section 7)
When the user explicitly asks to format PR comments, read `review-concerns.json`, filter for items where `status == "action-needed"`, and emit a clean, ready-to-post markdown block grouped by file and line anchor. Never output unsolicited review comments.

---

## 4. Structured Walkthrough: Content-Shaping Rules

The walkthrough is authored JSON-first (`review-walkthrough.json`, Schema v3), from which both the Markdown walkthrough and the scrollable HTML companion are deterministically compiled by `scripts/build-walkthrough.py`. The structured JSON is the single source of truth. The full technical spec lives in [`html-walkthrough.md`](html-walkthrough.md).

### 4a. Pure Prose Bodies & Structured Anchors
- **Pure Conversational Prose:** `headsUp[*].body` and `files[*].summary` must be 100% natural conversational prose. **Never prepend parenthesized path mentions** (e.g., do NOT write `(Bar.tsx:35): ...` or `([Bar.tsx:35](#)): ...`).
- **Structured References:** File references live strictly inside structured `refs` arrays (or `files` entries in each slice) with `path`, `startLine`, and optional `endLine`.
- The compiler/renderer automatically constructs file links and 1-click Copy Path pills (`.ref-pill`) in HTML, and clean links alongside bold roles in Markdown.

### 4b. Qualitative Anti-Fatigue Shaping
- **No Rigid Numeric Caps:** Schema v3 imposes no hard limits on item counts, summary paragraph counts, or title character lengths. Use judgment based on the diff's actual complexity.
- **Synthesize Titles Cleanly:** `overview.title` frames the overall change; each `slice.title` names the workflow or sub-change cleanly (never copy the first file's summary verbatim).
- **Tight, Un-truncated Prose:** Keep `headsUp[*].body` and `lookFor` direct and scannable without truncating real context. Use `extra` only for a genuine secondary edge case.
- **Omit Empty Sections:** If a slice has no `Heads Up` risks or no manual `QA Check` steps, omit `headsUp` / `qa` (or leave empty) rather than inventing filler. On a single-slice trivial diff, omit `overview.summary`.

### 4c. Do Not Invent Structure the Walkthrough Doesn't Have
- No severity levels, no `category` badges, no "must fix / should fix" labels, no ready-made fixes, no pass/fail verdicts. The walkthrough orients the reviewer; it does not judge.
- No code snippets or diff hunks in the HTML. The reviewer reads real, untrimmed code in the IDE, and the editor links / copy buttons are the bridge to it.
- **Anchoring Rule:** Every `Heads Up` inside a `Vertical Slice` must carry at least one verifiable `file:line` ref (`refs.length >= 1`). Only `Cross-Cutting` `Heads Up` items may have an empty `refs` array when the risk spans multiple slices without a single anchor.

### 4d. Reading Files & Skim List
- Within a single slice, use one `files` entry per file with its consolidated `startLine`–`endLine` range; `role` is a short noun phrase, not a sentence.
- When a file serves multiple unrelated workflows, it may appear in multiple slices with its distinct `startLine`–`endLine` range in each.
- Keep `overview.skim` for bare repo-relative paths of boilerplate, lockfiles, docs, and generated files.
