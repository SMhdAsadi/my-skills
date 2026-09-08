---
name: review-walkthrough
description: "Interactive step-by-step code review companion. Builds a mental model of branch changes, maps an optimal dependency-ordered reading path, and guides the human reviewer through the diff chunk by chunk. Use when the user wants to walk through changes, review a branch step by step, or asks for a guided code review."
license: MIT
compatibility: "git >= 2.0"
metadata:
  author: SMhd
  tags:
    - git
    - code-review
    - walkthrough
    - developer-tools
---

# Review Walkthrough

An interactive, step-by-step code review companion designed to maximize the depth and speed of **human** code reviews.

Instead of dumping static lints or evaluating pass/fail criteria, this skill acts as a tour guide: it pre-digests the diff, establishes the mental model, determines the optimal reading order, and guides the human reviewer through one logical chunk at a time. Consult [`references/review-rubric.md`](references/review-rubric.md) for architectural ordering heuristics and spotlight question templates.

---

## Process

### 1. Pin the Base & Inspect the Diff

1. Determine the base reference (`main`, `master`, `develop`, or a specific branch/commit named by the user).
   - If unspecified, try to resolve it silently: check for an upstream tracking branch, then fall back to `main`, then `master`, then `develop`, in that order.
   - Only ask the user if none of these resolve to a valid ref. Otherwise state the assumed base in the Executive Summary (Phase 1) rather than interrupting up front — the goal is to reach Step 1 fast.
2. Record the current HEAD commit: `git rev-parse HEAD`. This is the walkthrough's pinned commit — see Section 5 for why.
3. Inspect the diff and commit history:
   ```bash
   git rev-parse <base>
   git log <base>..HEAD --oneline
   git diff <base>...HEAD --stat
   ```
4. Check that the diff is non-empty. If empty or invalid, report this immediately.
5. Gauge diff size (files changed, lines changed) — this determines step count in Phase 2.
6. Read the changed files and hunk details to understand the core mechanisms before generating the plan.

---

### 2. Phase 1: Mental Model & Overview

Produce a concise orientation briefing:

1. **Base & Scope Note:** Which base ref was used (and how it was resolved, if not obvious) and the overall diff size. If the diff is large (rough guide: >15 files or >800 changed lines), say so explicitly and note that the roadmap below will use more steps than usual to keep each one reviewable.
2. **Executive Summary:** 2–3 sentences explaining the overarching intent and problem being solved.
3. **System Footprint:** Group modified files into logical architectural layers (e.g., Contracts & Schemas, Core Domain Logic, Services & Adapters, Presentation & UI, Tests & Infrastructure).
4. **Risk Radar:** Identify 2–3 high-leverage areas most sensitive to regressions, breaking changes, or subtle edge cases.

---

### 3. Phase 2: The Review Roadmap

Design an optimal **reading path** through the changes.

**Rules for the Roadmap:**
- Order changes from **foundation to leaf** (never alphabetical):
  1. Data schemas, types, and domain models
  2. Core business logic, domain services, state transitions
  3. Side effects, I/O, API endpoints, external integrations
  4. Consumers, UI components, presentation layers
  5. Tests, configuration, and documentation
- Break the diff into logical steps, scaled to size:
  - Typical diff: 3–5 steps.
  - Large diff (per the threshold above): 6–8 steps, keeping each step to a reviewable slice rather than compressing everything to fit an arbitrary cap. Never sacrifice "one coherent idea per step" just to stay under 5.
- For each step, list the step number, title, and the files it covers.

---

### 4. Phase 3: Interactive Turn-by-Turn Walkthrough

Immediately present **Step 1 only**:

1. **Step Header:** Step number, descriptive title, and file paths.
2. **Intent & Mechanism:** What this specific slice does and why it was implemented this way.
3. **Key Hunks:** Show the actual diff hunk (trimmed to the relevant lines, not the whole file) rather than paraphrasing it — the reviewer's eyes should land on real code. A short explanation can frame the hunk, but it supplements the code, it doesn't replace it.
4. **Reviewer Spotlight:** 2–3 targeted questions or edge cases, each anchored to a specific line range, function, or variable name in *this* hunk. Avoid generic categories ("check for missing validation") unless tied to a concrete spot in the diff — spotlight questions should read as "did X handle Y at line Z", not a boilerplate checklist.
5. **Prompt for Pacing:** End the turn asking the reviewer for their observations, questions, or a signal (`next`, `skip`, or jump to another step) before proceeding.

---

### 5. Subsequent Turns

In each subsequent turn:

- **Staleness check:** Before advancing, if it's been a while or the user mentions pushing/amending, re-run `git rev-parse HEAD` and compare to the pinned commit from Section 1. If it changed, flag this to the user and offer to re-diff and regenerate the roadmap from the current step forward, rather than silently continuing on stale content.
- If the user has comments, doubts, or questions about the current step, dig in, investigate the code, and discuss. Log any substantive concern, todo, or open question raised — don't rely on reconstructing it from scrollback later.
- Once the user signals `next` (or confirms readiness), move to the next step using the exact same structure (Header, Intent, Key Hunks, Reviewer Spotlight).
- If the user asks to see all remaining steps at once, accommodate them.
- When all steps are finished, provide a short **Sign-off Recap** built from the logged concerns/todos/agreements per step — not a fresh summary written from memory of the conversation.