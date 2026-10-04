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
| `better-persian` | "better-persian", "better persian", "write in persian", "persian copy", "long-form persian", "متن فارسی", "نامه اداری" | [`skills/better-persian/SKILL.md`](skills/better-persian/SKILL.md) |

### `better-persian`
- **Purpose**: Enforces natural Persian (Farsi) phrasing, register detection, UI microcopy standards, strict orthography (نیم‌فاصله/ZWNJ, Persian glyphs, quotes), and de-AI-ing (stripping robotic bureaucratic clichés).
- **Activation**: When generating or polishing long-form Persian content, articles, documentation, UI microcopy, proposals, or official letters. Does not add overhead to routine conversational Persian chat.
- **Contract**: Self-contained, zero-overhead (~900 token) specification. Evaluates deliverables by appropriate register, applies ZWNJ rules and Persian glyphs, handles technical terminology and inline code spacing, and rewrites banned AI tells (`می‌باشد`, `توسط`, ceremonial filler).

### `review-walkthrough`
- **Purpose**: Anti-fatigue review walkthrough generator and on-demand review co-pilot. Analyzes a branch diff once, writes a compact (~40–60 line), high-signal review walkthrough in everyday spoken developer language (automatically adapting to the user's conversation language) to an ephemeral markdown artifact, then stays on standby to answer reviewer questions while they read the real code in their own IDE.
- **Activation**: When asked to review changes, walk through a branch, examine a branch diff, or generate a review walkthrough for a PR.
- **Contract**: One-shot walkthrough generation with split assessment, gotchas prioritized up front, file-grouped reading order, and verification checklist; passive standby afterward — no turn-by-turn gating, no hunk reveals, no unsolicited sign-offs. Emergent questions are investigated under a both-hypotheses mandate; PR-ready review comments are compiled from logged concerns only on explicit request.


## Harness Compatibility Guidelines

- **OpenCode**: Skills can be loaded directly from the `skills/` directory or mirrored into `.opencode/skills/`.
- **Codex / Universal Harnesses**: Read the corresponding `SKILL.md` when the user request matches the skill's triggers.
- **Context Management**: Honor progressive disclosure. Do not dump the entire skill instructions into conversation context unless triggered by the user's intent.
