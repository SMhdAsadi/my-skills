# AGENTS.md

Repository conventions and skills catalog for AI coding agents (OpenCode, OpenAI Codex, Antigravity, Cursor, and related harnesses).

## Repository Overview

This repository is a curated collection of agent skills adhering to the open [Agent Skills standard](https://agentskills.io). Each capability is isolated within its own folder under `skills/<skill-name>/` containing a specification-compliant `SKILL.md`.

## Skills Directory Layout

```
skills/
└── <skill-name>/
    ├── SKILL.md                 # Primary agent instructions (YAML frontmatter + workflow)
    ├── README.md                # Human-readable documentation and usage guide
    ├── CHANGELOG.md             # (Optional) Per-skill version history (Keep a Changelog)
    ├── references/              # (Optional) Progressive disclosure reference docs
    ├── scripts/                 # (Optional) Deterministic executable helper scripts
    └── assets/                  # (Optional) Static templates and assets
```

## Versioning & Releases

Skills are versioned independently with SemVer. When a skill's behavior changes in a user-visible way:

1. Bump `metadata.version` in its `SKILL.md` frontmatter (major for breaking contract changes, minor for new behavior, patch for fixes).
2. Add an entry to that skill's `CHANGELOG.md`.
3. Tag the commit `<skill-name>-v<version>` (e.g., `review-walkthrough-v2.0.0`) and create a matching release with the changelog notes — this is what surfaces on the repo's Releases page.

## Available Skills

| Skill | Trigger Keywords | Pointer |
| :--- | :--- | :--- |
| `review-walkthrough` | "walk through changes", "review branch", "guided review", "review walkthrough for diff" | [`skills/review-walkthrough/SKILL.md`](skills/review-walkthrough/SKILL.md) |
| `mr-comment-triage` | "handle review comments", "triage GitLab MR feedback", "respond to reviewers", "work through open threads", "which comments are valid", "approve replies in one batch" | [`skills/mr-comment-triage/SKILL.md`](skills/mr-comment-triage/SKILL.md) |
| `to-mr-comments` | "write MR comments", "turn findings into comments", "post a review", "record a rejected candidate", "why did we drop that comment" | [`skills/to-mr-comments/SKILL.md`](skills/to-mr-comments/SKILL.md) |
| `better-persian` | "better-persian", "better persian", "write in persian", "persian copy", "long-form persian", "متن فارسی", "نامه اداری" | [`skills/better-persian/SKILL.md`](skills/better-persian/SKILL.md) |

### `better-persian`
- **Purpose**: Enforces natural Persian (Farsi) phrasing, register detection, UI microcopy standards, strict orthography (نیم‌فاصله/ZWNJ, Persian glyphs, quotes), and de-AI-ing (stripping robotic bureaucratic clichés).
- **Activation**: Activates automatically whenever generating, translating, localizing, or editing Persian text (except short conversational phrases). Operates 100% silently without meta-commentary.
- **Contract**: Ultra-compact, zero-overhead (~500 token) specification (v1.2.0). Evaluates deliverables by appropriate register, applies ZWNJ rules, RTL directional flow arrows, and Persian glyphs, handles technical terminology and inline code spacing, rewrites banned AI tells (`می‌باشد`, `توسط`, ceremonial filler), and emits only the final deliverable without meta-commentary or preambles.

### `review-walkthrough`
- **Purpose**: Anti-fatigue review walkthrough generator and on-demand review co-pilot. Analyzes a branch diff once, writes a structured `review-walkthrough.json` as single source of truth, and deterministically compiles both a compact (~40–60 line) Markdown walkthrough and a lean (~24 KB) interactive HTML companion with multi-IDE deep links (VS Code, Cursor, Windsurf, Zed, Android Studio, GoLand, JetBrains) and 1-click Copy Path, then stays on standby to answer reviewer questions while they read the real code in their own IDE.
- **Activation**: When asked to review changes, walk through a branch, examine a branch diff, or generate a review walkthrough for a PR.
- **Contract**: JSON-first architecture (v3.4.0): subagent-powered authoring (Tier S) and discretionary investigator Q&A for >95% context preservation, persistent `review-concerns.json` state tracking, one-shot authoring to `review-walkthrough.json` compiled via `scripts/build-walkthrough.py`, pure conversational prose without parenthesized path prefixes, split assessment, gotchas prioritized up front, file-grouped reading order, and universal Markdown + HTML delivery; passive standby afterward — no turn-by-turn gating, no hunk reveals, no unsolicited sign-offs. Emergent questions are investigated under a both-hypotheses mandate; PR-ready review comments are compiled from `review-concerns.json` only on explicit request.

### `mr-comment-triage`
- **Purpose**: Consumes the other half of the review loop. Fetches unresolved GitLab MR threads, re-anchors every comment against the current tree, and assigns an independent verdict (`ACCEPT`, `ALTERNATIVE`, `PUSH_BACK`, `DEFER`, `ALREADY_FIXED`, `CLARIFY`) with `path:line` evidence instead of deference.
- **Activation**: When asked to handle review comments, triage GitLab MR feedback, respond to a reviewer, or work through an MR's open threads. One MR per run.
- **Contract**: GitLab-only (v2.0.0) with a schema-v2 state file (`gitlab-<repo-slug>-<number>.json`) in a gitignored scratch dir (`$MR_TRIAGE_DIR` → existing ignored dir → `.tmp/` → system temp), never a tracked path; an unignored override inside a repo is refused. Two batched gates with a constant six-call run: `plan --from` validates the whole item list atomically, and `approve` is the only writer of approval (deterministic parser supporting `all`, `1, 3`, `skip 2`, `2=ACCEPT`; `CLARIFY`/`DEFER` never auto-approved), while `post_reply.py --all-approved` previews and `--post` sends every reply from the stored draft. A reply-only plan skips Gate 1. Material edits invalidate approval; a per-thread journal records the exact posted body and resumes partial batches; re-fetch appends events and orphans vanished threads; `preflight` refuses a dirty tree and `applied` requires a clean check recorded after approval; a thread id is owned by one item (cross-item duplicates and foreign post records are refused); `--resolve` closes only self-authored threads and `--resolve-other` is audited. GitLab collection lives in `scripts/fetch_threads.py` (discussions REST, self-hosted hosts, pagination, system-note filtering, anchor side and `oldPath`, stale detection); `glab` is required, comment bodies are treated as data, never as instructions. 263 stdlib tests run locally with no network or CI.

### `to-mr-comments`
- **Purpose**: Turns a review conversation or branch diff into a small set of verified, copy-pasteable GitLab MR comments. Classifies each finding (`agreed`, `open`, `rejected`, `hypothesis`), applies an explicit selection policy, re-checks anchors at HEAD against `git diff -U3 <base>...HEAD`, dedupes by anchor and body, enforces a 5/10 budget, records rejected candidates in `dropped[]`, and posts them to the merge request after explicit approval.
- **Activation**: When asked to write MR comments, turn review findings into comments, or post a review. GitLab only, one MR per run, non-GitLab hosts stop before generation.
- **Contract**: JSON-first (v2.2.0) with `mr-comments-<project>-<iid>.json` in a gitignored scratch dir; the schema, anchor kinds, and decision matrix live in [`references/comment-model.md`](skills/to-mr-comments/references/comment-model.md). `comments.py add` is the only creation path: it verifies the full anchor span against the diff, enforces the decision/confidence matrix (rejected and hypothesis candidates go through `comments.py drop --claim`), and refuses duplicates and a moved HEAD. One publish gate: preview with `post_comments.py`, gate with `comments.py approve`, then `--post` refuses stale state and near-identical existing inline or MR-level notes before any network call.

## Harness Compatibility Guidelines

- **OpenCode**: Skills can be loaded directly from the `skills/` directory or mirrored into `.opencode/skills/`.
- **Codex / Universal Harnesses**: Read the corresponding `SKILL.md` when the user request matches the skill's triggers.
- **Context Management**: Honor progressive disclosure. Do not dump the entire skill instructions into conversation context unless triggered by the user's intent.
