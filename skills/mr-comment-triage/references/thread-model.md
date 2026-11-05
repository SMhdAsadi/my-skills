# Thread model and state schema

The triage state file is the single source of truth for a run. Chat scrollback is not a database: a plan that survives across turns is what makes "what did we decide on #2?" answerable three turns later.

Schema version: **2**. Written by `scripts/fetch_threads.py`, mutated by `scripts/triage_state.py` and `scripts/post_reply.py`. Any other `schemaVersion` is rejected rather than guessed at; re-fetch to rebuild the file.

---

## Where the file lives

Resolution order, first match wins:

| Priority | Location | Notes |
|---|---|---|
| 1 | `$MR_TRIAGE_DIR` | Explicit override. Accepted only when it resolves outside the repository, or inside it and passes `git check-ignore`. |
| 2 | `<repo>/tmp/mr-comment-triage/`, `<repo>/.tmp/mr-comment-triage/`, `<repo>/scratch/mr-comment-triage/`, `<repo>/.scratch/mr-comment-triage/` | First parent that exists **and** passes `git check-ignore`. The skill-owned subdirectory keeps project files and other skills out of the way. |
| 3 | `<repo>/.tmp/mr-comment-triage/` | Created only when git already ignores `.tmp/`. |
| 4 | `$TMPDIR/mr-comment-triage/` | Fallback when the repo has no ignored scratch dir. |

The rule is absolute: **the state file must never appear in `git status`.** A verdict log in the repo would end up in a commit, and a review bot's output is not source code. An unignored `$MR_TRIAGE_DIR` inside a repo is refused with the offending path and the repository it belongs to.

Filename is stable per target, so re-running the fetcher resumes instead of fragmenting:

```
gitlab-<repo-slug>-<number>.json
gitlab-virasty-client-reactnative-2355.json
```

The slug lowercases the project path and replaces every run of non-alphanumerics with a hyphen.

---

## Anchors

A comment's position is not always a line. Three kinds, decided once at fetch time so later phases never branch on the payload shape:

| Kind | Meaning | Source (GitLab) |
|---|---|---|
| `inline` | `path` + `line` | `position.new_path` or `old_path`, plus a line or `line_range` |
| `file` | `path`, no line | `position.new_path` or `old_path` set, all lines null |
| `mr` | no position at all | `position` null (`DiscussionNote`) |

`path` is `new_path` when it exists, otherwise `old_path`, so a deleted file anchors at its old path. `oldPath` keeps the pre-rename path for renames and payload construction; it is `null` when the path did not change or there is no `old_path`.

`side` is `new` for the post-change side and `old` for deletions (`new_line` → `new`, else `old_line` → `old`). When both are null the side comes from `line_range`: non-null `new_line` values in `start`/`end` win, otherwise the non-null `old_line` values. A mixed range that mentions both sides is therefore read against the new file, deterministically. `line`/`endLine` are the min/max of the chosen side's values, and an inline anchor never has a null `side` — a line with no side signal falls back to `new`. A deleted-line comment must be read against the old file, not the new one.

Multi-line comments carry `endLine`; the range start is the anchor `line`. A file-level or MR-level anchor has no side.

---

## Staleness

`stale: true` means the comment was written against a diff version that is no longer HEAD. It does not mean the comment is wrong — it means the anchor has to be re-resolved before the claim can be judged.

It is measured as `note.position.head_sha != mr.diff_refs.head_sha`. A stale thread still gets a verdict; `ALREADY_FIXED` is the common outcome, but not the automatic one.

---

## File shape

