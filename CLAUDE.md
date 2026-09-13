# CLAUDE.md

Guidelines for Anthropic Claude Code when working in this repository.

## Project Summary

A multi-harness skills repository providing plug-and-play skills compatible with the [Agent Skills standard](https://agentskills.io), Vercel Skills CLI (`npx skills`), Claude Code, OpenCode, Codex, and Cursor.

## Skill Inventory

- [`skills/review-walkthrough`](skills/review-walkthrough/SKILL.md): Architectural reading plan generator and on-demand review co-pilot — analyzes a branch diff once, writes a dependency-ordered reading plan artifact with line-anchored risk hypotheses, then stays on standby for emergent Q&A while the reviewer reads code in their IDE.

## Working with Skills

1. **Discovery**: Skills live under `skills/<skill-name>/SKILL.md`.
2. **Metadata Standard**: Each `SKILL.md` must have valid YAML frontmatter:
   - `name`: 1–64 characters, lowercase alphanumeric and hyphens only (`^[a-z0-9-]+$`).
   - `description`: 1–1024 characters describing what the skill does and explicit trigger conditions.
   - `license`: SPDX identifier (default `MIT`).
   - `compatibility`: System/runtime requirements (e.g. `git >= 2.0`).
3. **Progressive Disclosure**: Detailed rubric guides, checklists, or reference tables belong under `skills/<skill-name>/references/`, linked from `SKILL.md`.
4. **Validation**: Test any new or modified skills using the validation script in `.github/workflows/validate-skills.yml`.
