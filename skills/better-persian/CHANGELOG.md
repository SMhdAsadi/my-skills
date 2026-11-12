# Changelog — better-persian

All notable changes to the `better-persian` skill are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this skill adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each release is tagged `better-persian-v<version>` and published on the [Releases page](https://github.com/SMhdAsadi/my-skills/releases).

---

## [2.0.0] - 2026-11-12

Conversational first. The skill no longer polishes chat replies into small formal documents.

### Breaking
- **Default register is now conversation.** Formal Persian (and everything that hangs off it: `هٔ`, `←`, administrative structure, UI imperatives) applies only when explicitly requested or when the user names a formal destination.

### Changed
- **ZWNJ is word-specific, not a blanket prefix rule.** `میشه`, `نمیشه`, `میگم`, `نمیگم`, `میدم`, `نمیدم`, `میره`, `نمیره`, `میاد`, `نمیاد` are written joined; `می‌تونم`, `می‌خوام`, `می‌دونم`, `می‌کنم`, `می‌گیرم`, `می‌فهمم` keep the half-space. A closed exception list beats a rule the model has to guess at.
- **Language mixing mirrors the user.** If they say `کامیت`, the skill says `کامیت`; if they say `commit`, it says `commit`. Default remains English for infrastructure concepts and Persian for everyday nouns.
- **Code comments, commit messages, and technical docs default to English.** Persian only on explicit request.
- **Ezafe split:** `ه‌ی` in chat (`خونه‌ی من`), `هٔ` in formal (`پروژهٔ جدید`), and `ـه` reserved for the copula (`خونه‌ست`).
- **Self-check pass:** three questions before emitting chat text, catching what a ban list misses.

### Added
- **`references/examples.md`:** ten before/after pairs in chat voice, plus a formal contrast.
- **Tone rules:** `تو` by default, no sycophantic openers, no closing offers, emoji only mirrored from the user.
- **Anti-restyle rule:** fix what is wrong; never rewrite a reply that already sounds human.

### Removed
- **Five-register taxonomy** (formal-human / technical-UI / administrative / academic / colloquial), collapsed into conversation and formal.
- **Persian-digit mandate** — numerals are a free choice.
- **`چی‌ست`, `واسه`** — written-only or over-casual forms the skill should not produce.

## [1.2.0] - 2026-10-12

### Added
- **Directional Arrows & Flow rule:** Explicitly mandates leftwards arrow `←` (`U+2190`) for progression and sequential flows in RTL (Persian) text, banning rightwards arrow `→` which points backwards to preceding steps in right-to-left reading order.

## [1.1.0] - 2026-10-04

Refactored and compressed specification for always-on agent context compatibility with zero conversational friction.

### Added
- **Silent Execution contract:** Enforces zero meta-commentary, forbidding changelogs, edit explanations, preambles, and post-hoc justifications in generated output.

### Changed
- **Specification compression:** Reduced `SKILL.md` footprint by ~60% (~500 tokens) using dense operational mappings, eliminating expository prose while preserving all linguistic and orthographic rules.
- **Trigger refinement:** Refined automatic activation description to exempt trivial one-line conversational phrases (e.g. «بله درسته»).

## [1.0.0] - 2026-10-04

Initial release of the lightweight, production-grade Persian language skill for AI coding agents.

### Added
- **Compact specification (`SKILL.md`):** Zero-overhead (~900 token) rule set that prevents agent context dilution while providing complete coverage.
- **Register detection system:** Guidelines for formal-but-human, technical & UI microcopy, administrative, colloquial, and academic registers.
- **De-AI-ing rules:** Explicit bans and transformations for common Persian AI giveaways (copula inflation `می‌باشد`, ceremonial fillers, significance inflation, cliché openers, calqued passives with «توسط», nominal bloat «به صورت»).
- **Technical & UI conventions:** Guidelines for UI buttons/toasts, English software loanwords, and bidirectional inline code spacing.
- **Orthography engine:** Rules for ZWNJ (نیم‌فاصله), native Persian glyphs (`ک` / `ی`), standardized `ه‌ی` ezafe, numeral localization, and Persian quotation guillemets (`«...»`).
- **Factual integrity safeguard:** Prohibits fabricated statistics, claims, and brand metrics.
