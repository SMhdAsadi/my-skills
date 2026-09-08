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
    ├── references/              # (Optional) Progressive disclosure reference docs
    ├── scripts/                 # (Optional) Deterministic executable helper scripts
    └── assets/                  # (Optional) Static templates and assets
```

## Available Skills

| Skill | Trigger Keywords | Pointer |
| :--- | :--- | :--- |
| `review-walkthrough` | "walk through changes", "review branch", "guided review", "step-by-step diff" | [`skills/review-walkthrough/SKILL.md`](skills/review-walkthrough/SKILL.md) |

### `review-walkthrough`
- **Purpose**: Interactive, step-by-step code review companion that guides human reviewers through complex diffs chunk by chunk in topological dependency order (foundation to leaf).
- **Activation**: When asked to review changes, conduct a code review walkthrough, or examine a branch diff interactively.
- **Contract**: Inspects git diff, groups hunks logically, presents Step 1 first with targeted reviewer spotlight questions, and waits for user confirmation before advancing.

## Harness Compatibility Guidelines

- **OpenCode**: Skills can be loaded directly from the `skills/` directory or mirrored into `.opencode/skills/`.
- **Codex / Universal Harnesses**: Read the corresponding `SKILL.md` when the user request matches the skill's triggers.
- **Context Management**: Honor progressive disclosure. Do not dump the entire skill instructions into conversation context unless triggered by the user's intent.