```json
{
  "schemaVersion": 2,
  "host": "code.ts.co.ir",
  "repo": "virasty/client-reactnative",
  "target": {
    "kind": "mr",
    "number": 2355,
    "title": "release download: add --verify",
    "url": "https://code.ts.co.ir/virasty/client-reactnative/-/merge_requests/2355",
    "headSha": "654d851d...",
    "baseSha": "0f1e2d3c..."
  },
  "fetchedAt": "2026-11-05T10:20:00Z",
  "warnings": [],
  "threads": [
    {
      "id": "gl:6f1c9d2e4a7b8c0d1e2f3a4b5c6d7e8f9a0b1c2d",
      "remoteId": "6f1c9d2e4a7b8c0d1e2f3a4b5c6d7e8f9a0b1c2d",
      "anchor": {
        "kind": "inline",
        "path": "pkg/cmd/release/download/download.go",
        "oldPath": null,
        "line": 600,
        "endLine": 604,
        "side": "new"
      },
      "author": "sara",
      "authorKind": "human",
      "body": "Requirement: preserve stdout behavior without --verify ...",
      "createdAt": "2026-10-20T09:14:00Z",
      "resolvable": true,
      "resolved": false,
      "stale": false,
      "replies": [
        {
          "author": "alice",
          "authorKind": "human",
          "body": "Fixed in 654d851.",
          "createdAt": "2026-10-21T08:02:00Z"
        }
      ]
    }
  ],
  "items": [
    {
      "n": 1,
      "threadIds": ["gl:6f1c9d2e4a7b8c0d1e2f3a4b5c6d7e8f9a0b1c2d"],
      "verdict": "ACCEPT",
      "severity": "blocking",
      "claim": "stdout changes when --verify is omitted",
      "evidence": [
        {
          "path": "pkg/cmd/release/download/download.go",
          "line": 596,
          "note": "early return removed"
        }
      ],
      "action": "restore the early return before the verify branch",
      "replyDraft": "Good catch — restored the early return in 654d851.",
      "status": "posted",
      "approvedAt": "2026-11-05T10:26:00Z",
      "approvalHash": "9c1f...",
      "commitSha": "654d851",
      "posts": [
        {
          "threadId": "gl:6f1c9d2e4a7b8c0d1e2f3a4b5c6d7e8f9a0b1c2d",
          "postedAt": "2026-11-05T11:04:00Z",
          "resolvedAt": null,
          "body": "Good catch — restored the early return in 654d851.",
          "url": "https://code.ts.co.ir/.../notes/991",
          "source": "draft"
        }
      ],
      "orphaned": false,
      "missingThreadIds": [],
      "updatedAt": "2026-11-05T11:04:00Z"
    }
  ],
  "events": [
    {
      "at": "2026-11-05T10:20:00Z",
      "type": "fetched",
      "detail": "4 unresolved of 4 thread(s)"
    }
  ]
}
```

The example's item `status` is illustrative; the real values are the enum below and are derived from the posts, not written by hand.

`remoteId` is what GitLab needs to reply: the full discussion id. `id` is the namespaced key used everywhere else (`gl:`), so a state file can never be confused with another forge. The `gl:` prefix is retained even though GitLab is the only transport, because it makes a hand-edited file obviously invalid.

`authorKind` is `human`, `bot`, `self`, or `unknown`. `self` is set only when the note's username matches `GET /user` for the authenticated `glab` account. Bots are classified by a `[bot]` / `-bot` / `_bot` suffix or a known-reviewer list — never dismissed on that basis alone.

Post record:

```json
{
  "threadId": "gl:...",
  "postedAt": "2026-11-05T11:04:00Z",
  "resolvedAt": null,
  "body": "<exact posted text>",
  "url": "https://.../notes/991",
  "source": "draft | override"
}
```

Event record:

```json
{ "at": "2026-11-05T11:04:00Z", "type": "posted", "detail": "item #1 thread gl:..." }
```

Event types currently written: `fetched`, `refetched`, `head-moved`, `planned`, `approved`, `approval-invalidated`, `preflight-clean`, `posted`, `resolved`, `orphaned`, `resolve-override`, `skipped`. The status change itself is visible on the item; the event log records decisions, posting, and reconciliation.

---

## Verdicts, evidence, and approval

`verdict` ∈ `ACCEPT`, `ALTERNATIVE`, `PUSH_BACK`, `DEFER`, `ALREADY_FIXED`, `CLARIFY`.
`severity` ∈ `blocking`, `correctness`, `maintainability`, `nit`.

`ACCEPT` and `ALTERNATIVE` are the **code verdicts**: they need a non-empty `action`. The other four are **reply-only**: they need a non-empty `replyDraft` and edit no code. `CLARIFY` and `DEFER` are additionally **non-executable**: `approve all` holds them back, because the answer is a decision or a follow-up issue, not a patch.

Every evidence entry is `{path, line, note}` and is verified twice:

1. `plan --from` proves the path exists, is a file inside the checkout, and `1 <= line <= line count` at HEAD.
2. `approve` re-verifies the same entries before writing an approval. A held `CLARIFY`/`DEFER` item is skipped because it authorises no execution.

Evidence is required at plan time. An empty list is allowed when there is genuinely no line to cite; a missing field is not.

