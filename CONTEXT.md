# CONTEXT.md — Domain Model & Architecture Glossary

## Domain Language

- **Skill**: A modular, specification-compliant agent capability adhering to the open Agent Skills standard (`skills/<name>/SKILL.md`).
- **Review Walkthrough**: An anti-fatigue review companion for a pull request or branch diff, delivering both a compact Markdown summary (`review-walkthrough.md`) and a self-contained, presentation-style HTML companion (`review-walkthrough.html`).
- **Walkthrough Specification**: A structured JSON document (`review-walkthrough.json`) validated against Schema v2 that serves as the single source of truth for all walkthrough deliverables.
- **Walkthrough Compiler**: The deep module in `skills/review-walkthrough/scripts/walkthrough_generator.py` presenting `compile_walkthrough()` as its primary interface. It encapsulates Git metadata enrichment, diff-aware path resolution, schema validation, Markdown rendering, HTML companion injection, and atomic file emission.
- **CompileResult**: The structured result object returned by `compile_walkthrough()`, exposing rendered artifacts (`markdown: str`, `html: str`), the validated specification (`data: dict`), output file paths, and build statistics.
- **CLI Adapter**: The command-line interface in `skills/review-walkthrough/scripts/build-walkthrough.py` that parses shell arguments and invokes the Walkthrough Compiler.
- **Legacy Shim**: The backwards-compatibility adapter in `skills/review-walkthrough/scripts/build-html.py` that translates legacy invocation flags to the Walkthrough Compiler.
