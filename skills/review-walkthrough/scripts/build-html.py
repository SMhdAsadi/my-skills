#!/usr/bin/env python3
"""Backwards-compatibility shim for build-html.py.

DEPRECATION NOTICE:
In review-walkthrough v3.0+, generating HTML companions by scraping Markdown
is deprecated. The single source of truth is review-walkthrough.json, and the
primary build script is build-walkthrough.py.

This shim detects if a JSON file is passed and forwards to build-walkthrough.py,
or falls back to legacy markdown handling with a warning.
"""

import sys
from pathlib import Path

from walkthrough_generator import CompileError, compile_walkthrough
from walkthrough_schema import ValidationError


def main():
    first_arg = next((arg for arg in sys.argv[1:] if not arg.startswith("-")), None)
    out_html = None
    editor = None
    lang = None

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--out" and i + 1 < len(sys.argv):
            out_html = sys.argv[i + 1]
            i += 2
        elif arg == "--editor" and i + 1 < len(sys.argv):
            editor = sys.argv[i + 1]
            i += 2
        elif arg == "--lang" and i + 1 < len(sys.argv):
            lang = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    json_file = None

    if first_arg and first_arg.endswith(".json"):
        json_file = Path(first_arg)
    elif first_arg and first_arg.endswith(".md"):
        print(
            "build-html: warning: building HTML by scraping Markdown is deprecated in v3.0. "
            "Please use build-walkthrough.py with review-walkthrough.json as the source of truth.",
            file=sys.stderr,
        )
        candidate = Path(first_arg).with_suffix(".json")
        if candidate.exists():
            json_file = candidate
        else:
            print(
                "build-html: error: legacy markdown scraping requires an existing JSON file in v3.0.",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        print("build-html: error: missing input walkthrough file", file=sys.stderr)
        sys.exit(1)

    try:
        compile_walkthrough(
            json_file,
            html_path=out_html,
            editor=editor,
            lang=lang,
            write_files=True,
        )
    except (ValidationError, CompileError) as e:
        print(f"build-html: error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
