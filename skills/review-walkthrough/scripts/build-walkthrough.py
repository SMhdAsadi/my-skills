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
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = HERE.parent / "assets" / "walkthrough-template.html"

from walkthrough_schema import ValidationError, validate_walkthrough
from walkthrough_generator import (
    render_html,
    render_markdown,
    resolve_paths_against_diff,
)


def git(root: str, *args: str) -> str:
    try:
        cmd = ["git"]
        if root:
            cmd.extend(["-C", root])
        cmd.extend(args)
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def main():
    start_time = time.perf_counter()

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
        default=str(DEFAULT_TEMPLATE),
        help="Path to HTML template",
    )

    args = ap.parse_args()

    input_path = Path(args.json_file).resolve()
    if not input_path.exists():
        print(f"build-walkthrough: error: file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"build-walkthrough: error: invalid JSON in {input_path}: {e}", file=sys.stderr)
        sys.exit(1)

    if args.lang:
        data["lang"] = args.lang

    meta = data.setdefault("meta", {})
    repo = data.setdefault("repo", {})

    if args.editor:
        repo["defaultEditor"] = args.editor

    # Git enrichment if missing
    repo_root = repo.get("root") or git("", "rev-parse", "--show-toplevel")
    if repo_root:
        repo_root = os.path.abspath(os.path.expanduser(repo_root))
        repo["root"] = repo_root

    if not meta.get("headSha") or meta.get("headSha") == "HEAD":
        head = git(repo_root, "rev-parse", "--short", "HEAD")
        if head:
            meta["headSha"] = head

    # Diff-aware path resolution
    base_ref = args.base or meta.get("base")
    if repo_root and base_ref:
        diff_out = git(repo_root, "diff", "--name-only", f"{base_ref}...HEAD")
        if not diff_out:
            diff_out = git(repo_root, "diff", "--name-only", base_ref)
        if diff_out:
            diff_files = diff_out.splitlines()
            data = resolve_paths_against_diff(data, diff_files)

    # Validate against Schema v2
    try:
        data = validate_walkthrough(data)
    except ValidationError as e:
        print(f"build-walkthrough: validation error: {e}", file=sys.stderr)
        sys.exit(1)

    # Determine output destinations
    out_dir = Path(args.out_dir).resolve() if args.out_dir else input_path.parent
    stem = input_path.stem
    if stem.endswith(".json"):
        stem = stem[:-5]

    md_path = Path(args.md).resolve() if args.md else out_dir / f"{stem}.md"
    html_path = Path(args.html).resolve() if args.html else out_dir / f"{stem}.html"

    # Store resolved markdown path in metadata
    data["meta"]["markdownPath"] = str(md_path)

    # Render Markdown
    md_content = render_markdown(data)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_content, encoding="utf-8")

    # Render HTML
    tpl_path = Path(args.template)
    if not tpl_path.exists():
        print(f"build-walkthrough: error: template not found: {tpl_path}", file=sys.stderr)
        sys.exit(1)

    template_content = tpl_path.read_text(encoding="utf-8")
    try:
        html_content = render_html(data, template_content)
    except Exception as e:
        print(f"build-walkthrough: error rendering HTML: {e}", file=sys.stderr)
        sys.exit(1)

    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html_content, encoding="utf-8")

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    steps = data["steps"]
    gotchas = sum(1 for s in steps if s["kind"] == "gotcha")
    reading_items = sum(
        len(s.get("items", [])) for s in steps if s["kind"] == "reading"
    )

    print(
        f"wrote {md_path} and {html_path}: {len(steps)} steps "
        f"({gotchas} gotchas, {reading_items} reading items) in {elapsed_ms:.1f}ms"
    )


if __name__ == "__main__":
    main()
