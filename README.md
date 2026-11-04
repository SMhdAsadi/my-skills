# Agent Skills Collection

[![Agent Skills Standard](https://img.shields.io/badge/Agent%20Skills-Standard-0A84FF?style=flat-square)](https://agentskills.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)

Skills are instruction packs your AI agent reads when a task matches. No server, no API keys, no configuration — install once and they work in Claude Code, Cursor, Codex, OpenCode, Antigravity, and anything else that reads the [Agent Skills standard](https://agentskills.io).

---

## Install

```bash
npx skills add SMhdAsadi/my-skills
```

That installs every skill and wires them into whichever agents you already have.

```bash
npx skills add SMhdAsadi/my-skills --global              # available in every project
npx skills add SMhdAsadi/my-skills -s mr-comment-triage  # just one skill
```

Prefer to manage files yourself? Each folder under `skills/` is self-contained — copy it into your agent's skills directory and you're done.

---

## The skills

### [Review walkthrough](skills/review-walkthrough/)

You're staring at a branch with fourteen changed files and no obvious place to start. This reads the diff once and hands you a short walkthrough: what actually changed, the two or three spots most likely to bite, and the order to read the files in. Every reference links straight into your editor at the right line. After that it goes quiet and waits for your questions.

> *"Walk me through the changes on this branch."*

### [MR comment triage](skills/mr-comment-triage/)

Nine review comments, and at least two of them contradict each other. This fetches every open thread on a GitHub PR or GitLab MR — self-hosted GitLab included — checks each claim against the real code, and sorts them: accept this, push back on that, this one needs a decision you haven't made yet. You see the whole plan at once and approve it item by item. Nothing is edited, committed, or replied to before that, and replies stay drafts until you explicitly post them.

> *"Triage the review comments on this MR."*

### [To MR comments](skills/to-mr-comments/)

The opposite direction: you have findings, not threads. This turns what you actually agreed on — or what you found in the branch diff — into a small set of GitLab comments that cite the code, sit on a line that still exists, and fit in a thread. It re-checks every anchor at the current commit, collapses duplicates, enforces a budget, and records what it rejected so "no comment" stays auditable. With `glab`, you can stage them as draft notes only you can see, then publish when you're ready.

> *"Turn these findings into MR comments — keep it to five."*

### [Better Persian](skills/better-persian/)

Persian that reads like a person wrote it, not a translation engine. It picks the right register for the job — formal proposal, UI microcopy, casual message — fixes half-spaces, glyphs, and quotation marks, and removes the bureaucratic tells that make machine-written Farsi obvious.

> *"این متن را به فارسی روان بازنویسی کن."*

---

## License

MIT — see [LICENSE](LICENSE).
