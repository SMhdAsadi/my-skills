---
name: to-mr-comments
description: "Turns a review conversation or branch diff into a small set of verified, copy-pasteable GitLab merge request comments. Re-checks anchors at HEAD, merges duplicates, enforces a budget, and posts them to the merge request after explicit approval. Use when the user wants to write MR comments, turn review findings into comments, or post a review."
license: MIT
compatibility: "git >= 2.0; glab >= 1.40 (only for posting)"
metadata:
  author: SMhd
  version: "2.2.0"
  tags: [git, gitlab, code-review, merge-requests, developer-tools]
---

# To GitLab MR Comments

Turn a review conversation or a branch diff into a handful of comments that are wanted, true, anchored, sized, and safe to post. A comment is a small artifact: it names one change, cites one fact, and fits in a thread without becoming an essay.

Five invariants:

1. **A comment is a claim.** Without citable evidence it is not emitted.
2. **Anchors are verified at HEAD** and must fall inside the MR diff. A moved line is re-anchored or dropped, never guessed.
3. **Nothing is posted without explicit approval; there is no draft stage.** A preview shows the exact payloads, and only `--post` sends them.
4. **Comments reflect the user's decisions,** not the agent's opinions. `open` becomes a question; `hypothesis` never becomes a comment.
5. **Never copy credentials, tokens, customer data, internal URLs, or private metrics** into a comment, the evidence, or the state file.

---

## 1. Scope — GitLab only

One MR per run. If the target is not a confirmed GitLab instance, stop.

Resolve the target in this order:

1. A URL, project, or IID the user gave.
2. The current branch's open MR.
3. Ask.

Resolve the base: the upstream branch, then `main`, `master`, `develop`; only ask if none resolve. Record the full HEAD SHA at init.

**Platform check (hard stop):** confirm the host with `glab auth status --hostname <host>` or `glab api --hostname <host> version`. If `glab` is unavailable, require explicit `--host` and `--project` as the user's assertion. Otherwise:

> `to-mr-comments` is GitLab-only. The remote `<host>` is not a confirmed GitLab instance. Stopping without generating comments.

Distinguish "not GitLab" (stop) from "GitLab but `glab` missing" (generate offline; posting unavailable).

```bash
python3 scripts/comments.py init --from-mr            # reads the MR through glab api
python3 scripts/comments.py init --project team/api --iid 2340 \
  --base main --host gitlab.example.com --offline     # no network
```

State lives in a skill-owned subdirectory of a gitignored scratch dir: `$MR_COMMENTS_DIR`, else `to-mr-comments/` inside the first existing ignored `tmp/`, `.tmp/`, `scratch/`, or `.scratch/`, else system temp. Never a tracked path. `init` prints the absolute path; say it out loud when the fallback is used.

## 2. Harvest

Sources, in order: the conversation, an existing `review-concerns.json`, then `git diff <base>...HEAD`.

A reviewer who just finished a `Review Walkthrough` session leaves `review-concerns.json` in the repository's scratch directory. When it exists, read it before the diff — it already holds `path`/`startLine` refs and investigated findings:

| Concern `status` | Becomes |
|---|---|
| `action-needed` | A comment candidate with `decision: agreed` |
| `open` | A `question` candidate with `decision: open` |
| `resolved` | A `dropped[]` entry via `comments.py drop --claim ... --reason ...` |
| `accepted-risk` | A `dropped[]` entry via `comments.py drop --claim ... --reason ...` |

Classify every candidate:

| Decision | Meaning | May become |
|---|---|---|
| `agreed` | The user endorsed it. | `blocker`, `suggestion`, or any type |
| `open` | Unresolved question or trade-off. | `question` only |
| `rejected` | Considered and declined. | Nothing; record it with `drop --claim` |
| `hypothesis` | A hunch without evidence. | Nothing; record it with `drop --claim` |

`add` and `update` refuse `rejected` and `hypothesis` decisions, `low` confidence on every type, and `open` on anything but `question`. The script points at the `drop --claim` form when a candidate cannot become a comment.

Quote the user in `source.quote` — one short line. It is provenance for you and is **never rendered**.

