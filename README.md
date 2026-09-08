# Agent Skills Collection

[![Agent Skills Standard](https://img.shields.io/badge/Agent%20Skills-Standard-0A84FF?style=flat-square&logo=git&logoColor=white)](https://agentskills.io)
[![Vercel Skills CLI](https://img.shields.io/badge/Vercel%20Skills-CLI%20Compatible-000000?style=flat-square&logo=vercel&logoColor=white)](https://github.com/vercel-labs/skills)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)

A curated collection of production-grade skills for AI coding agents. Adheres strictly to the [Agent Skills standard](https://agentskills.io) and is ready for use across all major agent harnesses including **Vercel Skills CLI (`npx skills`)**, **Claude Code**, **OpenCode**, **OpenAI Codex**, **Cursor**, and **Antigravity**.

---

## Skills Catalog

| Skill | Category | Description | Primary Triggers |
| :--- | :--- | :--- | :--- |
| [`review-walkthrough`](skills/review-walkthrough/) | Code Review / Workflow | Step-by-step interactive code review companion. Maps an optimal foundation-to-leaf reading path through git diffs and guides human reviewers hunk by hunk with targeted spot checks. | *"walk through changes"*, *"review branch"*, *"guided code review"*, *"review diff step by step"* |

---

## Quickstart & Installation

### Option 1: Vercel Skills CLI (`npx skills`)

The fastest way to install skills into your local project or user environment:

```bash
# Install all skills from this repository
npx skills add SMhd/my-skills

# Install only review-walkthrough
npx skills add SMhd/my-skills@review-walkthrough

# Install globally for your user across all projects
npx skills add SMhd/my-skills --global

# Target a specific agent harness (e.g. claude-code, cursor)
npx skills add SMhd/my-skills --agent claude-code
```

> [!TIP]
> You can preview the skills in this repository before installing:
> ```bash
> npx skills add SMhd/my-skills --list
> ```

---

### Option 2: Harness-Specific Setup

#### OpenCode
OpenCode recognizes skills defined in `skills/` or `.opencode/skills/`. To use in an existing project:
```bash
git clone https://github.com/SMhd/my-skills.git /tmp/my-skills
mkdir -p .opencode/skills
cp -r /tmp/my-skills/skills/* .opencode/skills/
```

#### Anthropic Claude Code
Claude Code discovers skills placed in `~/.claude/skills/` (global) or `.claude/skills/` (project-level):
```bash
mkdir -p ~/.claude/skills
git clone https://github.com/SMhd/my-skills.git ~/.claude/skills/my-skills
```

#### Cursor
Cursor references rules via `.cursorrules` or `.cursor/rules/`. The included [`.cursorrules`](.cursorrules) configures Cursor to automatically utilize skills from `skills/`.

#### OpenAI Codex & Generic Agent Harnesses
Codex and other tools utilize [`AGENTS.md`](AGENTS.md) as the central index. Link or copy `skills/` into `~/.agents/skills/` or include `AGENTS.md` in your project root.

#### Google Antigravity / Gemini CLI
Copy or symlink the skill directory to your Antigravity skills path:
```bash
mkdir -p ~/.gemini/config/skills
cp -r skills/review-walkthrough ~/.gemini/config/skills/
```

---

## Repository Structure

```
my-skills/
├── .github/
│   ├── ISSUE_TEMPLATE/       # Structured GitHub issue templates
│   │   ├── bug_report.yml
│   │   └── skill_request.yml
│   └── workflows/
│       └── validate-skills.yml  # Automated CI validation workflow
├── .cursorrules              # Cursor IDE instructions
├── .gitattributes            # Git line endings and file attributes
├── .gitignore                # Clean git exclusion rules
├── AGENTS.md                 # Universal agent context pointer (Codex, OpenCode)
├── CLAUDE.md                 # Claude Code agent configuration
├── LICENSE                   # MIT License
├── README.md                 # Repository catalog and installation documentation
└── skills/
    └── review-walkthrough/   # Interactive code review skill
        ├── SKILL.md          # Agent specification and instructions
        ├── README.md         # Detailed human-facing documentation
        └── references/
            └── review-rubric.md # Heuristic reference for layering & spot checks
```

---

## Adding New Skills

Every skill in this repository must comply with the [Agent Skills standard](https://agentskills.io):

1. **Directory**: Create a new folder under `skills/<skill-name>/`.
2. **`SKILL.md` Specification**:
   - Must contain YAML frontmatter delimited by `---`.
   - `name`: 1–64 characters, lowercase alphanumeric and hyphens (`^[a-z0-9-]+$`).
   - `description`: Up to 1024 characters clearly defining what the skill does and explicit trigger conditions.
   - `license`: SPDX identifier (e.g. `MIT`).
   - `compatibility`: Optional runtime requirements (e.g. `git >= 2.0`).
3. **Progressive Disclosure**:
   - Keep `SKILL.md` focused on operational procedures and completion criteria.
   - Place large reference tables, rubrics, or schemas in `skills/<skill-name>/references/`.
   - Place automation scripts in `skills/<skill-name>/scripts/`.
4. **Validation**: Validate your skill against the specification before submitting a PR.

---

## License

This project is licensed under the [MIT License](LICENSE).
