#!/usr/bin/env python3
"""Shared helpers for the mr-comment-triage scripts.

Everything that touches the filesystem, the shell, or the state schema lives
here so the individual commands stay thin and testable.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
STATE_DIRNAME = "mr-comment-triage"

# Repo-local scratch directories we are willing to use, in preference order.
# `tmp/` is deliberately absent: it is commonly tracked.
SCRATCH_CANDIDATES = (".tmp", "scratch", ".scratch")
# Only this one may be created when it does not exist yet.
CREATABLE_SCRATCH = ".tmp"

VERDICTS = ("ACCEPT", "ALTERNATIVE", "PUSH_BACK", "DEFER", "ALREADY_FIXED", "CLARIFY")
SEVERITIES = ("blocking", "correctness", "maintainability", "nit")
NON_EXECUTABLE = ("CLARIFY", "DEFER")

ITEM_STATUSES = (
    "proposed",
    "approved",
    "rejected",
    "applied",
    "verified",
    "posted",
    "resolved",
    "skipped",
)


class ScriptError(RuntimeError):
    """A failure worth showing the user verbatim, with one actionable next step."""


def now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def run(cmd, *, cwd=None, check=True, env=None):
    """Run a command, raising ScriptError with the first lines of stderr on failure."""
    merged_env = None
    if env:
        merged_env = {**os.environ, **env}
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            env=merged_env,
        )
    except FileNotFoundError as exc:
        raise ScriptError(
            f"`{cmd[0]}` is not installed or not on PATH. Install it or pass a "
            "pasted thread dump instead."
        ) from exc
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()[:6]
        label = " ".join(cmd[:2])
        raise ScriptError(f"`{label}` failed:\n" + "\n".join(detail))
    return proc


def repo_root(start=None) -> Path | None:
    proc = run(["git", "rev-parse", "--show-toplevel"], cwd=start, check=False)
    if proc.returncode != 0:
        return None
    return Path(proc.stdout.strip())


def is_gitignored(root: Path, relpath: str) -> bool:
    proc = run(["git", "check-ignore", "-q", relpath], cwd=root, check=False)
    return proc.returncode == 0


def resolve_state_dir(root: Path | None = None) -> tuple[Path, str]:
    """Pick where the state file lives.

    Order: explicit override, an existing gitignored repo directory, a
    creatable gitignored repo directory, then the system temp directory.
    Never returns a path that git would track.
    """
    override = os.environ.get("MR_TRIAGE_DIR")
    if override:
        target = Path(override).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        return target, "MR_TRIAGE_DIR"

    root = root or repo_root()
    if root is not None:
        for name in SCRATCH_CANDIDATES:
            candidate = root / name
            if candidate.is_dir() and is_gitignored(root, name):
                return candidate, f"repo:{name}"

        creatable = root / CREATABLE_SCRATCH
        if is_gitignored(root, CREATABLE_SCRATCH):
            creatable.mkdir(parents=True, exist_ok=True)
            return creatable, f"repo:{CREATABLE_SCRATCH} (created)"

    target = Path(tempfile.gettempdir()) / STATE_DIRNAME
    target.mkdir(parents=True, exist_ok=True)
    return target, "system-temp"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def state_path(directory: Path, provider: str, repo: str, number: int) -> Path:
    return directory / f"{provider}-{slug(repo)}-{number}.json"


def load_state(path: Path) -> dict:
    if not path.exists():
        raise ScriptError(
            f"No triage state at {path}. Run fetch_threads.py first to collect threads."
        )
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(tmp, path)


def add_event(state: dict, kind: str, detail: str) -> None:
    state.setdefault("events", []).append(
        {"at": now_iso(), "type": kind, "detail": detail}
    )


def find_item(state: dict, number: int) -> dict:
    for item in state.get("items", []):
        if item.get("n") == number:
            return item
    raise ScriptError(
        f"Item #{number} does not exist. Triaged items: "
        f"{[i.get('n') for i in state.get('items', [])] or 'none'}"
    )
