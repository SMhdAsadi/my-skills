# Comment model and state schema

The state file (`mr-comments-<project>-<iid>.json`) is the single source of truth for one merge request. Chat scrollback is not a database: the file is what makes "why did we drop that one?" answerable after the conversation moves on.

Schema version: **1**. Written by `scripts/comments.py init`, mutated by `add` / `update` / `verify` / `approve` / `drop` / `render`, and read by `scripts/post_comments.py`.

---

## Where the file lives

Resolution order, first match wins:

| Priority | Location | Notes |
|---|---|---|
| 1 | `$MR_COMMENTS_DIR` | Explicit override, for CI or a shared workspace. |
| 2 | `<repo>/tmp/to-mr-comments/`, `<repo>/.tmp/to-mr-comments/`, `<repo>/scratch/to-mr-comments/`, `<repo>/.scratch/to-mr-comments/` | First parent that exists **and** passes `git check-ignore`. The skill-owned subdirectory keeps project files and other skills out of the way. |
| 3 | `<repo>/.tmp/to-mr-comments/` | Created only when git already ignores `.tmp/`. |
| 4 | `$TMPDIR/to-mr-comments/` | Fallback when the repo has no ignored scratch dir. |

The rule is absolute: **the state file must never appear in `git status`.** A comment log in the repo would end up in a commit, and generated review notes are not source code.

The filename is stable per target, so re-running `init` resumes instead of fragmenting:

```
mr-comments-<project-slug>-<iid>.json
mr-comments-team-api-2340.json
```

Re-initialising preserves `comments`, `dropped`, and `events`, updates the `mr` block, and appends an `updated` event. If HEAD moved, it records a warning and leaves re-verification to `verify`. `add` and `update` refuse while `mr.headSha` is stale; a clean `verify` writes the new HEAD into both `mr.headSha` and `mr.diffRefs.head_sha`, so the footer and the next GitLab payload agree.

---

## File shape

```json
{
  "schemaVersion": 1,
  "lang": "en",
  "createdAt": "2026-11-04T10:00:00Z",
  "mr": {
    "provider": "gitlab",
    "host": "gitlab.example.com",
    "project": "team/api",
    "iid": "2340",
    "webUrl": "https://gitlab.example.com/team/api/-/merge_requests/2340",
    "base": "main",
    "sourceBranch": "feat/slider-throttle",
    "targetBranch": "main",
    "headSha": "abc1234",
    "diffRefs": {
      "base_sha": "1111111",
      "start_sha": "2222222",
      "head_sha": "abc1234"
    }
  },
  "budget": { "target": 5, "max": 10, "forced": false },
  "comments": [
    {
      "id": "C1",
      "status": "pending",
      "type": "blocker",
      "severity": "correctness",
      "anchor": {
        "kind": "inline",
        "path": "src/components/VSlider/VSlider.tsx",
        "oldPath": null,
        "line": 118,
        "endLine": 124,
        "inDiff": true,
        "verifiedAt": "abc1234",
        "verifiedHash": "sha256:…",
        "verifiedText": "scheduleOnRN(onGesture, 'change');"
      },
      "evidence": "src/components/VSlider/VSlider.tsx:118 fires per pan tick; ~120 calls/s at 120Hz",
      "source": {
        "kind": "conversation",
        "decision": "agreed",
        "confidence": "high",
        "quote": "we should throttle this"
      },
      "title": "Throttle UI-to-JS dispatch in panGesture.onChange",
      "body": "Calling `scheduleOnRN` on every pan tick can dispatch up to 120 calls/sec…",
      "suggestion": null,
      "long": false,
      "posted": { "noteId": null, "discussionId": null, "postedAt": null }
    }
  ],
  "dropped": [
    {
      "claim": "Uniform LTR enforcement across all players",
      "reason": "unbounded audit; no anchor",
      "source": "conversation"
    }
  ],
  "events": [
    { "at": "2026-11-04T10:00:00Z", "kind": "created", "detail": "C1" }
  ]
}
```

---

## Fields

### Root

| Field | Type | Required | Notes |
|---|---|---|---|
| `schemaVersion` | integer | yes | `1`. |
| `lang` | string | yes | Language of the user's first prompt (`en`, `fa`, …). |
| `createdAt` | ISO-8601 string | yes | Preserved across re-init. |
| `mr` | object | yes | Target merge request. |
| `budget` | object | yes | `{target, max, forced}`. |
| `comments` | array | yes | Every comment ever added, including dropped ones. |
| `dropped` | array | yes | Candidates rejected before becoming comments. |
| `events` | array | yes | Append-only audit log. |

### `mr`