`approvalHash = sha256(canonical_json({verdict, threadIds, action, evidence}))`. Those four fields are the material intent. Changing any of them clears `approvedAt` and `approvalHash`, returns `approved`/`applied`/`verified` to `proposed`, and appends an `approval-invalidated` event. Changing `claim`, `replyDraft`, or `severity` does not invalidate the approval, but the new text is what gets posted or rendered.

---

## Status lifecycle

```
proposed ──approve──▶ approved ──apply──▶ applied ──check──▶ verified ──post──▶ posted ──resolve──▶ resolved
    │                    │
    └────skip────────────┴────skip────▶ skipped
```

- `proposed` — on the plan, not approved.
- `approved` — written only by `triage_state.py approve`, with `approvedAt` and `approvalHash`.
- `applied` — written only by `set --status applied`, and only from `approved`.
- `verified` — written only by `set --status verified`, and only from `approved` or `applied`.
- `posted` — derived when every thread on the item has a post record but at least one is unresolved.
- `resolved` — derived when every thread on the item has a post record with `resolvedAt`.
- `skipped` — written by `set --status skipped` or `approve ... skip N`, from `proposed` or `approved`. Skipping an approved item invalidates its approval.

Code items stop at `verified`; the reply phase is what moves them to `posted`/`resolved`. Reply-only items may go `proposed` or `approved` → `posted` → `resolved`.

`set --status` refuses `approved`, `posted`, and `resolved` outright and names the command that owns each. There is no direct writer for the derived states.

### Derived status and the per-thread journal

An item's status is recomputed from `posts` whenever a thread is posted or resolved:

- At least one `threadIds` entry has no post → the previous status survives, so a partial batch stays resumable.
- Every entry has a post, at least one has no `resolvedAt` → `posted`.
- Every entry has a post with `resolvedAt` → `resolved`.

The journal is per thread, not per item. A duplicate group is complete only when every thread is posted/resolved. Posting a single thread with `--thread` records that thread and leaves the rest of the item actionable. The exact body, the `draft`/`override` source, the timestamp, URL, and resolution time are all written to disk **before the next external call**, so an interrupted batch never re-posts a successful thread.

---

## Re-fetch reconciliation

Re-fetching the same MR preserves triage work instead of resetting it:

- `threads` is replaced by the fresh, authoritative set.
- `items` are carried forward with their verdicts, statuses, approval metadata, and post journal.
- `events` are concatenated: all prior events are kept, then the new `fetched` event, then a `refetched` event. Old events are never duplicated.
- If HEAD moved, a `head-moved` event and a warning are added; existing verdicts may be stale and must be re-verified, not blindly applied.
- An item with any `threadIds` absent from the fresh set gets `orphaned: true`, `missingThreadIds` naming the gone ids, an `orphaned` event, and a warning. Its approval is invalidated unless it is already `posted`/`resolved`.
- A thread that reappears clears `orphaned` and `missingThreadIds`, making the item plannable again.
- New threads are simply present for planning; they never join an existing item automatically.

`--reset` discards items and events and starts clean. It is the only way to drop triage history.

`--include-resolved` keeps resolved threads so a reply can be checked for duplicates. The summary distinguishes them honestly: `threads 4 unresolved, 2 resolved kept`, never counting resolved threads as unresolved.

---

## Orphan rules

`orphaned: true` means at least one thread the item names no longer exists in the MR. It is not a status; it is a gate:

- `render` and `show` print a warning naming the missing thread ids.
- `post_reply.py` refuses the item, in both `--item` and `--all-approved`, until it is re-planned or dropped.
- `approve` is not enough to clear it — only a re-fetch that finds the thread again, or a plan that stops naming it.

This is deliberately stricter than a warning. Posting a reply to a discussion id that GitLab no longer returns is at best a 404 and at worst a reply on a deleted thread.

---

## Invariants the scripts enforce

- Unknown thread ids are rejected rather than silently dropped — a typo in a thread id would otherwise produce a verdict with no thread behind it.
- A thread id may appear in one item only, and repeated ids inside an item are deduped in place.
- `plan --from` validates the whole document before writing; one bad item leaves the state file byte-identical.
- `approve` replaces the plan and prints what it un-approved, so a narrowed selection can never look like an addition.
- Only `approve` writes `approved`; only the execute phase writes `applied`/`verified`; only the reply phase writes `posted`/`resolved`.
- Only the reply phase can close a thread, and only `--resolve-other` can close one authored by someone else.
- Saves are atomic (`.tmp` + `os.replace`), so an interrupted run cannot leave half a state file.
- The state directory is chosen by `git check-ignore`, never by convention alone.
