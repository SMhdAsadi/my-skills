# Changelog — review-walkthrough

All notable changes to the `review-walkthrough` skill are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this skill adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each release is tagged `review-walkthrough-v<version>` and published on the [Releases page](https://github.com/SMhdAsadi/my-skills/releases).

---

## [2.1.2] - 2026-09-28

### Fixed
- **Heading and label localization:** Eliminated hardcoded English section headings (`Review Walkthrough`, `Affects:`, `The Gist`, `Heads Up`, `Suggested Reading Order`, `Skim:`, `What to Test`) and bilingual parenthetical hybrids in non-English walkthroughs. Added a multilingual reference table for standard titles and labels across languages.
- **RTL layout integrity:** Guaranteed that headings and metadata labels in RTL languages (Persian, Arabic, Hebrew) begin with native RTL terms to prevent markdown renderers from forcing LTR paragraph direction and breaking text alignment or punctuation.
- **Technical term clarity:** Explicitly preserved English formatting for code symbols, identifiers, branch names, and native framework terms while fully localizing structural chrome.

## [2.1.1] - 2026-09-28

Unified skill terminology strictly around **"review walkthrough"**:
- Replaced lingering references to *"Architectural Reading Plan"*, legacy *"plan"*, and *"review guide"* across `SKILL.md`, `README.md`, Mermaid lifecycle diagrams, and repository documentation with **"review walkthrough"**.
- Aligned trigger keywords and catalog descriptions across `AGENTS.md`, `README.md`, and `CLAUDE.md`.

## [2.1.0] - 2026-09-28

Anti-fatigue and pragmatic redesign to streamline human review speed and eliminate reading exhaustion.

### Changed
- **Anti-fatigue guide format:** Replaced bloated academic reports with a lean, compact (~40–60 line) review guide. Removed formal disclaimer banners, 40-character commit hash tables, and ASCII box trees.
- **Conversational tone:** Swapped stiff enterprise jargon (*"Executive Context & Invariant Delta"*, *"Topological Itinerary"*, *"Tier-1 Grounded Blast Radius"*) for natural, everyday spoken developer phrasing.
- **Language-agnostic adaptation:** The review guide automatically adapts to the user's conversation language (German, Persian, Spanish, etc.) with zero hardcoded language constraints.
- **Gotchas prioritized up front:** Surfaced 2–4 line-anchored gotchas and edge cases immediately below the 2-sentence summary so reviewers spot traps before diving into the diff.
- **File-grouped reading order:** Consolidated fragmented per-line checklist bullets into single-file entries with clickable links. Merged skimmable files into a single footer line rather than a separate markdown table.

## [2.0.0] - 2026-09-13

A ground-up redesign: the skill no longer walks the reviewer through a diff turn by turn in chat. It now generates a one-shot **Architectural Reading Plan** as a markdown artifact, then stays on standby as an on-demand review co-pilot while the human reads real code in their own IDE.

### Changed (breaking)
- **Interaction model replaced.** Turn-by-turn conversational gating (`next` / `skip` / `jump` pacing signals) is gone. The agent generates the full plan in one shot, posts a short briefing, and waits for the reviewer to drive.
- **No more in-chat hunk reveals.** The plan orients; the reviewer reads complete, untrimmed code in their native editor or diff viewer. This removes the selection bias of agent-trimmed hunks.
- **Sign-off recap is no longer automatic.** Concerns raised during the review are logged silently and compiled into a PR-ready comment block only on explicit request.

### Added
- **Split recommendation**: oversized diffs (>15 files or >800 lines) open with an explicit recommendation to split the PR, with a suggested boundary — the plan still covers diffs that cannot be split.
- **Progressive tooling tiers**: uses graph/structural MCP tools (`search_graph`, `trace_path`, ...) when available; degrades to git/grep heuristics otherwise, with heuristic claims labeled as such.
- **Ephemeral plan storage**: harness artifact dir → git-ignored repo temp dir (verified with `git check-ignore`) → system temp. The plan is never committed.
- **Epistemic guardrails**: advisory header on every plan, risk items phrased as open questions, and an anchoring rule requiring a verifiable `file:line` for every substantive claim.
- **Verification & testing blind spots** section: what automated tests cover vs. what requires manual verification.
- **Lower-risk skimmable files** section: generated/boilerplate files, each with a rationale and a verification pointer.
- **Both-hypotheses investigation protocol** for emergent Q&A, with an optional neutral research-subagent dispatch template and a no-subagent fallback.
- **Plan scaling rules**: small diffs get compact plans; ceremony is never generated beyond what the diff warrants.

## [1.0.0] - 2026-09-08

### Added
- Initial release: interactive, step-by-step code review companion.
- Diff inspection with base-ref resolution and pinned `HEAD` staleness detection.
- Mental-model briefing (executive summary, system footprint, risk radar).
- Topological reading roadmap, foundation to leaf (schemas → domain logic → I/O → UI → tests).
- Turn-by-turn walkthrough with trimmed key hunks and line-anchored reviewer spotlight questions.
- Sign-off recap aggregating concerns logged during the walkthrough.

---

[2.1.2]: https://github.com/SMhdAsadi/my-skills/releases/tag/review-walkthrough-v2.1.2
[2.1.1]: https://github.com/SMhdAsadi/my-skills/releases/tag/review-walkthrough-v2.1.1
[2.1.0]: https://github.com/SMhdAsadi/my-skills/releases/tag/review-walkthrough-v2.1.0
[2.0.0]: https://github.com/SMhdAsadi/my-skills/releases/tag/review-walkthrough-v2.0.0
[1.0.0]: https://github.com/SMhdAsadi/my-skills/releases/tag/review-walkthrough-v1.0.0