| Field | Type | Required | Notes |
|---|---|---|---|
| `provider` | `"gitlab"` | yes | GitLab only. |
| `host` | string | yes | `gitlab.example.com`, no scheme. |
| `project` | string | yes | `group/subgroup/project`. |
| `iid` | string | yes | MR IID, not the global id. |
| `webUrl` | string | yes | Canonical MR URL. |
| `base` | string | yes | Diff base ref used by `git diff <base>...HEAD`. |
| `sourceBranch` | string | yes | Source branch at init time. |
| `targetBranch` | string | yes | Target branch. |
| `headSha` | string | yes | Full SHA the verification is valid for. |
| `diffRefs` | object | yes | `base_sha`, `start_sha`, `head_sha` from GitLab, or derived from git in offline mode. |

### `comments[]`

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | `C1…Cn`, assigned once, never reused. |
| `status` | enum | yes | `pending`, `approved`, `dropped`, `posted`. A legacy `draft` is accepted on read and normalised to `pending`; writes always use `pending`. |
| `type` | enum | yes | `blocker`, `question`, `suggestion`, `follow-up`, `test-gap`. |
| `severity` | enum | yes | `blocking`, `correctness`, `maintainability`, `nit`. |
| `anchor` | object | yes | See below. |
| `evidence` | string | yes | Must cite a location, command, URL, or measurement. |
| `source` | object | yes | Provenance and confidence. |
| `title` | string | yes | 60 characters or fewer. |
| `body` | string | yes | Final prose only. Never the title, target, or fences. |
| `suggestion` | string \| null | yes | Replacement lines without fences; required for `suggestion`, null otherwise. Maximum 5 lines. |
| `long` | boolean | yes | Relaxes the body limit from 120 to 250 words. |
| `posted` | object | yes | `{noteId, discussionId, postedAt}`. `noteId` is the created note; `discussionId` is set for discussion notes and for a matched duplicate. |
| `dropReason` | string | no | Set by `drop` or by an approval skip. |

### `anchor`

| Field | Type | Required | Notes |
|---|---|---|---|
| `kind` | enum | yes | `inline`, `file`, `mr`. |
| `path` | string \| null | inline/file | Repository-relative path at HEAD. |
| `oldPath` | string \| null | no | Pre-rename path when the diff renames or copies the file; `null` otherwise. Set by `add`, `update --reanchor`, and `verify`. |
| `line` | integer \| null | inline | The API anchor. Always a single line. |
| `endLine` | integer \| null | no | Display and prose only. Never sent as `line_range`, but the span is verified. |
| `inDiff` | boolean \| null | no | Set by verification; null for MR-level. |
| `verifiedAt` | string \| null | no | HEAD SHA the anchor was verified at. |
| `verifiedHash` | string \| null | no | `sha256:` of `line..endLine` at HEAD. |
| `verifiedText` | string \| null | no | Text at `line` when verified. |

### `source`

| Field | Type | Required | Notes |
|---|---|---|---|
| `kind` | `conversation` \| `diff` | yes | Where the candidate came from. |
| `decision` | `agreed` \| `open` \| `rejected` \| `hypothesis` | yes | The user's stance. |
| `confidence` | `high` \| `medium` \| `low` | yes | Controls phrasing and eligibility. |
| `quote` | string \| null | no | Short provenance quote. **Never rendered.** |

### `dropped[]` and `events[]`

| Field | Type | Notes |
|---|---|---|
| `claim` | string | The rejected candidate, stated in one line. |
| `reason` | string | Why it was rejected. |
| `source` | `conversation` \| `diff` | Where it came from. |

`comments.py drop --claim ... --reason ... [--source ...]` appends these rows before a candidate ever becomes a comment; `drop <id>` moves an existing comment to `dropped` instead. Both append a `dropped` event.

Events are `{at, kind, detail}` with `kind` ∈ `created`, `updated`, `verified`, `approved`, `dropped`, `posted`, `skipped-duplicate`.

---

## Anchor kinds

| Kind | Required | Posting behavior |
|---|---|---|
| `inline` | `path`, `line`; `inDiff = true` | GitLab diff note (`position_type: "text"`, `new_line`). |
| `file` | `path`; path in the diff's changed-file list | GitLab file note (`position_type: "file"`). |
| `mr` | none | Regular MR note (`POST .../notes`). |

Verification order for one anchor:

1. A state HEAD that differs from the live HEAD is `head-moved`, before any content check.
2. `mr` is always `ok`.
3. A missing `path` is `missing`; a path absent from the diff is `out-of-diff`.
4. `file` is `ok` as soon as the path is in the diff's changed-file set. It does not need the file at HEAD, so deleted, binary, and pure-rename files work.
5. `inline` must exist at HEAD, must have an integer `line`, and its whole `line..endLine` span must fit inside both the file and a single diff hunk.

A renamed or copied destination path (`new_path`) also records its source path as `oldPath`, taken from the diff's `rename from` / `copy from` line. That is what keeps the GitLab payload's `old_path` correct without a git call at preview time.

