# Changelog — review-walkthrough

All notable changes to the `review-walkthrough` skill are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this skill adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each release is tagged `review-walkthrough-v<version>` and published on the [Releases page](https://github.com/SMhdAsadi/my-skills/releases).

---

## [3.0.0] - 2026-10-11

### Added
- **JSON-first architecture:** `review-walkthrough.json` (Schema v2) is now the single source of truth for all walkthrough deliverables. Both the Markdown walkthrough and the companion HTML file are compiled deterministically in forward generation.
- **Forward generator script (`scripts/build-walkthrough.py`):** Compiles `review-walkthrough.json` into both `.md` and `.html` in milliseconds, with strict schema validation and diff-aware path resolution (`git diff --name-only`).
- **Multi-IDE support:** Top-bar editor switcher supporting **VS Code**, **Cursor**, **Windsurf**, **Zed** (`zed://file/...`), and **JetBrains** (`idea://open?...`), plus a **Copy Only** mode. Active editor is persisted in `localStorage["rw-editor"]`.
- **1-Click Copy Path (`.cp-btn`):** Dedicated copy button on every reference pill that copies repo-relative `path:line` to the clipboard with visual confirmation feedback.
- **Dedicated reference pills:** Gotcha file references are displayed in dedicated `.ref-pill` rows, keeping body prose 100% human and conversational without sentence-flipping parenthesized path prefixes.
- **Scrollable reading checklist:** Reading orders with more than 6 files render inside a scrollable checklist container (`.chk-list`) with styled scrollbars to maintain viewport budget.

### Changed
- **Ultra-lean offline footprint:** Removed the 78 KB base64 embedded font blob from `assets/walkthrough-template.html`. Asset size reduced from ~90.6 KB to ~23.7 KB (~74% reduction). Persian font uses `local("Vazirmatn")` and native Arabic/Persian system UI stacks, strictly scoped to `[lang="fa"]`.
- **Pure conversational prose:** Gotcha bodies and reading summaries are validated to ensure they contain pure prose without parenthesized file:line mentions.
- **Unblocked checkbox interaction:** Native checklist checkboxes are excluded from card keyboard navigation traps, allowing reviewers to toggle checks with the Spacebar without triggering step navigation.
- **Universal generation:** Both Markdown and HTML companions are generated simultaneously on every run without fast-path skips.

### Fixed
- **Basename path ambiguity:** File references are resolved against `git diff --name-only` rather than full repository walk, avoiding false matches and directory ambiguity.
- **Backwards compatibility:** `scripts/build-html.py` delegates seamlessly to `build-walkthrough.py` when invoked directly.

---

## [2.4.2] - 2026-10-11

### Changed
- **Generic test card title:** the test step now uses a short count-based line ("Run these 3 checks on a device.", localized) instead of keyword extraction, which echoed the items and wrapped like a truncated fourth bullet.

## [2.4.1] - 2026-10-11

### Fixed
- **Broken editor links:** the builder now expands `~` in the repo root (editors cannot resolve a literal `~` in `file://` URLs) and resolves basename-only refs to full repo-relative paths via `git ls-files` (single match wins; ambiguous names stay short and render as plain spans instead of dead links).
- **Inline filenames open the real file:** bare `basename:line` mentions in prose resolve against the walkthrough's known paths, so the inline link target is always the full path.
- **Footnotes gone when inline covers them:** a ref already linked inline in the same card no longer gets a duplicate footnote below. Each file appears exactly once per card — inline when mentioned, footnote otherwise.
- **Full paths shortened, not deleted:** parenthesized `(src/a/Bar.tsx:35):` mentions become `(Bar.tsx:35):` in the prose, which renders as the inline link.

## [2.4.0] - 2026-10-11

### Changed
- **One Light / One Dark Pro theme:** the HTML companion now follows the One editor palettes — One Light in light mode, One Dark Pro in dark mode — with green (`--add`) / red (`--del`) diff stats and yellow (`--warn`) gotcha markers.
- **Two-line header:** source/target branches render as separate tags on their own line; file counts and green `+added` / red `−removed` stats move to a second line.
- **Short file links:** refs display as `basename:line` (full path in the tooltip), with automatic `…/parent/basename` disambiguation when two files share a name. The copy-path button is gone — links need no backup.
- **No more truncation:** the builder keeps full body/summary/test text; title cap raised 120 → 160 chars and cards grow instead of cutting mid-word.
- **Synthesized card titles:** scope shows the diff shape (small/medium/large), reading shows `Read in order: role1 → role2 …`, tests show `Verify: keyword1 · keyword2 …` — no card repeats its first item anymore.
- **Quieter chrome:** icon-only System/Light/Dark toggle (monitor/sun/moon), single-chevron Previous/Next with no `<kbd>` duplicates, auto-height cards, 24px progress touch targets, footer shows only the markdown basename.
- **Status dots:** `added`/`deleted` refs get a small green/red dot; inline `path:line` mentions in prose are linkified instead of repeated as raw text.

### Fixed
- **Prose path duplication:** parenthesized `(path:line)` mentions (including markdown-link form) are stripped from card prose since the structured ref below already links them.
- **Affects misparsing:** the builder now matches the localized Affects label instead of grabbing the first bold line (which was the scope bar).
- **Skim detection:** Persian (`بررسی گذرا`), German, and Spanish skim labels are recognized again.

## [2.3.0] - 2026-10-11

### Changed
- **HTML fast-path:** small diffs (≤5 files and ≤200 changed lines) are now markdown-only by default. The HTML companion builds automatically only for larger diffs, or whenever the user explicitly asks for it.
- **Scripted HTML build:** new `scripts/build-html.py` parses the finished markdown into the template's JSON block and validates the contract. Agents never open the ~90 KB template in context and never hand-write JSON — one script call replaces the read/copy/escape/validate loop.
- **Verification checklist removed:** the light/dark screenshot pass, font proof, and editor-link click-throughs are gone (they cost minutes and were always skipped in practice). The only check is the builder's exit code: JSON parses and step order/counts match the markdown.
- **Slimmer mandatory reads:** markdown-only runs never open the HTML spec. HTML runs need only its Sections 2–3 (data contract, editor links); the template's standby investigation template lives in the rubric and is read only during Q&A.
- **Bounded investigation:** small diffs use `git diff` plus at most ~3 targeted file reads with no graph-tool calls. Graph tools are reserved for larger or architecturally unclear diffs, capped at ~3 calls. Split assessment is one sentence unless the diff is massive.
- **Storage order flipped for openability:** repo gitignored temp dir first (preferred home for HTML, opened manually in a browser), harness artifact dir second and only when the artifact type renders there (markdown previews inline, HTML does not), system temp last. Markdown and HTML may live in different directories — each goes where it opens fastest.
- **Chat briefing** drops the "checks I could not run" line; the HTML line now only says where it is or why it was skipped.

## [2.2.0] - 2026-10-11

### Added
- **HTML companion:** After writing the markdown walkthrough, the skill now generates a self-contained, card-based HTML version of the same content (one card per step: scope, optional split recommendation, one card per gotcha, a checkable reading list, tests). Generated by default; skipped when the user asks for markdown only.
- **Editor links:** Every `file:line` reference in the HTML opens the file at that line in the user's editor (`vscode://file/...`, plus Cursor, Windsurf, VSCodium, Insiders, and remote/WSL variants), with a copy-path button as fallback. The repo root comes from `git rev-parse --show-toplevel`.
- **Theming:** The HTML follows the OS light/dark setting with a System / Light / Dark override, a neutral token-based palette, and a print stylesheet.
- **Static template shipped:** `assets/walkthrough-template.html` is a single self-contained file (about 90 KB, Vazirmatn subset embedded) with a built-in renderer and validator. It follows the data contract exactly and shows an error card on invalid data.
- **Language rule:** the HTML uses the language of the user's first prompt, the same as the markdown. The template has built-in English and Persian strings and accepts a `ui` object for any other language; direction, digits, and font follow `lang`.
- **Full RTL and Persian support:** Embedded Vazirmatn (base64, works offline), logical-property layout, direction-aware chevrons and keyboard shortcuts, bidi isolation for Latin identifiers and paths, Persian digits and orthography rules, and a fixed Persian UI string table aligned with the markdown labels.
- **Data/template separation:** The skill writes only a validated JSON block; the template (markup, CSS, JS, fonts) is static, so output cannot drift between runs. The JSON is rendered with `textContent` and `<` is escaped, so review text can never inject markup.
- **New reference `references/html-walkthrough.md`:** The full HTML spec (design tokens, wording and register, font embedding, RTL rules, JSON schema with validation rules, editor-link construction, verification checklist).
- **New rubric section (Section 4):** Content-shaping rules for the HTML: same facts as the markdown, card budgets, gotcha category mapping, and an explicit ban on inventing severity, fixes, snippets, or evidence the walkthrough does not contain.

### Changed
- **Chat briefing** now also reports the HTML path (or why it was skipped) and any verification checks that could not be run; limit raised from 3–5 to 3–6 lines.
- **Staleness handling** regenerates the markdown and the HTML together, and notes that editor links open the working tree.
- **Fail-safe behavior:** If the HTML cannot be produced correctly (validation failure, or a missing template), the skill skips it and keeps the markdown as the deliverable instead of shipping a half-built or fallback-font file.

### Notes
- The markdown walkthrough keeps its spoken developer voice. The Persian HTML uses a formal-but-readable register defined in `references/html-walkthrough.md` (Section 4); facts, anchors, and order are identical.

## [2.1.3] - 2026-09-28

### Fixed
- **RTL Scope bar and Reading Order formatting:** Added `**Branch Label**` (`**برنچ:**` in Persian) to the Scope bar and defined an explicit role-first format for Suggested Reading Order checklist items (`- [ ] **<Role>** ([file:line](#)): <Summary>`). This ensures the first strong character on every line is native, preventing markdown renderers from resolving list items or the branch summary into LTR.
- **Technical terms and developer vocabulary:** Clarified that technical terms, protocols, and acronyms (WebRTC, ICE, REST, API) must stay in Latin script without phonetic transliteration (avoiding awkward transliterations like وب‌آرتی‌سی or استیل), while clarifying that backticks are optional for acronyms in prose. Standardized everyday developer vocabulary (e.g. preferring برنچ over unfamiliar translations like شاخه).

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

[2.4.2]: https://github.com/SMhdAsadi/my-skills/releases/tag/review-walkthrough-v2.4.2
[2.4.1]: https://github.com/SMhdAsadi/my-skills/releases/tag/review-walkthrough-v2.4.1
[2.4.0]: https://github.com/SMhdAsadi/my-skills/releases/tag/review-walkthrough-v2.4.0
[2.3.0]: https://github.com/SMhdAsadi/my-skills/releases/tag/review-walkthrough-v2.3.0
[2.2.0]: https://github.com/SMhdAsadi/my-skills/releases/tag/review-walkthrough-v2.2.0
[2.1.3]: https://github.com/SMhdAsadi/my-skills/releases/tag/review-walkthrough-v2.1.3
[2.1.2]: https://github.com/SMhdAsadi/my-skills/releases/tag/review-walkthrough-v2.1.2
[2.1.1]: https://github.com/SMhdAsadi/my-skills/releases/tag/review-walkthrough-v2.1.1
[2.1.0]: https://github.com/SMhdAsadi/my-skills/releases/tag/review-walkthrough-v2.1.0
[2.0.0]: https://github.com/SMhdAsadi/my-skills/releases/tag/review-walkthrough-v2.0.0
[1.0.0]: https://github.com/SMhdAsadi/my-skills/releases/tag/review-walkthrough-v1.0.0