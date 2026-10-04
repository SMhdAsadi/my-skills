# Changelog — better-persian

All notable changes to the `better-persian` skill are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this skill adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each release is tagged `better-persian-v<version>` and published on the [Releases page](https://github.com/SMhdAsadi/my-skills/releases).

---

## [1.0.0] - 2026-10-04

Initial release of the lightweight, production-grade Persian language skill for AI coding agents.

### Added
- **Compact specification (`SKILL.md`):** Zero-overhead (~900 token) rule set that prevents agent context dilution while providing complete coverage.
- **Register detection system:** Guidelines for formal-but-human, technical & UI microcopy, administrative, colloquial, and academic registers.
- **De-AI-ing rules:** Explicit bans and transformations for common Persian AI giveaways (copula inflation `می‌باشد`, ceremonial fillers, significance inflation, cliché openers, calqued passives with «توسط», nominal bloat «به صورت»).
- **Technical & UI conventions:** Guidelines for UI buttons/toasts, English software loanwords, and bidirectional inline code spacing.
- **Orthography engine:** Rules for ZWNJ (نیم‌فاصله), native Persian glyphs (`ک` / `ی`), standardized `ه‌ی` ezafe, numeral localization, and Persian quotation guillemets (`«...»`).
- **Factual integrity safeguard:** Prohibits fabricated statistics, claims, and brand metrics.