`endLine` widens the range a human sees and the range the verifier and hash cover; it does not widen the API anchor. The tool deliberately avoids `line_range` / `line_code`, which are fragile across GitLab versions and renamed files. A comment about a whole deleted file uses `file`; the tool never anchors a deleted line.

## Status lifecycle

```
pending ──approve──▶ approved ──post──▶ posted
   │                    │
   └──────drop──────────┴──────▶ dropped
```

- `pending` → `approved`, `dropped`
- `approved` → `posted`, `pending` (any edit resets it), `dropped`
- `dropped` is terminal for posting; the row stays in `comments` so its id is never reused.
- `posted` is terminal. No edits, no second post.
- Dropping a comment or recording a rejected candidate never blocks re-adding the same body at the same anchor: duplicate detection ignores `dropped` rows.

`approve` replaces the previous plan: a comment that was approved and is not in the new expression returns to `pending` and is reported as un-approved.

## Recording rejected candidates

`drop` has two modes and never guesses which one you meant:

| Invocation | Effect |
|---|---|
| `drop C3 --reason "..."` | Moves the existing comment to `dropped`, sets `dropReason`, appends a `dropped` event. Posted comments refuse. |
| `drop --claim "..." --reason "..." [--source conversation\|diff]` | Appends `{claim, reason, source}` to `dropped[]` and a `dropped` event; no comment is created. |
| Both an id and `--claim`, or neither | Error: ambiguous invocation. |

---

## Validation rules (`add` and `update`)

Hard failures, not warnings:

| Rule | Result |
|---|---|
| `type` not in the allowed set | reject |
| `severity` not in the allowed set | reject |
| `decision` is `rejected` or `hypothesis` | reject; point at `drop --claim` |
| `decision == open` on a non-`question` type | reject |
| `decision != agreed` on `blocker`, `suggestion`, `follow-up`, or `test-gap` | reject |
| `confidence == low` on any type | reject; point at `drop --claim` |
| `inline` without `path` + `line` | reject |
| `inline` whose `line..endLine` is outside the file at HEAD | reject |
| `inline` whose `line..endLine` spans outside one diff hunk | reject; suggest `file` or `mr` |
| `file` anchor whose path is not in the diff | reject; suggest `mr` |
| Evidence missing, or without `path:line`, a backticked command, a URL, or a measurement | reject |
| Duplicate `(path, line, normalised body)` against a live comment | reject, on `add` and after an `update` |
| Title longer than 60 characters | reject |
| Body longer than 120 words (250 with `--long`) | reject |
| `suggestion` without a replacement | reject |
| `suggestion` longer than 5 lines | reject |
| More than `budget.max` live comments | reject unless `--force`, which sets `budget.forced = true` |
| Exactly at `budget.target` | warn once, then allow |
| Comment id already exists | reject |
| `update --reanchor` without re-verification | reject |
| `add` / `update` when live HEAD differs from `mr.headSha` | reject; run `verify` or `init` first |
| `update` with `--path` / `--line` but no `--reanchor` | reject |

`looks_like_evidence(text)` accepts any of: `\S+:\d+`, `` `[^`]+` ``, `https?://…`, or a number followed by `ms|s|fps|%|x|KB|MB|GB`.

---

## Selection policy

Keep a candidate only if it passes at least one:

1. Prevents a reachable defect: crash, data loss, race, wrong output.
2. Breaks a stated contract or invariant.
3. Leaves changed behaviour untested in a way that matters.
4. Creates unbounded cost: per-frame work, N+1 queries, leaks, retry storms.
5. The user explicitly asked for it.

Reject if any:

- Style-only and already covered by the formatter or linter.
- A preference with no stated consequence.
- Requires an unbounded audit the diff cannot satisfy.
- Already raised and resolved in the thread.
- No citable evidence.

Then dedupe by root cause or symbol, merge nits into one comment, and record every rejected candidate in `dropped[]`. A run that emits nothing is a valid, successful run.

### Confidence → phrasing

| Confidence | Phrasing |
|---|---|
| `high` | Recommendation: "Let's…", "This will…" |
| `medium` | Question: "Does this…?", "What happens when…?" |
| `low` | Drop it. Do not phrase it as a hedge. |

---

## Privacy

`source.quote` is provenance for the agent, not comment copy. It is written to the state file and **never** rendered, posted, or summarised into a comment. The same rule applies to harvested context: no credentials, tokens, customer data, internal URLs, or private metrics. Evidence in a comment is a `path:line` and a fact about the code, not a quotation from a private channel.

---

## Budget semantics

- `target = 5`: the soft target. Reaching it prints a one-time warning.
- `max = 10`: the hard cap. `add` refuses the 11th live comment unless `--force`.
- `forced`: set to `true` when `--force` was used, so a later reader knows the cap was overridden.
- Dropped comments do not count against the budget; they still hold their ids.
