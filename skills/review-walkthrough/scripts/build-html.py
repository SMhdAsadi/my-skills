#!/usr/bin/env python3
"""Backwards-compatibility shim for build-html.py.

DEPRECATION NOTICE:
In review-walkthrough v3.0+, generating HTML companions by scraping Markdown
is deprecated. The single source of truth is review-walkthrough.json, and the
primary build script is build-walkthrough.py.

This shim detects if a JSON file is passed and forwards to build-walkthrough.py,
or falls back to legacy markdown handling with a warning.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD_WALKTHROUGH = HERE / "build-walkthrough.py"

if __name__ == "__main__":
    first_arg = next((arg for arg in sys.argv[1:] if not arg.startswith("-")), None)

    # Check if a .json file was passed as first argument
    if first_arg and first_arg.endswith(".json"):
        # Rewrite --out to --html
        new_argv = [sys.executable, str(BUILD_WALKTHROUGH)]
        i = 1
        while i < len(sys.argv):
            if sys.argv[i] == "--out" and i + 1 < len(sys.argv):
                new_argv.extend(["--html", sys.argv[i + 1]])
                i += 2
            else:
                new_argv.append(sys.argv[i])
                i += 1
        res = subprocess.run(new_argv)
        sys.exit(res.returncode)

    # Otherwise warn and check if corresponding json exists for markdown
    print(
        "build-html: warning: building HTML by scraping Markdown is deprecated in v3.0. "
        "Please use build-walkthrough.py with review-walkthrough.json as the source of truth.",
        file=sys.stderr,
    )

    if first_arg and first_arg.endswith(".md"):
        candidate_json = Path(first_arg).with_suffix(".json")
        if candidate_json.exists():
            new_argv = [sys.executable, str(BUILD_WALKTHROUGH), str(candidate_json)]
            i = 1
            while i < len(sys.argv):
                if sys.argv[i] == first_arg:
                    i += 1
                elif sys.argv[i] == "--out" and i + 1 < len(sys.argv):
                    new_argv.extend(["--html", sys.argv[i + 1]])
                    i += 2
                else:
                    new_argv.append(sys.argv[i])
                    i += 1
            res = subprocess.run(new_argv)
            sys.exit(res.returncode)

    print(
        "build-html: error: legacy markdown scraping requires an existing JSON file in v3.0.",
        file=sys.stderr,
    )
    sys.exit(1)
