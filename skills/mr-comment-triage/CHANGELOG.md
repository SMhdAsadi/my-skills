# Changelog — mr-comment-triage

All notable changes to the `mr-comment-triage` skill are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this skill adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each release is tagged `mr-comment-triage-v<version>` and published on the [Releases page](https://github.com/SMhdAsadi/my-skills/releases).

---

## [2.0.0] - 2026-11-05

### Added

- **Batch plan ingestion:** `triage_state.py plan --from PLAN.json` accepts the whole item list as a JSON array or `{"items": [...]}` and validates every item — known and unique thread ids, verdict/severity enums, `path:line` evidence at HEAD, action for code verdicts, reply draft for reply-only verdicts — before one atomic write. `--dry-run` renders without saving. A bad item leaves the state file byte-identical. A replacement plan may not drop a thread that already has a post record: the record is carried to the new item and its status re-derived, without reviving the old approval.
- **Enforced state machine:** `approve` is the only writer of `approved`; the execute phase owns `applied`/`verified`; the reply phase owns `posted`/`resolved`. `set --status` refuses the states it does not own and names the command that does. `approve` also rejects an executable `ACCEPT`/`ALTERNATIVE` item with an empty `action`, and `applied` requires a `preflight-clean` event recorded at or after the item's `approvedAt`.
- **Thread ownership:** a thread id may belong to one item. `set --threads` dedupes repeated ids and rejects an id owned by another item; the reply command refuses a selection where two items name the same thread or a thread already has a post record on another item, before any preview or external call.
- **Approval evidence:** each approval records `approvedAt` and an `approvalHash` over the material intent (`verdict`, `threadIds`, `action`, `evidence`). A material edit invalidates the approval, returns the item to `proposed`, and appends an `approval-invalidated` event.
- **Reply-only fast path:** a plan with no code verdicts can skip Gate 1 and go straight to the batch reply preview and post. A plan that still contains an unapproved code item is refused instead of silently mixing it in.
- **Batched Gate 2:** `post_reply.py --all-approved` previews every eligible item, thread, body, and resolve decision in one output; one `--post` sends the batch. The item's stored `replyDraft` is the default body, and `--body`/`--body-file` overrides are recorded with `source: override`.
- **Per-thread journal:** each post records its exact body, timestamp, URL, resolution time, and source, and is saved before the next external call. A partial failure reports succeeded, failed, and unattempted threads and resumes without double-posting. Item status is derived from the journal; a duplicate group finishes only when every thread is recorded.
- **Re-fetch reconciliation:** re-fetching replaces `threads`, keeps `items`, appends events instead of replacing them, records a `head-moved` event and warning, and marks items whose threads vanished as `orphaned` with `missingThreadIds`, an `orphaned` event, and a warning. A returning thread clears the orphan state.
- **`preflight`:** refuses a dirty working tree before the execute phase with the offending paths, and records a clean result as a `preflight-clean` event. The guard is enforced: an item cannot move to `applied` without a clean check taken after its approval.
- **Resolve guard:** `--resolve` closes only `authorKind: self` threads. `--resolve-other` is required for anyone else, is only valid with `--resolve`, and appends a `resolve-override` event naming the thread and author.
- **Anchor completeness:** anchors keep `oldPath` for renames and deleted files, derive `side` from `new_line`/`old_line`/`line_range` (new side wins a mixed range), and never leave an inline anchor with a null side.
- **`MR_TRIAGE_DIR` guard:** an override inside a repository is accepted only when it passes `git check-ignore`; otherwise the command refuses it and names the path and repository.
- **Test suite:** 263 stdlib `unittest` cases covering the state machine, gates, batch plan and reply paths, thread ownership, HEAD evidence, the preflight guard, partial failure, anchors, re-fetch/orphans, safety guards, and the GitLab-only contract. No network, credentials, or CI workflow.

### Changed

- **GitLab only:** `glab` and `git` are the only forge dependencies; `glab` is required and there is no second transport. Compatibility metadata is now `glab >= 1.40; git >= 2.0`.
- **State schema v2:** the file is `gitlab-<repo-slug>-<number>.json`, carries `host`, `repo`, and a typed `target`, and `load_state` rejects any other schema version with instructions to re-fetch. There is no migration.
- **Two batched gates, constant invocation count:** a normal run is six calls — `fetch`, `plan --from`, `render`, `approve`, `post_reply.py --all-approved` preview, and `post_reply.py --all-approved --post` — regardless of thread count.
- **Evidence at HEAD:** `plan --from` checks every citation exists and the line is in range, and `approve` re-checks before approving.
- **Output:** plan and reply previews state item counts, thread counts, bodies, resolve decisions, held/skipped/unapproved items, and orphan warnings instead of leaving them implicit.
- **Error reporting:** a failing command is shown in full with reply bodies, `private_token`, `token`, and `query` values redacted, keeping the tool, subcommand, host, and endpoint diagnosable.

### Removed

- **The alternate forge provider:** its query layer, REST wrapper, normalizer, reply/resolve mutations, host-based provider detection, provider flag, fixtures, and every related document and recipe are removed. GitLab is the only forge left.
- **The undocumented bypass flag:** there is no force switch on any gate. The only override is the audited `--resolve-other`.
- **The thread-dump fallback:** `glab` is a hard requirement; there is no ingestion path for manually supplied comments.
- **The fixed ten-thread budget:** no silent truncation and no fixed cap. The documented guidance is to ask before planning an oversized batch.
- **Item-level posting fields and the `rejected` status:** replaced by per-thread `posts` and the derived status enum.

### Fixed

- **Gate 1 was a convention:** `set --status applied` and the bypass flag could make an unapproved item executable. Both paths are gone.
- **Approval drift:** changing the verdict, threads, action, or evidence after approval now invalidates the approval instead of authorizing a different action.
- **Partial batch corruption:** a successful reply is journaled before the next call, so a later failure cannot erase it or cause a re-post.
- **Duplicate thread ids:** ids are deduped at ingestion, and posting one thread no longer marks a whole item complete.
- **O(N) workflow:** one `plan --from` and one batched reply replace the per-item command loop.
- **State escaping the scratch directory:** an unignored override inside a repo is refused.
- **Destructive re-fetch:** events are appended, vanished threads are reconciled, and history survives.
- **Unprovable posts:** the state now records the exact posted body and its source.
- **Documentation that promised nonexistent behavior:** the thread-dump path, the fixed ten-thread budget, the alternate provider, the old state filename, and stale test counts are gone from the Skill, README, references, and repository catalog.

---

## [1.1.0] - 2026-11-04

### Changed

- **State location:** `tmp/` is now the highest-priority repo scratch directory when git already ignores it, and artifacts live in a skill-owned subdirectory (`tmp/mr-comment-triage/`) instead of directly in the scratch directory. This keeps state out of a shared `tmp/` and prevents collisions with project files or other skills. The `.tmp/`, `scratch/`, and `.scratch/` candidates follow the same subdirectory rule; a tracked or unignored `tmp/` is still skipped.

---

## [1.0.0] - 2026-10-26

### Added

- **Three-phase triage workflow:** read-only collection and verification, a single batch proposal, then execution gated on explicit per-item approval. Nothing in the repository is written before gate 1.
- **Six-verdict taxonomy:** `ACCEPT`, `ALTERNATIVE`, `PUSH_BACK`, `DEFER`, `ALREADY_FIXED`, `CLARIFY`. `CLARIFY` and `DEFER` are non-executable and are held back by `approve "all"` rather than silently folded into the diff.
- **`scripts/fetch_threads.py`:** GitLab collection.
  - Discussions come from `projects/:id/merge_requests/:iid/discussions`, because `glab mr note list --state unresolved` is still marked experimental. Supports self-hosted hosts and URL-encodes the project path. Paginates through `per_page`/`page` and warns at the page cap.
  - Filters on `resolvable && !resolved`, drops system notes, and falls back through `new_line → old_line → line_range`.
  - Detects staleness from `position.head_sha != diff_refs.head_sha`.
  - Classifies authors as `human`, `bot`, `self`, or `unknown` without dismissing bot comments.
  - Re-fetching preserves existing verdicts and records a `head-moved` event when HEAD changed.
- **`scripts/triage_state.py`:** state inspection and mutation, with a deterministic approval parser (`all`, `1, 3`, `skip 2`, `2=ACCEPT`). `approve` replaces the previous plan and reports what it un-approved. Rejects unknown thread ids instead of dropping them.
- **`scripts/post_reply.py`:** GitLab reply and resolve, preview-only unless `--post` is passed. Refuses unapproved items, empty bodies, and double-posting. Resolving requires `--post --resolve` as a separate decision.
- **`scripts/_common.py`:** gitignored-directory state resolution (`$MR_TRIAGE_DIR` → existing ignored scratch dir → creatable `.tmp/` → system temp), atomic writes, and stable per-target filenames.
- **Persistent, per-target state file:** single source of truth for threads, verdicts, statuses, and an append-only event log. Never written to a tracked path.
- **`references/thread-model.md`:** schema, anchor kinds (`inline` / `file` / `mr`), staleness rules, and the item status lifecycle.
- **`references/fetch-recipes.md`:** the underlying REST commands, GitLab traps, and a troubleshooting table.
- **Test suite:** stdlib `unittest` cases covering remote parsing, the GitLab normalizer, approval parsing, state directory resolution, and atomic saves. No network or credentials required.

### Design notes

- **Anchors are not always lines.** Real MRs contain resolvable threads with `position: null`; a mandatory "file and line" column breaks on them, so the model has three anchor kinds.
- **`resolved == false` is the wrong filter.** GitLab returns `resolvable: false, resolved: null` for system notes, so the predicate is `resolvable && !resolved`.
- **Bots are judged by content.** A generated reviewer comment that encodes a checkable requirement is a legitimate finding.
- **Two gates, not one.** Editing code and posting on a shared MR have different blast radii, so posting and resolving are separate explicit flags.