## 3. Select

Keep a candidate only if it passes at least one:

1. Prevents a reachable defect: crash, data loss, race, wrong output.
2. Breaks a stated contract or invariant.
3. Leaves changed behavior untested in a way that matters.
4. Creates unbounded cost: per-frame work, N+1, leak, retry storm.
5. The user explicitly asked for it.

Reject if any:

- Style-only and already covered by the formatter or linter.
- A preference with no stated consequence.
- Requires an unbounded audit the diff cannot satisfy.
- Already raised and resolved in the thread.
- No citable evidence.

Then dedupe by root cause or symbol, merge nits into one comment, aim for 5 and never exceed 10. Write every rejected candidate to `dropped[]` with a reason: that is how "no comment" stays auditable. A run that emits nothing is a successful run.

```bash
python3 scripts/comments.py drop --claim "Uniform LTR enforcement across all players" \
  --reason "unbounded audit; no anchor" --source conversation
```

`drop` takes either an existing id (`drop C3 --reason "..."`) or a pre-certification candidate (`--claim`, `--reason`, optional `--source`), never both.

## 4. Certify

For each survivor:

1. Re-read the target file at HEAD. Read the line, not the diff summary.
2. Confirm the line — and the whole `line..endLine` span — is inside one hunk of `git diff -U3 <base>...HEAD`. A file deleted in the MR only carries a `file` anchor.
3. Write `evidence` as `path:line` plus the fact — a measurement, a command, a URL. "It looks slow" is not evidence.
4. Add it. The script validates and verifies in the same call:

```bash
python3 scripts/comments.py add \
  --type blocker --severity correctness \
  --title "Throttle UI-to-JS dispatch in panGesture.onChange" \
  --body-file /tmp/c1.md \
  --evidence "src/components/VSlider/VSlider.tsx:118 fires per pan tick; ~120 calls/s at 120Hz" \
  --source conversation --decision agreed --confidence high \
  --quote "we should throttle this" \
  --path src/components/VSlider/VSlider.tsx --line 118 --end-line 124
```

5. After the batch, run `python3 scripts/comments.py verify`.

A new comment enters as `pending`. Only `approve` makes it eligible for posting; nothing else moves it.

A renamed file is detected from the diff and stored as `anchor.oldPath`, so the discussion payload carries both `old_path` and `new_path` without a second git call at preview time.

`add` and `update` refuse when the repository's live HEAD differs from `mr.headSha`: run `verify` (or `init`) first, so every anchor in the state belongs to one commit. A clean `verify` writes the new HEAD into both `mr.headSha` and `mr.diffRefs.head_sha`.

If verification returns `moved`, `out-of-diff`, or `missing`: re-anchor with `update --reanchor` or `drop` it. Never post around a failed anchor. When a rebase both moves HEAD and takes a file out of the diff, `verify` cannot pass and therefore cannot resync HEAD — run `init` first, then demote the anchor.

## 5. Emit

```bash
python3 scripts/comments.py render
```

Write `mr-comments.md` next to the state file. Present:

- The absolute `.md` path.
- The footer (`5 comments · 5/5 anchors verified at abc1234 · 3 dropped · lang=en`).
- The dropped table.
- Every copy block in chat, each self-contained and paste-ready.

Inline mode puts `**Anchor:**` outside the box and a bold title inside it, with no `###` heading — GitLab renders one as a document heading in a thread. Summary mode uses `### <title>` and `**Target:**` inside the box for MR-level notes.

Nothing here touches the network: every comment is still `pending` until §6.

## 6. Post (optional)

Only when the user asks, and only one gate: preview → explicit approval → `--post`.

```bash
python3 scripts/post_comments.py                    # preview payloads; no network
python3 scripts/comments.py approve "all"           # or "1, 3" / "skip 2"
python3 scripts/post_comments.py --post             # create the real comments
python3 scripts/post_comments.py --post --one C2    # a single comment
```

Order: preview → show the payload list → ask → `approve` → `--post` → show a `#note_<id>` link per comment.

