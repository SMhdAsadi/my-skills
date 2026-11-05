# Thread model and state schema

The triage state file (`mr-triage.json`) is the single source of truth for a run. Chat scrollback is not a database: a plan that survives across turns is what makes "what did we decide on #2?" answerable three turns later.

Schema version: **1**. Written by `scripts/fetch_threads.py`, mutated by `scripts/triage_state.py` and `scripts/post_reply.py`.

---

## Where the file lives

Resolution order, first match wins:

| Priority | Location | Notes |
|---|---|---|
| 1 | `$MR_TRIAGE_DIR` | Explicit override, for CI or a shared workspace. |
| 2 | `<repo>/tmp/mr-comment-triage/`, `<repo>/.tmp/mr-comment-triage/`, `<repo>/scratch/mr-comment-triage/`, `<repo>/.scratch/mr-comment-triage/` | First parent that exists **and** passes `git check-ignore`. The skill-owned subdirectory keeps project files and other skills out of the way. |
| 3 | `<repo>/.tmp/mr-comment-triage/` | Created only when git already ignores `.tmp/`. |
| 4 | `$TMPDIR/mr-comment-triage/` | Fallback when the repo has no ignored scratch dir. |

The rule is absolute: **the state file must never appear in `git status`.** A verdict log in the repo would end up in a commit, and a review bot's output is not source code.

Filename is stable per target, so re-running the fetcher resumes instead of fragmenting:

```
gitlab-<repo-slug>-<number>.json
gitlab-virasty-client-reactnative-2340.json
```

Re-fetching preserves `items` and appends a `refetched` event. If HEAD moved between fetches, a `head-moved` event and a warning are added — existing verdicts may be stale and must be re-verified, not blindly applied.

---

## Anchors

A comment's position is not always a line. Three kinds, decided once at fetch time so later phases never branch on the payload shape:

| Kind | Meaning | Source (GitLab) |
|---|---|---|
| `inline` | `path` + `line` | `position.new_path` or `old_path`, plus a line or `line_range` |
| `file` | `path`, no line | `position.new_path` or `old_path` set, all lines null |
| `mr` | no position at all | `position` null (`DiscussionNote`) |

`path` is `new_path` when it exists, otherwise `old_path`, so a deleted file anchors at its old path. `oldPath` keeps the pre-rename path for renames and payload construction; it is `null` when the path did not change or there is no `old_path`.

`side` is `new` for the post-change side and `old` for deletions (`new_line` → `new`, else `old_line` → `old`). When both are null the side comes from `line_range`: non-null `new_line` values in `start`/`end` win, otherwise the non-null `old_line` values. A mixed range that mentions both sides is therefore read against the new file, deterministically. `line`/`endLine` are the min/max of the chosen side's values, and an inline anchor never has a null `side`. A deleted-line comment must be read against the old file, not the new one.

Multi-line comments carry `endLine`; the range start is the anchor `line`.

---

## Staleness

`stale: true` means the comment was written against a diff version that is no longer HEAD. It does not mean the comment is wrong — it means the anchor has to be re-resolved before the claim can be judged.

It is measured as `note.position.head_sha != mr.diff_refs.head_sha`.

A stale thread still gets a verdict. `ALREADY_FIXED` is the common outcome, but not the automatic one.

---

## File shape

```json
{
  "schemaVersion": 1,
  "provider": "gitlab",
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
  "fetchedAt": "2026-10-26T10:20:00Z",
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
        { "author": "alice", "authorKind": "human", "body": "Fixed in 654d851.", "createdAt": "..." }
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
        { "path": "pkg/cmd/release/download/download.go", "line": 596, "note": "early return removed" }
      ],
      "action": "restore the early return before the verify branch",
      "replyDraft": "Good catch — restored the early return in 654d851.",
      "status": "approved",
      "commitSha": null,
      "postedAt": null,
      "postedReplies": []
    }
  ],
  "events": [
    { "at": "2026-10-26T10:20:00Z", "type": "fetched", "detail": "3 unresolved of 3 thread(s)" },
    { "at": "2026-10-26T10:26:00Z", "type": "approved", "detail": "approved=[1] skipped=[3] unapproved=[]" }
  ]
}
```

`remoteId` is what GitLab needs to reply: the full 40-character discussion id. `id` is the namespaced key used everywhere else (`gl:`), so a state file can never be confused with another forge.

`authorKind` is `human`, `bot`, `self`, or `unknown`. Bots are classified by a `[bot]` / `-bot` / `_bot` suffix or a known-reviewer list — never dismissed on that basis alone.

---

## Verdicts and statuses

`verdict` ∈ `ACCEPT`, `ALTERNATIVE`, `PUSH_BACK`, `DEFER`, `ALREADY_FIXED`, `CLARIFY`.
`severity` ∈ `blocking`, `correctness`, `maintainability`, `nit`.

`CLARIFY` and `DEFER` are **non-executable**: `approve "all"` holds them back, because the answer is a decision or a follow-up issue, not a patch.

`status` lifecycle:

```
proposed ──approve──▶ approved ──edit──▶ applied ──check──▶ verified ──post──▶ posted ──resolve──▶ resolved
    │                     │
    └──skip──────────────▶│
                          └──skip──▶ skipped / rejected
```

Only `approved`, `applied`, and `verified` items may be posted. Posting is refused twice over: unapproved status, or an item that already has `postedAt`.

---

## Invariants the scripts enforce

- Unknown thread ids are rejected rather than silently dropped — a typo in a thread id would otherwise produce a verdict with no thread behind it.
- `approve` replaces the plan and prints what it un-approved, so a narrowed selection can never look like an addition.
- Saves are atomic (`.tmp` + `os.replace`), so an interrupted run cannot leave half a state file.
- The state directory is chosen by `git check-ignore`, never by convention alone.
