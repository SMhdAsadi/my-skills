# Changelog — to-mr-comments

All notable changes to the `to-mr-comments` skill are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this skill adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each release is tagged `to-mr-comments-v<version>` and published on the [Releases page](https://github.com/SMhdAsadi/my-skills/releases).

---

## [2.1.0] - 2026-11-04

### Changed

- **State location:** `tmp/` is now the highest-priority repo scratch directory when git already ignores it, and artifacts live in a skill-owned subdirectory (`tmp/to-mr-comments/`) instead of directly in the scratch directory. This keeps state out of a shared `tmp/` and prevents collisions with project files or other skills. The `.tmp/`, `scratch/`, and `.scratch/` candidates follow the same subdirectory rule; a tracked or unignored `tmp/` is still skipped.

---

## [2.0.0] - 2026-11-04

### Removed

- **GitLab draft notes are gone.** `--create`, `--publish`, `bulk_publish`, `posted.draftNoteId`, and the author-only staging stage no longer exist. Posting is one gate: preview with no flags, explicit `comments.py approve`, then `post_comments.py --post`. Inline and file anchors now create real discussions (`POST .../discussions` with `body` and `position`); MR-level comments keep `POST .../notes` with `body`. The pre-approval status is renamed `draft` → `pending` (legacy values are accepted on read and written back as `pending`), and `update` on an approved comment resets it to `pending`.

### Fixed

- **`glab_json` treats an empty successful write as success.** GitLab answers `204 No Content`; the old parser raised "returned non-JSON output: ''" *after* the note was created, which looked like a failure and invited a duplicate retry. Non-GET responses with an empty body now return `{}`, and a test pins the no-retry behavior.
- **Payload key correctness is enforced by shape.** The removed draft-note builder sent `body` where GitLab required `note`; with the endpoint gone, `/discussions` and `/notes` both take `body`, and the payload tests assert the exact key set.

---

## [1.0.0] - 2026-11-04

### Added

- **Six-phase workflow:** harvest, select, certify, emit, and two independent publish gates. A comment is a claim with evidence, not a thought that survived the conversation.
- **Selection policy:** keep only findings that prevent a reachable defect, break a contract, leave changed behavior untested, create unbounded cost, or were explicitly requested. Everything else is written to `dropped[]` with a reason.
- **`scripts/comments.py`:** the state CLI.
  - `init` (explicit or `--from-mr`), resolving the host, project, IID, base, and `diff_refs`; non-GitLab hosts stop before any comment is generated.
  - `add` validates type, severity, title length, body budget, evidence shape, agreement/confidence rules, suggestion size, duplicates, and the comment budget, then verifies the anchor against `git diff -U3 <base>...HEAD` before writing.
  - `update`, `list` (table and JSON), `verify`, `approve`, `drop`, and `render`.
  - `approve` reuses the triage grammar (`all`, `1, 3`, `skip 2`, `2=APPROVE`) and resets comments that fall out of the new plan.
- **`scripts/verify_anchors.py`:** deterministic diff parsing and anchor verification.
  - Handles omitted hunk counts, multi-hunk diffs, new files, deleted files, renames (including pure renames), and binary diffs.
  - Records a `sha256` of the anchored range; a mismatch is `moved`, never silently accepted.
  - Three anchor kinds: `inline`, `file`, `mr`.
- **`scripts/post_comments.py`:** GitLab transport through `glab api` only.
  - Preview makes zero network calls.
  - `--create` produces author-only draft notes; `--publish` publishes them.
  - Refuses unapproved comments, stale verification, and a HEAD that no longer matches the state, all before the first request.
  - Deduplicates against existing discussions at `path:line` with a 0.9 similarity threshold.
  - Partial batch failures report created draft ids and publish nothing.
- **`mr-comments.md` renderer:** inline and summary modes, severity ordering with MR-level anchors last, collision-safe outer fences, native suggestion blocks, a deterministic footer, and an explicit empty state.
- **Persistent state (`mr-comments-<project>-<iid>.json`):** schema v1 with append-only events, a comment budget, dropped candidates, and per-anchor verification metadata. Never written to a tracked path.
- **`references/comment-model.md`:** schema, anchor kinds, status lifecycle, validation rules, selection policy, privacy rules, and budget semantics.
- **`references/gitlab-recipes.md`:** exact `glab api --input -` payloads for inline, file, and MR-level notes; draft-note lifecycle; dedupe; error table.
- **`references/examples.md`:** four certified comments (`blocker`, `question`, `suggestion`, `test-gap`) and the old LTR comment as a rejected anti-example.
- **Test suite:** 102 stdlib `unittest` cases plus golden fixtures for English, Persian, suggestions, and the empty state. No network or credentials required.

### Design notes

- **JSON first.** The state file, not chat scrollback, is what makes revisions and dedupe possible three turns later.
- **Draft notes are the default staging area.** They are visible only to the author, so a wrong comment can be deleted without notifying the team.
- **`endLine` is display-only.** GitLab's `line_range` payload breaks on rebase and rename; v1 anchors one line and shows the range in prose.
- **Bulk publish is not always safe.** GitLab's bulk endpoint publishes every pending draft, so the script falls back to per-note publishing when the state knows about an unapproved draft.
- **A run with no comments is a valid run.** The dropped table is the evidence that the review happened.
