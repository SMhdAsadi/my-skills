# Changelog — mr-comment-triage

All notable changes to the `mr-comment-triage` skill are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this skill adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each release is tagged `mr-comment-triage-v<version>` and published on the [Releases page](https://github.com/SMhdAsadi/my-skills/releases).

---

## [1.0.0] - 2026-10-26

### Added

- **Three-phase triage workflow:** read-only collection and verification, a single batch proposal, then execution gated on explicit per-item approval. Nothing in the repository is written before gate 1.
- **Six-verdict taxonomy:** `ACCEPT`, `ALTERNATIVE`, `PUSH_BACK`, `DEFER`, `ALREADY_FIXED`, `CLARIFY`. `CLARIFY` and `DEFER` are non-executable and are held back by `approve "all"` rather than silently folded into the diff.
- **`scripts/fetch_threads.py`:** provider-normalized collection.
  - GitHub through GraphQL `reviewThreads`, because `gh pr view --comments` carries no resolution state. Paginates via `pageInfo` and warns when `totalCount` exceeds what was fetched.
  - GitLab through `projects/:id/merge_requests/:iid/discussions`, because `glab mr note list --state unresolved` is still marked experimental. Supports self-hosted hosts and URL-encodes the project path.
  - Filters on `resolvable && !resolved`, drops system notes, and falls back through `line → originalLine → line_range.start`.
  - Detects staleness from `isOutdated` (GitHub) and `position.head_sha != diff_refs.head_sha` (GitLab).
  - Classifies authors as `human`, `bot`, `self`, or `unknown` without dismissing bot comments.
  - Re-fetching preserves existing verdicts and records a `head-moved` event when HEAD changed.
- **`scripts/triage_state.py`:** state inspection and mutation, with a deterministic approval parser (`all`, `1, 3`, `skip 2`, `2=ACCEPT`). `approve` replaces the previous plan and reports what it un-approved. Rejects unknown thread ids instead of dropping them.
- **`scripts/post_reply.py`:** reply and resolve, preview-only unless `--post` is passed. Refuses unapproved items, empty bodies, and double-posting. Resolving requires `--post --resolve` as a separate decision.
- **`scripts/_common.py`:** gitignored-directory state resolution (`$MR_TRIAGE_DIR` → existing ignored scratch dir → creatable `.tmp/` → system temp), atomic writes, and stable per-target filenames.
- **Persistent state file (`mr-triage.json`):** single source of truth for threads, verdicts, statuses, and an append-only event log. Never written to a tracked path.
- **`references/thread-model.md`:** schema, anchor kinds (`inline` / `file` / `mr`), staleness rules, and the item status lifecycle.
- **`references/fetch-recipes.md`:** the underlying GraphQL and REST commands, provider traps, and a troubleshooting table.
- **Test suite:** 38 stdlib `unittest` cases covering remote parsing, both normalizers, approval parsing, state directory resolution, and atomic saves. No network or credentials required.

### Design notes

- **Anchors are not always lines.** Real MRs contain resolvable threads with `position: null`; a mandatory "file and line" column breaks on them, so the model has three anchor kinds.
- **`resolved == false` is the wrong filter.** GitLab returns `resolvable: false, resolved: null` for system notes, so the predicate is `resolvable && !resolved`.
- **Bots are judged by content.** A generated reviewer comment that encodes a checkable requirement is a legitimate finding.
- **Two gates, not one.** Editing code and posting on a shared MR have different blast radii, so posting and resolving are separate explicit flags.
