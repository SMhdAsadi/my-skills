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
3. Tag the commit `<skill-name>-v<version>` (e.g., `review-walkthrough-v2.0.0`) and create a matching GitHub Release with the changelog notes — this is what surfaces on the repo's Releases page.

## Available Skills

| Skill | Trigger Keywords | Pointer |
| :--- | :--- | :--- |
| `review-walkthrough` | "walk through changes", "review branch", "guided review", "review walkthrough for diff" | [`skills/review-walkthrough/SKILL.md`](skills/review-walkthrough/SKILL.md) |
| `review-english` | "review English", "/review-english", "English mistakes in my AI chats", "practice English from my prompts" | [`skills/review-english/SKILL.md`](skills/review-english/SKILL.md) |

### `review-walkthrough`
- **Purpose**: Anti-fatigue review walkthrough generator and on-demand review co-pilot. Analyzes a branch diff once, writes a compact (~40–60 line), high-signal review walkthrough in everyday spoken developer language (automatically adapting to the user's conversation language) to an ephemeral markdown artifact, then stays on standby to answer reviewer questions while they read the real code in their own IDE.
- **Activation**: When asked to review changes, walk through a branch, examine a branch diff, or generate a review walkthrough for a PR.
- **Contract**: One-shot walkthrough generation with split assessment, gotchas prioritized up front, file-grouped reading order, and verification checklist; passive standby afterward — no turn-by-turn gating, no hunk reveals, no unsolicited sign-offs. Emergent questions are investigated under a both-hypotheses mandate; PR-ready review comments are compiled from logged concerns only on explicit request.

### `review-english`
- **Purpose**: Audits a Persian-speaking developer's everyday English from real AI-assistant chats; renders a local weekly report with top error patterns and Persian mental-model explanations (v0.1.0 "The Report").
- **Activation**: When asked to review English, walk through English mistakes in AI chats, or generate an English practice report.
- **Contract**: Deterministic scripts do extraction/redaction/sampling/rendering; the agent does ALL linguistic work via versioned JSON (`extracted_prompts.json` → `analysis.json`). 100% local, no network. See `skills/review-english/PROGRESS.md` for the rollout plan (v0.2 drills+SRS, v0.3 habit loop, v0.4 second adapter).

## Harness Compatibility Guidelines

- **OpenCode**: Skills can be loaded directly from the `skills/` directory or mirrored into `.opencode/skills/`.
- **Codex / Universal Harnesses**: Read the corresponding `SKILL.md` when the user request matches the skill's triggers.
- **Context Management**: Honor progressive disclosure. Do not dump the entire skill instructions into conversation context unless triggered by the user's intent.
