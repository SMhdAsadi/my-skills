---
name: review-walkthrough
description: "Generates an architectural reading plan for a branch diff, then stays on standby as an on-demand review co-pilot. Use when the user wants to walk through changes, review a branch, examine a diff, or asks for a guided code review."
license: MIT
compatibility: "git >= 2.0"
metadata:
  author: SMhd
  version: "2.0.0"
  tags:
    - git
    - code-review
    - walkthrough
    - developer-tools
---

# Review Walkthrough

An **Architectural Reading Plan Generator and On-Demand Review Co-Pilot** designed to maximize the depth and speed of **human** code reviews.

Instead of gating the review behind turn-by-turn chat steps, this skill analyzes the branch diff once, writes a topologically ordered **reading plan** to an ephemeral markdown artifact, and then stands by: the human reviews at their own pace in their native IDE or diff viewer, and asks the agent questions only when they hit ambiguities, tricky logic, or suspected bugs. Consult [`references/review-rubric.md`](references/review-rubric.md) for layering heuristics, risk-hypothesis formulas, and investigation templates.

---

## Process

### 1. Pin the Base & Inspect the Diff

1. Determine the base reference (`main`, `master`, `develop`, or a specific branch/commit named by the user).
   - If unspecified, resolve it silently: check for an upstream tracking branch, then fall back to `main`, then `master`, then `develop`, in that order.
   - Only ask the user if none of these resolve to a valid ref. Otherwise state the assumed base in the chat briefing (Section 5) rather than interrupting up front.
2. Record the current HEAD commit: `git rev-parse HEAD`. This is the plan's pinned commit — see Section 6 for staleness handling.
3. Inspect the diff and commit history:
   ```bash
   git rev-parse <base>
   git log <base>..HEAD --oneline
   git diff <base>...HEAD --stat
   ```
4. Check that the diff is non-empty. If empty or invalid, report this immediately.
5. Gauge diff size (files changed, lines changed). This drives the split assessment (Section 2) and the plan's scale (Section 4).
6. Read the changed files and hunk details to understand the core mechanisms before generating the plan.

---

### 2. Split Assessment (Root Cause First)

Large diffs are the primary driver of review fatigue and missed defects. If the diff exceeds the large-diff threshold (rough guide: >15 files or >800 changed lines):

- Open the plan with an explicit **Split Recommendation**: state that splitting the change into smaller, independently reviewable units is the superior fix, and suggest a concrete split boundary when one is visible (e.g., schema migration first, then domain logic, then consumers).
- Still generate the full plan — reviewers frequently inherit diffs they cannot split (AI-authored branches, legacy changes, external PRs).

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

### 4. Generate the Architectural Reading Plan

Write the complete plan as a single markdown artifact. **One shot** — do not page it through chat.

#### 4a. Resolve the Storage Path (Ephemeral, Never Git-Tracked)

The plan is a disposable draft. It must never be committed and never live in `.git/`. Resolve the path using this fallback hierarchy:

1. **Agent harness storage (first priority):** the harness's dedicated artifact/scratch directory, if the environment provides one.
2. **Repository temp directory:** a local scratch directory (e.g., `tmp/`, `.tmp/`), but only after verifying with `git check-ignore` that it is excluded from tracking.
3. **System temp directory (final fallback):** e.g., `/tmp/review-plan-<branch>-<timestamp>.md` on Unix.

Report the resolved absolute path to the user so they can open it directly in their editor.

#### 4b. Plan Contents

1. **Advisory header:** one line stating the plan is agent-generated orientation material — hypotheses to verify against the real code, not verified judgments.
2. **Ref metadata:** pinned base ref, pinned HEAD commit hash, scope stats (files, +/- lines), and blast radius (Tier-1 grounded, or explicitly labeled heuristic — see Section 3).
3. **Split recommendation** (only when Section 2 applies).
4. **Executive context & invariant delta:** 2–3 sentences on overarching intent, plus which system invariants appear modified vs. preserved. Phrase preserved invariants as claims to verify ("`X` appears untouched — confirm at `file:line`"), not assurances.
5. **Topological reading itinerary:** ordered foundation-to-leaf layers with interactive checkboxes, clickable `file:line` links, and a one-sentence rationale per slice:
   - `Layer 1: Schemas, Types, and Migrations`
   - `Layer 2: Core Domain Logic & State Machines`
   - `Layer 3: Side Effects, I/O, API Endpoints & Workers`
   - `Layer 4: Consumers, Controllers & UI Components`
   - `Layer 5: Tests, Tooling & Infrastructure`
6. **Reviewer risk radar:** 3–5 concrete, line-anchored hypotheses (concurrency, boundary conditions, rollback semantics, backward compatibility), phrased as open questions — never conclusions.
7. **Verification & testing blind spots:** what the automated tests cover vs. what remains untested or needs manual verification.
8. **Lower-risk skimmable files:** boilerplate/generated files the reviewer can likely skim. Each entry must carry a rationale ("generated by `<tool>`", "lockfile churn only") and a verification pointer ("confirm via `git diff --stat`", "check the header comment"). Never call any file unconditionally safe.

**Anchoring rule:** every substantive claim in the plan must reference a verifiable `file:line`. If a mechanism cannot be anchored, flag it explicitly as unverified or omit it.

**Scaling rule:** keep the plan proportional to the diff. A small diff (<=5 files, <=300 lines) gets a compact plan: short context, one merged itinerary list, 2–3 risk hypotheses, and blind spots only if non-obvious. Do not generate ceremony the diff doesn't warrant.

**Do not include:** paged diff hunks, lint/formatting nits, generic checklist questions ("is this secure?"), or pass/fail approval badges.

---

### 5. Chat Briefing

After writing the plan, reply concisely:

- The absolute path to the plan artifact (so the user can open it side-by-side with their IDE/diff viewer).
- The base ref used (and how it was resolved, if non-obvious) and overall diff size.
- The split recommendation, if one was issued.
- The top 2–3 risks from the radar, in one line each.

Then stop. Do not walk through steps, do not ask the user to type `next`.

---

### 6. Passive Standby & Emergent Q&A (Turns 2..N)

The human drives pacing. The agent answers questions and otherwise stays out of the way.

- **Staleness check:** if the user mentions pushing, amending, or rebasing — or a long gap has passed — re-run `git rev-parse HEAD` and compare to the pinned commit. If it changed, flag it and offer to re-diff and regenerate the plan rather than answering against stale content.
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