Inline and file anchors become discussions (`POST .../discussions` with `body` and `position`); MR-level comments become notes (`POST .../notes` with `body`). A renamed file carries `old_path` as well as `new_path`. `--post` refuses unless HEAD equals the state HEAD, every selected comment is `approved`, and every anchor verifies at that HEAD. A comment is also refused when a near-identical live note already exists — inline (`**Title**`) or MR-level (`### Title`) — and is skipped and reported, never repeated. Partial posting is limited to `--one`.

If `glab` is unavailable, stop at the `.md`. Do not attempt a workaround or a direct HTTP call.

## 7. Revise

Stable ids make revision cheap: "shorten C2", "drop C3", "make C1 a question", "translate the rest to Persian".

```bash
python3 scripts/comments.py update C1 --body-file /tmp/c1-v2.md
python3 scripts/comments.py update C1 --decision agreed --type blocker --severity correctness
python3 scripts/comments.py update C1 --no-long
python3 scripts/comments.py update C2 --reanchor --kind mr         # file left the diff
python3 scripts/comments.py drop C3 --reason "out of scope for this MR"
python3 scripts/comments.py drop --claim "Rename the util" --reason "style; covered by linter"
python3 scripts/comments.py approve "all, skip C3"    # or "1, 3" / "2=APPROVE"
python3 scripts/comments.py render
```

`update` also takes `--decision`, `--confidence`, `--source`, and `--long` / `--no-long`; it re-validates the whole matrix, then runs duplicate detection, so an edit cannot collide with another active comment. Demote an anchor that a rebase moved out of the diff with `--reanchor --kind mr` (or `--reanchor` with no `--path`) and keep its id. If that rebase also moved HEAD, run `init` first: `verify` cannot resync a state whose anchor no longer verifies.

`update` on an approved comment resets it to `pending`, so approval is always explicit. Re-render after every change. Re-run `verify` after any rebase or amend, then `render` again: the footer's SHA is the proof of freshness. After posting, `--one C2` retries a single comment; a batch retry is never implicit.

## 8. Degradation

| Situation | Behavior |
|---|---|
| No git repo | Stop with a clear message. |
| Detached HEAD | Use the explicit base and say so. |
| Empty diff | "No changes to review." Stop. |
| No `glab` | Offline mode: generate and render; posting is unavailable. |
| Non-GitLab host | Hard stop per §1. |
| Deleted file | Use a `file` anchor; inline lines do not exist. |
| File left the diff after a rebase | Run `init` to resync HEAD, then demote with `update <id> --reanchor --kind mr`. |
| HEAD moved since init | `verify` first; `add` and `update` refuse until the state matches. |
| No evidence for a candidate | Drop it; record the reason. |

---

## Comment anatomy

| Type | Shape |
|---|---|
| `blocker` | claim + evidence + required change + consequence |
| `question` | observation + question + why it matters; no embedded answer |
| `suggestion` | one-line why + native suggestion block (5 lines max) |
| `follow-up` | why it is out of scope + a concrete next step |
| `test-gap` | behavior + missing case + the cheapest useful test |

Confidence maps to phrasing: **high** is a recommendation, **medium** is a question, **low** is a drop. Severity is separate: `blocking`, `correctness`, `maintainability`, `nit`.

Keep the title under 60 characters and the body under 120 words (250 with `--long`). One comment, one change. If a body needs a second heading, it needs a second comment.

## Language

Write in the language of the user's first prompt and store it in `lang`.

- For Persian, load the `better-persian` skill if available. Otherwise apply four rules inline: use ZWNJ (`نیم‌فاصله`), Persian glyphs (`ی`, `ک`), keep Latin identifiers and code in backticks, and never repeat an English translation in parentheses.
- In RTL languages, start every line with a native word so renderers resolve direction correctly.
- Code, paths, commands, and measurements stay in Latin script even inside RTL prose.

## References

- [`references/comment-model.md`](references/comment-model.md) — schema v1, anchor kinds, statuses, validation rules, selection policy.
- [`references/gitlab-recipes.md`](references/gitlab-recipes.md) — `glab api` payloads, discussion creation, dedupe, the 204 rule, error table.
- [`references/examples.md`](references/examples.md) — four certified comments and one rejected anti-example.
