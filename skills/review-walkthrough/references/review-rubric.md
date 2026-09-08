# Review Walkthrough Rubric & Reference

Supplementary guide and reference heuristics for executing the `review-walkthrough` skill.

---

## 1. Topological Reading Order (Foundation to Leaf)

Always sequence diff hunks according to architectural dependency. Leaf nodes cannot be properly evaluated without first understanding the underlying contracts and domain rules.

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
| **3** | **Side Effects & I/O** | `controllers/`, `api/`, HTTP endpoints, DB queries, RPC | Verifies how the system talks to external networks, disk, or databases. |
| **4** | **Presentation & UI** | `components/`, views, styling, templates | Validates user experience, state binding, and visual handling of loading/error states. |
| **5** | **Tests & Tooling** | `*.test.ts`, `*_test.go`, configs, CI workflows | Verifies test coverage, assertions, and build setup against the changes reviewed in steps 1–4. |

---

## 2. Reviewer Spotlight Question Formulas

Spotlight questions must avoid generic fluff ("is this tested?"). Instead, formulate questions that anchor to specific symbols, lines, and potential failure modes in the diff.

### Question Categories & Examples

#### A. Invariants & Boundary Conditions
- *"In `calculate_fee` (lines 42–48), what happens if `total_cents` is zero or negative?"*
- *"Notice that `items` is assumed non-empty at line 89. Is an empty slice guarded upstream?"*

#### B. Error Handling & Fallbacks
- *"If `fetchUserPreferences` times out at line 112, does the fallback return cached data or propagate an uncaught rejection?"*
- *"Are transactional rollback semantics guaranteed if the second insert fails on line 64?"*

#### C. Concurrency & Re-entrancy
- *"Is `mutex.Lock()` acquired before checking `is_active` at line 130, or is there a race window?"*
- *"Could multiple simultaneous webhook callbacks trigger duplicate ledger records at lines 75–82?"*

#### D. Backward Compatibility & Migration
- *"The payload field `status` was renamed to `state` on line 15. Are older mobile clients still sending `status`?"*
- *"Does the database migration in Step 1 require lock acquisition on a heavily written table?"*

---

## 3. Session Pacing & Signals

| User Signal | Agent Action |
| :--- | :--- |
| `next` or `looks good` | Acknowledge, mark current step as reviewed, and present the next step immediately. |
| `skip` | Mark step as skipped in the sign-off notes and proceed to the next logical step. |
| `jump <step number>` | Switch immediately to the requested step. |
| `re-diff` | Re-run `git rev-parse HEAD` and refresh diff hunks from the current step onward. |
| Specific question/critique | Pause progression. Investigate codebase context, analyze the concern, and propose fixes or clarify intent. |
