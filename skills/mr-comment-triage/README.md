# MR Comment Triage (`mr-comment-triage`)

[![Agent Skills Standard](https://img.shields.io/badge/Agent%20Skills-Standard-0A84FF?style=flat-square)](https://agentskills.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](../../LICENSE)

Turns a GitLab MR full of open review threads into **one batch plan you approve or reject in one gate** — then applies the approved fixes, runs the checks, and posts the replies as a second batch.

---

## The Problem

An MR comes back with nine comments. Three are real bugs, two are the same bug reported twice, one is a bot restating a CI failure, two are valid but out of scope, and one is a question that needs a product decision. The usual agent behaviour is worse than doing it by hand:

1. **Blind compliance** — every comment is treated as an order, so the code gets bent around suggestions that were wrong to begin with.
2. **Blind deference** — the agent assumes the reviewer read more of the codebase than it did, and never checks the claim.
3. **Turn-by-turn churn** — one comment at a time means nine round trips, nine diffs, and no view of the whole plan.
4. **Lost state** — by the fourth turn nobody remembers which items were accepted, which were pushed back, and which reply was already drafted.

## The Solution

`mr-comment-triage` reads every open thread once, re-anchors each comment against the actual code, and returns a verdict per item: `ACCEPT`, `ALTERNATIVE`, `PUSH_BACK`, `DEFER`, `ALREADY_FIXED`, or `CLARIFY`. You see the whole plan in one table, approve what you agree with in one expression, override what you don't, and only then does anything get written. Replies are previewed as one batch and posted with one explicit flag.

Nothing mutates before approval, except that a plan made only of reply-only verdicts can skip straight to the reply gate. Replies stay drafts until you explicitly post them.

---

## Key Features

- **GitLab only** — discussions come from the GitLab REST API through `glab`, including self-hosted instances. There is no second provider, and `glab` is required.
- **Comments are hypotheses** — each claim is verified against the current tree before a verdict is formed, with `path:line` evidence rather than agreement. Every citation is checked to exist at HEAD.
- **Six verdicts, not two** — separates "right concern, wrong fix" (`ALTERNATIVE`) from "wrong premise" (`PUSH_BACK`), and gives out-of-scope and needs-a-decision their own lanes (`DEFER`, `CLARIFY`) instead of smuggling them into the diff.
- **Two batched gates** — one `plan --from` writes the whole plan, one `approve` decides it; one `post_reply --all-approved` previews every reply, one `--post` sends the batch. Six calls total, independent of thread count.
- **Reply-only fast path** — a plan with no code edits skips Gate 1 entirely: preview and post are the only gate.
- **An enforced state machine** — only `approve` can approve, only the execute phase can mark applied or verified, and only the reply phase can mark a thread posted or resolved. Editing the verdict, threads, action, or evidence invalidates the approval.
- **Per-thread journal** — each reply records its exact body, timestamp, URL, and resolution state before the next thread starts, so a partial failure resumes without double-posting.
- **Staleness-aware** — a comment written against an older diff version is flagged, then re-anchored at HEAD instead of being judged against a line that no longer exists.
- **Renames and deletions** — anchors carry `oldPath` and a `new`/`old` side, so a deleted-line comment is read against the old file.
- **Duplicate collapsing** — three reviewers raising one issue is one item with three thread ids, not three approvals for the same edit.
- **Bots judged by content** — a bot comment that encodes a checkable claim is triaged like any other; a status ping is not.
- **State that survives the session** — `gitlab-<repo-slug>-<number>.json` in a gitignored scratch directory, never in the repo, so a long approval-and-execution loop never depends on chat scrollback.
- **Re-fetch reconciliation** — re-fetching keeps items and appends events, marks vanished threads as orphans, and refuses to post to them.
- **Deterministic where it matters** — fetching, state transitions, approval parsing, and evidence checks are scripts, not vibes.

---

## How to Trigger

- *"Handle the review comments on this MR"*
- *"Triage the MR feedback and tell me which ones you'd push back on"*
- *"Work through the open threads on !2340"*
- *"Which of these review comments are actually valid?"*

## Quickstart

```bash
npx skills add SMhdAsadi/my-skills@mr-comment-triage
```

Then, inside the repository you are reviewing:

```bash
python3 scripts/fetch_threads.py
python3 scripts/triage_state.py threads
```

The agent takes it from there. If you want to drive it manually, the full command surface is in [`SKILL.md`](SKILL.md).

---

## How It Works

```
collect ─▶ re-anchor ─▶ verify ─▶ plan ─▶ [gate 1: approve] ─▶ preflight ─▶ apply ─▶ draft ─▶ [gate 2: post]
 read-only                         one batch      one decision      clean tree             one batch
```

1. **Collect** — unresolved threads from GitLab, normalized into one model and one state file.
2. **Re-anchor** — inline, file-level, and MR-level comments are distinguished; side and old path are derived; stale anchors are re-resolved at HEAD.
3. **Verify** — read the hunk, then the file, then the callers or tests the claim depends on.
4. **Plan** — one JSON document with verdicts, severity, evidence, actions, and draft replies; validated atomically before writing.
5. **Gate 1** — one `approve` expression covers the batch. `CLARIFY` and `DEFER` are held back, and the script restates what was approved, held, skipped, and un-approved.
6. **Preflight** — refuse a dirty tree, then apply one item at a time, blocking issues first, with targeted checks per item and the full suite once at the end.
7. **Gate 2** — one preview of every reply and its resolve decision, then one `--post`. Resolving your own threads is a separate flag; closing someone else's needs an audited override.

A plan containing only reply-only verdicts skips Gate 1 and goes directly from plan to the Gate 2 preview and post.

---

## State File

Resolution order, first match wins:

1. `$MR_TRIAGE_DIR`, accepted only when it is outside the repository or gitignored inside it
2. `mr-comment-triage/` inside an existing gitignored `tmp/`, `.tmp/`, `scratch/`, or `.scratch/`
3. `.tmp/mr-comment-triage/`, created only if git already ignores `.tmp/`
4. `$TMPDIR/mr-comment-triage/`

It is never written to a tracked path. The filename is stable per target:

```
gitlab-<repo-slug>-<number>.json
gitlab-virasty-client-reactnative-2355.json
```

Re-fetching resumes the existing plan instead of starting over: items and the event log survive, vanished threads become orphans, and a moved HEAD adds a warning that verdicts need re-verification. Schema version 2 and lifecycle: [`references/thread-model.md`](references/thread-model.md).

---

## Requirements

| Tool | Version | Needed for |
|---|---|---|
| `git` | >= 2.0 | Everything |
| `glab` | >= 1.40 | MR collection, replies, and resolution, including self-hosted GitLab |
| Python | 3.10+ | The three helper scripts (stdlib only) |

No `glab`? Install and authenticate it first; thread collection has no other transport.

---

## Limitations

- One MR per run; it is not a queue processor.
- Very large MRs are not truncated or silently capped. The agent should ask before planning an oversized batch; every thread in the plan costs a row to review, and the batch reply costs one call per thread.
- It will not resolve threads it did not open unless you deliberately pass `--resolve-other`; that override is recorded in the event log.
- Verdicts are opinions with evidence attached. The gate exists because the evidence can still be wrong.
- Existing state from an older schema is rejected, not migrated; re-fetch to rebuild it.

## Related Skills

| Skill | Relationship |
|---|---|
| [`review-walkthrough`](../review-walkthrough/) | Before review: understand your own diff. |
