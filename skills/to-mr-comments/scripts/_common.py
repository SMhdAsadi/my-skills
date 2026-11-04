#!/usr/bin/env python3
"""Shared helpers for the to-mr-comments scripts.

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
STATE_DIRNAME = "to-mr-comments"

# Repo-local scratch directories we are willing to use, in preference order.
# `tmp/` is deliberately absent: it is commonly tracked.
SCRATCH_CANDIDATES = (".tmp", "scratch", ".scratch")
# Only this one may be created when it does not exist yet.
CREATABLE_SCRATCH = ".tmp"

SEVERITIES = ("blocking", "correctness", "maintainability", "nit")
SEVERITY_ORDER = {"blocking": 0, "correctness": 1, "maintainability": 2, "nit": 3}
TYPES = ("blocker", "question", "suggestion", "follow-up", "test-gap")
STATUSES = ("draft", "approved", "dropped", "posted")
DECISIONS = ("agreed", "open", "rejected", "hypothesis")
CONFIDENCES = ("high", "medium", "low")
SOURCES = ("conversation", "diff")
ANCHOR_KINDS = ("inline", "file", "mr")

EVENT_KINDS = (
    "created",
    "updated",
    "verified",
    "approved",
    "dropped",
    "draft-created",
    "published",
    "skipped-duplicate",
)

BUDGET_TARGET = 5
BUDGET_MAX = 10

_REMOTE_PATTERNS = (
    re.compile(r"^git@(?P<host>[^:]+):(?P<path>.+?)(?:\.git)?$"),
    re.compile(r"^ssh://[^@/]+@(?P<host>[^:/]+)(?::\d+)?/(?P<path>.+?)(?:\.git)?$"),
    re.compile(r"^https?://(?:[^@/]+@)?(?P<host>[^/]+)/(?P<path>.+?)(?:\.git)?/?$"),
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


def run(cmd, *, cwd=None, check=True, env=None, input_text=None):
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
            input=input_text,
        )
    except FileNotFoundError as exc:
        raise ScriptError(
            f"`{cmd[0]}` is not installed or not on PATH. Install it and try again."
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
    candidates = [relpath]
    if not relpath.endswith("/"):
        candidates.append(relpath + "/")
    for candidate in candidates:
        proc = run(["git", "check-ignore", "-q", candidate], cwd=root, check=False)
        if proc.returncode == 0:
            return True
    return False


def resolve_state_dir(root: Path | None = None) -> tuple[Path, str]:
    """Pick where the state file lives.

    Order: explicit override, an existing gitignored repo directory, a
    creatable gitignored repo directory, then the system temp directory.
    Never returns a path that git would track.
    """
    override = os.environ.get("MR_COMMENTS_DIR")
    if override:
        target = Path(override).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        return target, "MR_COMMENTS_DIR"

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


def state_filename(project: str, iid: str | int) -> str:
    project_slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(project).strip("/")).strip("-")
    return f"mr-comments-{project_slug}-{iid}.json"


def load_state(path: Path) -> dict:
    if not path.exists():
        raise ScriptError(
            f"No comment state at {path}. Run `comments.py init` first."
        )
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def add_event(state: dict, kind: str, detail: str) -> None:
    state.setdefault("events", []).append(
        {"at": now_iso(), "kind": kind, "detail": detail}
    )


def find_comment(state: dict, cid: str) -> dict:
    wanted = str(cid).strip().upper()
    if wanted.isdigit():
        wanted = f"C{wanted}"
    for comment in state.get("comments", []):
        if comment.get("id") == wanted:
            return comment
    known = [comment.get("id") for comment in state.get("comments", [])] or "none"
    raise ScriptError(f"Comment {cid} does not exist. Known comments: {known}")


def comment_number(cid: str) -> int:
    match = re.fullmatch(r"C(\d+)", str(cid).strip().upper())
    if not match:
        raise ScriptError(f"Comment id must look like C1, got {cid!r}")
    return int(match.group(1))


def parse_remote(url: str) -> tuple[str, str] | None:
    """Split a git remote URL into (host, group/path), dropping any port."""
    url = url.strip()
    for pattern in _REMOTE_PATTERNS:
        match = pattern.match(url)
        if match:
            host = match.group("host").split(":")[0].lower()
            path = match.group("path").strip("/")
            if path:
                return host, path
    return None
