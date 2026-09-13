# Review Walkthrough Rubric & Reference

Supplementary heuristics for executing the `review-walkthrough` skill: layer sequencing, risk-hypothesis formulation, and neutral-investigation templates.

---

## 1. Topological Reading Order (Foundation to Leaf)

Sequence the itinerary by architectural dependency. Leaf nodes cannot be properly evaluated without first understanding the underlying contracts and domain rules.

```
[Layer 1: Schemas & Types]
       │
       ▼
[Layer 2: Core Domain Logic]
       │
       ▼
[Layer 3: Side Effects & I/O]
       │
       ▼
[Layer 4: Presentation & UI]
       │
       ▼
[Layer 5: Tests & Infrastructure]
```

### Layer Definitions

| Order | Layer | File Patterns / Examples | Why Review Here First |
| :---: | :--- | :--- | :--- |
| **1** | **Data Models & Types** | `*.types.ts`, `schema.prisma`, `models.py`, DB migrations | Defines the data shape and invariants. All downstream code depends on these definitions. |
| **2** | **Core Domain Logic** | `services/`, `domain/`, state reducers, business rules | The heart of the change. Verifies algorithms, invariants, and edge conditions independent of I/O. |
| **3** | **Side Effects & I/O** | `controllers/`, `api/`, HTTP endpoints, DB queries, RPC, workers | Verifies how the system talks to external networks, disk, or databases. |
| **4** | **Presentation & UI** | `components/`, views, styling, templates | Validates user experience, state binding, and visual handling of loading/error states. |
| **5** | **Tests & Tooling** | `*.test.ts`, `*_test.go`, configs, CI workflows | Verifies test coverage, assertions, and build setup against the changes reviewed in layers 1–4. |

Not every diff touches every layer — merge or omit empty layers per the plan's scaling rule. In tangled codebases where no clean layering exists, order by observed caller/callee dependency instead of forcing the template.

---

## 2. Risk Radar Hypothesis Formulas

Radar entries must avoid generic fluff ("is this tested?"). Each is an **open question** anchored to a specific symbol, line range, or failure mode in the diff — a hypothesis for the reviewer to verify against the real code, never a conclusion.

### Question Categories & Examples

#### A. Invariants & Boundary Conditions
- *"In `calculate_fee` (`billing.ts:42-48`), what happens if `total_cents` is zero or negative?"*
- *"`items` appears to be assumed non-empty at `cart.ts:89`. Is an empty slice guarded upstream?"*

#### B. Error Handling & Fallbacks
- *"If `fetchUserPreferences` times out (`prefs.ts:112`), does the fallback return cached data or propagate an uncaught rejection?"*
- *"Are transactional rollback semantics guaranteed if the second insert fails (`ledger.ts:64`)?"*

#### C. Concurrency & Re-entrancy
- *"Is `mutex.Lock()` acquired before checking `is_active` (`worker.ts:130`), or is there a race window?"*
- *"Could simultaneous webhook callbacks trigger duplicate ledger records (`hooks.ts:75-82`)?"*

#### D. Backward Compatibility & Migration
- *"`status` was renamed to `state` (`api.ts:15`). Are older mobile clients still sending `status`?"*
- *"Does the migration in Layer 1 require lock acquisition on a heavily written table?"*

---

## 3. Neutral Investigation Protocol (Emergent Q&A)

When the reviewer asks an ad-hoc question during standby, investigate without a thumb on the scale.

### 3a. Investigation Checklist (primary agent, or dispatch basis)

1. Restate the question as two competing hypotheses (e.g., "protected against duplicates" vs. "a duplicate path exists").
2. Read the target code and its real callers — prefer graph tools (`trace_path`, `search_graph`) when available, grep otherwise.
3. Collect concrete evidence for **both** sides: `file:line` references and actual execution paths.
4. Report which way the evidence points, with the evidence. If unresolved, say so and name what would resolve it.

### 3b. Subagent Dispatch Template (when subagents are supported)

> Investigate a code-review question in <repo>. Context: branch `<branch>` vs base `<base>`; inspect the diff with `git diff <base>...HEAD`. Target symbols/lines: <symbols, file:line ranges>.
>
> Question under review: <user's question>.
>
> Evaluate BOTH hypotheses: (1) the code handles this correctly — identify the protections that exist and where they live; (2) the code can fail here — identify concrete edge cases, callers, or execution paths that defeat those protections. Do not try to confirm a predetermined answer. Gather caller traces and report evidence as `file:line` references. End with: evidence summary, which hypothesis the evidence supports, and any remaining uncertainty.

When subagents are unavailable, the primary agent runs the identical investigation itself — the both-hypotheses mandate applies either way.

### 3c. Concern Log Format

Keep a running internal log during standby; it feeds on-demand output only, never unsolicited recaps:

```
- [Layer N / file:line] Concern or open question — status: open | resolved | accepted-risk
```

Compile the log into a PR-ready markdown block only on explicit user request.
