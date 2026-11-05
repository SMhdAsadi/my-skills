# To GitLab MR Comments (`to-mr-comments`)

[![Agent Skills Standard](https://img.shields.io/badge/Agent%20Skills-Standard-0A84FF?style=flat-square)](https://agentskills.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](../../LICENSE)

Turns a review conversation or a branch diff into **a handful of comments that are wanted, true, anchored, and safe to post** — preview them, approve them, then post them to the merge request.

---

## The Problem

You finished reviewing a branch and the findings are scattered across chat: three real issues, one question, two preferences, and a vague worry about "consistency across all players." The usual agent behavior is worse than writing them by hand:

1. **Everything becomes a comment.** A preference and a data-loss bug get the same confident tone.
2. **Nothing is checked.** The line moved two commits ago, or was never in the diff, and GitLab rejects the note after you paste it.
3. **No evidence.** "This could be slow" is unfalsifiable; the author cannot tell whether to act.
4. **Essays.** A comment that needs three headings is a document, not a review note.
5. **Nothing is remembered.** Turn three asks "what did we drop and why?", and the answer is gone.

## The Solution

`to-mr-comments` keeps a JSON state file as the source of truth. Each finding is classified (`agreed`, `open`, `rejected`, `hypothesis`), tested against an explicit selection policy, and only then added — which validates the evidence, counts the words, checks the budget, and verifies the anchor against `git diff <base>...HEAD`. A finding that does not pass is recorded in `dropped[]` with a reason instead of quietly disappearing.

The result is a deterministic `mr-comments.md` with one copy box per comment. Posting is a separate, single-gate step: preview the exact payloads, approve explicitly, then `--post`.

---

## Key Features

- **Comment budget** — aim for 5, hard cap 10. `--force` is recorded so a later reader knows the cap was overridden.
- **Evidence is mandatory** — a `path:line`, a backticked command, a URL, or a measurement with units. "Looks slow" is rejected by the script.
- **Anchors verified at HEAD** — inline lines and their whole `line..endLine` span must fall inside one diff hunk and inside the file; a hash catches text drift; a moved line is `moved`, never silently accepted.
- **Three anchor kinds** — `inline`, `file`, and `mr`, so a comment about a deleted, binary, or renamed file still has a home. Renames record the pre-rename path and send both `old_path` and `new_path`.
- **Auditable drops** — `drop C3 --reason "..."` retires a comment, `drop --claim "..." --reason "..."` records a rejected candidate before it ever became one. "No comment" stays explainable.
- **Strict decision matrix** — `rejected` and `hypothesis` never become comments, `low` confidence is always dropped, and `open` is only allowed on a `question`.
- **Status lifecycle** — `pending → approved → posted`, with `dropped` as an auditable side exit. Editing an approved comment resets it to pending.
- **Deterministic renderer** — inline and summary modes, collision-safe fences, severity ordering, and a footer that states exactly how many anchors are verified at which SHA.
- **Deduplication** — an existing inline or MR-level note with a 0.9 text similarity is skipped, not repeated; edits are checked too.
- **GitLab-only, on purpose** — `glab api` is the only transport. Non-GitLab hosts are rejected before any comment is generated.
- **State that survives the session** — `mr-comments-<project>-<iid>.json` in a gitignored scratch directory, never a tracked path. `add` and `update` refuse a moved HEAD until `verify` resynchronises the state.

---

## How to Trigger

- *"Turn these findings into MR comments."*
- *"Write review comments for this branch."*
- *"Post a review on !2340 — keep it to five comments."*
- *"Why did we drop the LTR comment?"*

## Quickstart

```bash
npx skills add SMhdAsadi/my-skills@to-mr-comments
```

Then, inside the repository you are reviewing:

```bash
python3 scripts/comments.py init --from-mr
python3 scripts/comments.py list
python3 scripts/comments.py render
```

The agent takes it from there. The full command surface is in [`SKILL.md`](SKILL.md).

---

## How It Works

```
harvest ──▶ select ──▶ certify ──▶ emit ──▶ [approve] ──▶ [post]
 conversa     policy     verify      md       pending       comments
```

1. **Harvest** — the conversation first, an existing `review-concerns.json` from a `Review Walkthrough` session second, the diff last. Every candidate gets a decision and a short provenance quote.
2. **Select** — keep only findings with a reachable consequence; write the rest to `dropped[]` with `comments.py drop --claim`.
3. **Certify** — re-read the line at HEAD, confirm it is inside the diff, write the evidence, then `comments.py add` (which validates and verifies) and `comments.py verify`.
4. **Emit** — render `mr-comments.md` and present the path, footer, dropped table, and copy blocks.
5. **Approve** — `comments.py approve` is the explicit gate; nothing is posted without it.
6. **Post** — `post_comments.py` previews the payloads, then `--post` creates the real comments.

---

## State File

Resolution order, first match wins:

1. `$MR_COMMENTS_DIR`
2. `to-mr-comments/` inside an existing gitignored `tmp/`, `.tmp/`, `scratch/`, or `.scratch/`
3. `.tmp/to-mr-comments/`, created only if git already ignores `.tmp/`
4. `$TMPDIR/to-mr-comments/`

Never written to a tracked path. The filename is stable per MR, so re-initialising resumes the existing plan instead of starting over. If HEAD moved, the state says so and posting refuses until `verify` is clean again.

Schema, lifecycle, and validation rules: [`references/comment-model.md`](references/comment-model.md).

---

## Requirements

| Tool | Version | Needed for |
|---|---|---|
| `git` | 2.0+ | Everything |
| Python | 3.10+ | The four helper scripts (stdlib only) |
| `glab` | 1.40+ | Posting comments, including self-hosted GitLab |

No `glab`? Generation and rendering still work; posting stops at the `.md`, and the copy blocks paste cleanly into the GitLab UI.

---

## Limitations

- GitLab only. GitHub is not supported.
- One MR per run.
- Multi-line `line_range` anchors are out of scope; the API anchor is one line while `endLine` is verified and display-only.
- Suggestions are capped at 5 replacement lines.
- It writes comments about code; it does not apply fixes. Run the fix in the same branch and re-verify.
- It does not reply to or resolve existing threads — that is [`mr-comment-triage`](../mr-comment-triage/).

## Related Skills

| Skill | Relationship |
|---|---|
| [`mr-comment-triage`](../mr-comment-triage/) | The other direction: consume existing review threads and answer them. |
| [`review-walkthrough`](../review-walkthrough/) | Before writing comments: understand your own diff. |
| [`better-persian`](../better-persian/) | Persian register and orthography for `lang=fa`. |
