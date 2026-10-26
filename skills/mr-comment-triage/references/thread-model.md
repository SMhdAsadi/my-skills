# Thread model and state schema

The triage state file (`mr-triage.json`) is the single source of truth for a run. Chat scrollback is not a database: a plan that survives across turns is what makes "what did we decide on #2?" answerable three turns later.

Schema version: **1**. Written by `scripts/fetch_threads.py`, mutated by `scripts/triage_state.py` and `scripts/post_reply.py`.

---

## Where the file lives

Resolution order, first match wins:

| Priority | Location | Notes |
|---|---|---|
| 1 | `$MR_TRIAGE_DIR` | Explicit override, for CI or a shared workspace. |
| 2 | `<repo>/.tmp/`, `<repo>/scratch/`, `<repo>/.scratch/` | First one that exists **and** passes `git check-ignore`. |
| 3 | `<repo>/.tmp/` | Created only when git already ignores that path. |
| 4 | `$TMPDIR/mr-comment-triage/` | Fallback when the repo has no ignored scratch dir. |

The rule is absolute: **the state file must never appear in `git status`.** A verdict log in the repo would end up in a commit, and a review bot's output is not source code.

Filename is stable per target, so re-running the fetcher resumes instead of fragmenting:

```
<provider>-<repo-slug>-<number>.json
gitlab-virasty-client-reactnative-2340.json
github-cli-cli-14783.json
```

Re-fetching preserves `items` and appends a `refetched` event. If HEAD moved between fetches, a `head-moved` event and a warning are added — existing verdicts may be stale and must be re-verified, not blindly applied.

---

## Anchors

A comment's position is not always a line. Three kinds, decided once at fetch time so later phases never branch on provider:

| Kind | Meaning | Source (GitHub) | Source (GitLab) |
|---|---|---|---|
| `inline` | `path` + `line` | `reviewThreads.path` + `line ?? originalLine` | `position.new_path` + `new_line ?? old_line` |
| `file` | `path`, no line | `path` set, `line` null | `position.new_path` set, both lines null |
| `mr` | no position at all | `path` null | `position` null (`DiscussionNote`) |

`side` is `new` when the anchor sits on the post-change side (`diffSide == RIGHT`, or `new_line` present) and `old` for deletions. A deleted-line comment must be read against the old file, not the new one.

Multi-line comments carry `endLine`; the range start is the anchor `line`.

---

## Staleness

`stale: true` means the comment was written against a diff version that is no longer HEAD. It does not mean the comment is wrong — it means the anchor has to be re-resolved before the claim can be judged.

| Provider | Test |
|---|---|
| GitHub | `reviewThreads.isOutdated` |
| GitLab | `note.position.head_sha != mr.diff_refs.head_sha` |

A stale thread still gets a verdict. `ALREADY_FIXED` is the common outcome, but not the automatic one.

---

## File shape

```json
{
  "schemaVersion": 1,
  "provider": "github",
  "host": "github.com",
  "repo": "cli/cli",
  "target": {
    "kind": "pr",
    "number": 14783,
    "title": "release download: add --verify",
    "url": "https://github.com/cli/cli/pull/14783",
    "headSha": "654d851d...",
    "baseSha": "0f1e2d3c..."
  },
  "fetchedAt": "2026-10-26T10:20:00Z",
  "warnings": [],
  "threads": [
    {
      "id": "gh:PRRT_kwDODKw3uc6u3y-b",
      "remoteId": "PRRT_kwDODKw3uc6u3y-b",
      "anchor": {
        "kind": "inline",
        "path": "pkg/cmd/release/download/download.go",
        "line": 600,
        "endLine": 604,
        "side": "new"
      },
      "author": "copilot-pull-request-reviewer",
      "authorKind": "bot",
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
      "threadIds": ["gh:PRRT_kwDODKw3uc6u3y-b"],
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

`remoteId` is what the forge needs to reply: the GraphQL node id on GitHub, the 40-character discussion id on GitLab. `id` is the namespaced key used everywhere else (`gh:` / `gl:`), so a state file can never confuse the two.

`authorKind` is `human`, `bot`, `self`, or `unknown`. Bots are classified by GraphQL `__typename == "Bot"`, a `[bot]` / `-bot` / `_bot` suffix, or a known-reviewer list — never dismissed on that basis alone.

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
