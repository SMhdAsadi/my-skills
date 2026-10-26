# MR / PR Comment Triage (`mr-comment-triage`)

[![Agent Skills Standard](https://img.shields.io/badge/Agent%20Skills-Standard-0A84FF?style=flat-square)](https://agentskills.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](../../LICENSE)

Turns an MR full of open review threads into **one batch plan you approve or reject item by item** — then applies the approved fixes, runs the checks, and drafts the replies.

---

## The Problem

An MR comes back with nine comments. Three are real bugs, two are the same bug reported twice, one is a bot restating a CI failure, two are valid but out of scope, and one is a question that needs a product decision. The usual agent behaviour is worse than doing it by hand:

1. **Blind compliance** — every comment is treated as an order, so the code gets bent around suggestions that were wrong to begin with.
2. **Blind deference** — the agent assumes the reviewer read more of the codebase than it did, and never checks the claim.
3. **Turn-by-turn churn** — one comment at a time means nine round trips, nine diffs, and no view of the whole plan.
4. **Lost state** — by the fourth turn nobody remembers which items were accepted, which were pushed back, and which reply was already drafted.

## The Solution

`mr-comment-triage` reads every open thread once, re-anchors each comment against the actual code, and returns a verdict per item: `ACCEPT`, `ALTERNATIVE`, `PUSH_BACK`, `DEFER`, `ALREADY_FIXED`, or `CLARIFY`. You see the whole plan in one table, approve what you agree with, override what you don't, and only then does anything get written.

Nothing mutates before approval. Replies stay drafts until you explicitly post them.

---

## Key Features

- **Comments are hypotheses** — each claim is verified against the current tree before a verdict is formed, with `path:line` evidence rather than agreement.
- **Six verdicts, not two** — separates "right concern, wrong fix" (`ALTERNATIVE`) from "wrong premise" (`PUSH_BACK`), and gives out-of-scope and needs-a-decision their own lanes (`DEFER`, `CLARIFY`) instead of smuggling them into the diff.
- **One batch gate** — approve `all`, `1, 3`, `skip 2`, or `2=ACCEPT`. `all` never includes items that need a human decision.
- **Provider-normalized** — GitHub via GraphQL `reviewThreads`, GitLab via the discussions REST API, including self-hosted instances. System notes, MR-level threads, deleted-line anchors, and outdated comments are handled once, centrally.
- **Staleness-aware** — a comment written against an older diff version is flagged, then re-anchored at HEAD instead of being judged against a line that no longer exists.
- **Duplicate collapsing** — three reviewers raising one issue is one item with three thread ids, not three approvals for the same edit.
- **Bots judged by content** — a bot comment that encodes a checkable claim is triaged like any other; a status ping is not.
- **State that survives the session** — `mr-triage.json` in a gitignored scratch directory, never in the repo, so a long approval-and-execution loop never depends on chat scrollback.
- **Two gates, not one** — editing code and replying on a shared MR are different blast radii. Posting requires its own explicit flag, and resolving someone else's thread requires another.
- **Deterministic where it matters** — fetching, state transitions, and approval parsing are scripts, not vibes.

---

## How to Trigger

- *"Handle the review comments on this MR"*
- *"Triage the PR feedback and tell me which ones you'd push back on"*
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
collect ──▶ re-anchor ──▶ verify ──▶ propose ──▶ [gate 1] ──▶ apply ──▶ draft ──▶ [gate 2]
 read-only                                    approval              writes        post
```

1. **Collect** — unresolved threads from GitHub or GitLab, normalized into one model.
2. **Re-anchor** — inline, file-level, and MR-level comments are distinguished; stale anchors are re-resolved at HEAD.
3. **Verify** — read the hunk, then the file, then the callers or tests the claim depends on.
4. **Propose** — verdicts plus severity, written to the state file and rendered as a table.
5. **Gate 1** — you approve a subset; the script restates the resulting plan before anything changes.
6. **Apply** — one item at a time, blocking issues first, targeted checks per item and the full suite once at the end.
7. **Gate 2** — replies are drafted for every thread; posting and resolving are separate explicit flags.

---

## State File

Resolution order, first match wins:

1. `$MR_TRIAGE_DIR`
2. an existing gitignored directory among `.tmp/`, `scratch/`, `.scratch/`
3. `.tmp/`, created only if git already ignores it
4. `$TMPDIR/mr-comment-triage/`

It is never written to a tracked path. The filename is stable per target (`github-cli-cli-14783.json`), so re-fetching resumes the existing plan instead of starting over. If HEAD moved between fetches, the state records it and warns that verdicts need re-verification.

Schema and lifecycle: [`references/thread-model.md`](references/thread-model.md).

---

## Requirements

| Tool | Version | Needed for |
|---|---|---|
| `git` | 2.0+ | Everything |
| `gh` | 2.40+ | GitHub PRs |
| `glab` | 1.40+ | GitLab MRs, including self-hosted |
| Python | 3.10+ | The three helper scripts (stdlib only) |

No `gh`/`glab`? The skill degrades to a pasted thread dump and still runs the verification and planning phases.

---

## Limitations

- One MR per run; it is not a queue processor.
- Beyond ~15 open threads it triages the top 10 by severity and reports what it skipped.
- It will not resolve threads it did not open unless you ask for that thread specifically.
- Verdicts are opinions with evidence attached. The gate exists because the evidence can still be wrong.

## Related Skills

| Skill | Relationship |
|---|---|
| [`review-walkthrough`](../review-walkthrough/) | Before review: understand your own diff. |
