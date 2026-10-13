#!/usr/bin/env python3
"""Build review-walkthrough Markdown and HTML companions from structured JSON.

Usage:
    python3 build-walkthrough.py <walkthrough.json> [--out-dir <dir>]
        [--md <walkthrough.md>] [--html <walkthrough.html>]
        [--editor vscode|cursor|windsurf|zed|android-studio|goland|idea|webstorm|pycharm|copy]
        [--lang fa|en|de|es] [--template <template.html>]

The JSON file is the single source of truth. Both Markdown and HTML are rendered
deterministically in milliseconds with zero regex scraping.
"""

import argparse
import sys
from pathlib import Path

from walkthrough_schema import ValidationError
from walkthrough_generator import CompileError, compile_walkthrough


def main():
    ap = argparse.ArgumentParser(
        description="Render Markdown and HTML review walkthroughs from JSON."
    )
    ap.add_argument("json_file", help="Path to input review-walkthrough.json")
    ap.add_argument(
        "--out-dir",
        help="Directory for output files (defaults to json_file's directory)",
    )
    ap.add_argument("--md", help="Custom output path for Markdown walkthrough")
    ap.add_argument("--html", help="Custom output path for HTML companion")
    ap.add_argument("--editor", help="Default editor / IDE preference")
    ap.add_argument("--lang", help="Override document language")
    ap.add_argument("--base", help="Base branch/commit to query git diff files")
    ap.add_argument(
        "--template",
        help="Path to HTML template",
    )

    args = ap.parse_args()

    input_path = Path(args.json_file).resolve()
    if not input_path.exists():
        print(f"build-walkthrough: error: file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    try:
        res = compile_walkthrough(
            input_path,
            out_dir=args.out_dir,
            md_path=args.md,
            html_path=args.html,
            editor=args.editor,
            lang=args.lang,
            base_ref=args.base,
            template_path=args.template,
            write_files=True,
        )
    except ValidationError as e:
        print(f"build-walkthrough: validation error: {e}", file=sys.stderr)
        sys.exit(1)
    except CompileError as e:
        print(f"build-walkthrough: error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"build-walkthrough: unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

    stats = res.stats
    print(
        f"wrote {res.md_path} and {res.html_path}: {stats['steps']} steps "
        f"({stats['gotchas']} gotchas, {stats['reading_items']} reading items) in {res.elapsed_ms:.1f}ms"
    )


if __name__ == "__main__":
    main()
