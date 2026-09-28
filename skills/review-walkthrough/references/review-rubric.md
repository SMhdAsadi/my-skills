# Review Walkthrough Rubric & Reference

Supplementary heuristics for executing the `review-walkthrough` skill: practical sequencing, punchy gotcha formulation, and neutral-investigation templates.

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
- **Group by File:** Consolidate multiple changes in the same file into a single checklist entry with a range (e.g., `VSlider.tsx:49-180`). Never fragment one file into 4 separate bullets for scattered lines.
- **Omit ASCII Diagrams:** Do not include ASCII tree diagrams unless the diff is massive (>20 files) and has complex branching. For typical diffs, a simple numbered list is faster to parse and saves vertical space.
- **Merge Skimmables:** List boilerplate, documentation, lockfiles, and generated files as a single footer note (`*Skim: ...*`) rather than wasting vertical space on a separate table.

---

## 2. Heads Up (Gotchas & Risks) Formulation

Gotchas must be line-anchored, practical, and written in direct spoken developer language (matching the user's conversational language). They highlight potential traps, regressions, or subtle edge cases before the reviewer begins reading the diff.

### Tone & Style: Direct vs. Academic

| Style | Don't Do This (Academic & Stiff) | Do This (Conversational & Punchy) |
| :--- | :--- | :--- |
| **Header** | `### 1. Concurrency Invariant & Race Window In Worker` | `- **Potential race condition** ([worker.ts:130](...)):` |
| **Body** | `Question: Is mutex.Lock() acquired before checking is_active (worker.ts:130), or does a race window exist where two concurrent routines evaluate the predicate simultaneously?` | `Lock is checked after \`is_active\`. If two jobs arrive at once, both might pass before either locks.` |
| **Layout Flip** | `Question: Within an LTR-directed container, will Yoga layout the video control bar in reverse order when isRTL() evaluates to false?` | `The container forces \`ltr\`, but line 85 still flips \`flexDirection\`. In LTR mode, this might reverse the buttons (fullscreen on left, play on right).` |

### Key Gotcha Categories
- **Edge cases & boundary traps:** Zero values, empty slices, null handling, division by zero.
- **State & re-render fan-out:** Broad reactive state selectors that trigger unnecessary renders on idle components.
- **Layout & styling collisions:** Competing CSS/flex properties (e.g., forced LTR container with inline RTL direction flip).
- **Concurrency & ordering:** Missing mutexes, non-atomic multi-step operations, lifecycle race conditions.
- **Persistence & reset surprises:** Values unintentionally reset on track/page switches, or stale cached values.

---

## 3. Neutral Investigation Protocol (Emergent Q&A)

When the reviewer asks an ad-hoc question during standby, investigate without a thumb on the scale.

### 3a. Investigation Checklist
1. Restate the question as two competing hypotheses (e.g., "protected against duplicates" vs. "a duplicate path exists").
2. Read the target code and its real callers — prefer graph tools (`trace_path`, `search_graph`) when available, grep otherwise.
3. Collect concrete evidence for **both** sides: `file:line` references and actual execution paths.
4. Report which way the evidence points, with the evidence. Keep the explanation direct and conversational. If unresolved, say so and name what would resolve it.

### 3b. Subagent Dispatch Template (when subagents are supported)

> Investigate a code-review question in <repo>. Context: branch `<branch>` vs base `<base>`; inspect the diff with `git diff <base>...HEAD`. Target symbols/lines: <symbols, file:line ranges>.
>
> Question under review: <user's question>.
>
> Evaluate BOTH hypotheses: (1) the code handles this correctly — identify the protections that exist and where they live; (2) the code can fail here — identify concrete edge cases, callers, or execution paths that defeat those protections. Do not try to confirm a predetermined answer. Gather caller traces and report evidence as `file:line` references. End with: evidence summary, which hypothesis the evidence supports, and any remaining uncertainty.

When subagents are unavailable, the primary agent runs the identical investigation itself under the same both-hypotheses mandate.

### 3c. Concern Log Format

Keep a running internal log during standby; it feeds on-demand output only, never unsolicited recaps:

```
- [Layer N / file:line] Concern or open question — status: open | resolved | accepted-risk
```

Compile the log into a ready-to-post markdown block only on explicit user request.
