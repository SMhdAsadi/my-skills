#!/usr/bin/env python3
"""Shared helpers for the mr-comment-triage scripts.

Everything that touches the filesystem, the shell, or the state schema lives
here so the individual commands stay thin and testable.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 2
STATE_DIRNAME = "mr-comment-triage"

# Repo-local scratch directories we are willing to use, in preference order.
# `tmp/` is included because many projects keep it gitignored; a tracked or
# unignored `tmp/` is rejected by the `git check-ignore` test below.
SCRATCH_CANDIDATES = ("tmp", ".tmp", "scratch", ".scratch")
# Only this one may be created when it does not exist yet.
CREATABLE_SCRATCH = ".tmp"

VERDICTS = ("ACCEPT", "ALTERNATIVE", "PUSH_BACK", "DEFER", "ALREADY_FIXED", "CLARIFY")
SEVERITIES = ("blocking", "correctness", "maintainability", "nit")
CODE_VERDICTS = ("ACCEPT", "ALTERNATIVE")
NON_CODE_VERDICTS = tuple(verdict for verdict in VERDICTS if verdict not in CODE_VERDICTS)
NON_EXECUTABLE = ("CLARIFY", "DEFER")

ITEM_STATUSES = (
    "proposed",
    "approved",
    "applied",
    "verified",
    "posted",
    "resolved",
    "skipped",
)

# The fields that carry the approved intent. Changing any of them invalidates a
# prior approval, because the old "yes" no longer describes what would run.
MATERIAL_FIELDS = ("verdict", "threadIds", "action", "evidence")

APPROVED_STATES = ("approved", "applied", "verified")


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
    Inside a repo scratch directory the artifacts live in a skill-owned
    subdirectory, so they never collide with project files or another skill.
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
                target = candidate / STATE_DIRNAME
                target.mkdir(parents=True, exist_ok=True)
                return target, f"repo:{name}"

        creatable = root / CREATABLE_SCRATCH
        if is_gitignored(root, CREATABLE_SCRATCH):
            target = creatable / STATE_DIRNAME
            target.mkdir(parents=True, exist_ok=True)
            return target, f"repo:{CREATABLE_SCRATCH} (created)"

    target = Path(tempfile.gettempdir()) / STATE_DIRNAME
    target.mkdir(parents=True, exist_ok=True)
    return target, "system-temp"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def state_path(directory: Path, repo: str, number: int) -> Path:
    return directory / f"gitlab-{slug(repo)}-{number}.json"


def resolve_state_file(explicit: str | None, *, must_exist: bool = True) -> Path | None:
    """Return the state file selected by --state or by the scratch directory.

    With ``must_exist=False`` a missing state file selects the directory instead
    of failing, so `triage_state.py path` can be the first command in a run.
    """
    if explicit:
        path = Path(explicit).expanduser()
        if must_exist and not path.exists():
            raise ScriptError(f"No state file at {path}")
        return path

    directory, _ = resolve_state_dir()
    candidates = sorted(
        path for path in directory.glob("*.json") if not path.name.endswith(".tmp")
    )
    if not candidates:
        if not must_exist:
            return None
        raise ScriptError(
            f"No triage state in {directory}. Run fetch_threads.py first."
        )
    if len(candidates) > 1:
        listing = "\n".join(f"  {path}" for path in candidates)
        raise ScriptError(
            "Multiple triage states found; pass --state to disambiguate:\n" + listing
        )
    return candidates[0]


def load_state(path: Path) -> dict:
    if not path.exists():
        raise ScriptError(
            f"No triage state at {path}. Run fetch_threads.py first to collect threads."
        )
    with path.open(encoding="utf-8") as handle:
        try:
            state = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ScriptError(
                f"State file {path} is not valid JSON (line {exc.lineno}, column "
                f"{exc.colno}). Run fetch_threads.py again to rebuild it."
            ) from exc
    version = state.get("schemaVersion")
    if version != SCHEMA_VERSION:
        raise ScriptError(
            f"State file {path} uses schema version {version!r}; this version of "
            f"mr-comment-triage needs version {SCHEMA_VERSION}. "
            "Run fetch_threads.py again to rebuild it."
        )
    return state


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


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def approval_hash(item: dict) -> str:
    """Hash exactly the material intent that approval authorises."""
    payload = {field: item.get(field) for field in MATERIAL_FIELDS}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def invalidate_approval(item: dict, reason: str = "") -> str:
    """Drop the approval revision; executable states fall back to proposed."""
    if item.get("status") in APPROVED_STATES:
        item["status"] = "proposed"
    item["approvedAt"] = None
    item["approvalHash"] = None
    return reason


def ensure_item_defaults(item: dict) -> dict:
    """Fill the v2 item fields so older hand-written fixtures stay valid."""
    defaults = {
        "threadIds": [],
        "verdict": None,
        "severity": "correctness",
        "claim": "",
        "evidence": [],
        "action": "",
        "replyDraft": "",
        "status": "proposed",
        "approvedAt": None,
        "approvalHash": None,
        "commitSha": None,
        "posts": [],
        "orphaned": False,
        "missingThreadIds": [],
        "updatedAt": None,
    }
    for field, value in defaults.items():
        item.setdefault(field, value)
    return item


def refresh_item_status(item: dict) -> str:
    """Derive posted/resolved once every thread on the item has a post record.

    Partial posting leaves the previous status so the batch stays resumable.
    """
    thread_ids = item.get("threadIds") or []
    if not thread_ids:
        return item.get("status")
    posts = {
        post.get("threadId"): post
        for post in (item.get("posts") or [])
        if post.get("threadId")
    }
    if not all(thread_id in posts for thread_id in thread_ids):
        return item.get("status")
    if all(posts[thread_id].get("resolvedAt") for thread_id in thread_ids):
        item["status"] = "resolved"
    else:
        item["status"] = "posted"
    return item["status"]


def find_item(state: dict, number: int) -> dict:
    for item in state.get("items", []):
        if item.get("n") == number:
            return item
    raise ScriptError(
        f"Item #{number} does not exist. Triaged items: "
        f"{[i.get('n') for i in state.get('items', [])] or 'none'}"
    )


EVIDENCE_PATTERN = re.compile(
    r"^(?P<path>[^:]+):(?P<line>\d+)(?::(?P<note>.*))?$"
)


def normalize_evidence_entry(entry) -> dict:
    """Turn a `path:line[:note]` string or a `{path, line, note}` object into a dict."""
    if isinstance(entry, str):
        match = EVIDENCE_PATTERN.match(entry.strip())
        if not match:
            raise ScriptError(
                f"Evidence entry {entry!r} is not 'path:line' or 'path:line:note'."
            )
        path = match.group("path").strip()
        if not path:
            raise ScriptError("Evidence entry needs a non-empty path before ':line'.")
        line = int(match.group("line"))
        if line < 1:
            raise ScriptError(
                f"Evidence for {path!r} needs a positive integer 'line', got {line}."
            )
        return {
            "path": path,
            "line": line,
            "note": (match.group("note") or "").strip(),
        }
    if isinstance(entry, dict):
        path = entry.get("path")
        line = entry.get("line")
        note = entry.get("note")
        if not isinstance(path, str) or not path.strip():
            raise ScriptError("Evidence object needs a non-empty 'path'.")
        if type(line) is not int or line < 1:
            raise ScriptError(
                f"Evidence for {path.strip()!r} needs a positive integer 'line'."
            )
        if note is not None and not isinstance(note, str):
            raise ScriptError(f"Evidence note for {path.strip()!r} must be a string.")
        return {"path": path.strip(), "line": line, "note": (note or "").strip()}
    raise ScriptError(
        "Each evidence entry must be a 'path:line[:note]' string or a "
        "{path, line, note} object."
    )


def verify_evidence(entries, root: Path) -> list[dict]:
    """Normalize evidence and prove every citation exists at HEAD in ``root``.

    Returns the normalized ``[{path, line, note}]`` list so callers can persist
    exactly what they verified.
    """
    if entries is None:
        raise ScriptError(
            "Evidence is required; pass an empty list when there is no line to cite."
        )
    if not isinstance(entries, list):
        raise ScriptError(
            "Evidence must be a list of 'path:line[:note]' strings or "
            "{path, line, note} objects."
        )

    root_path = Path(root).resolve()
    verified = []
    for entry in entries:
        parsed = normalize_evidence_entry(entry)
        relative = Path(parsed["path"])
        if relative.is_absolute():
            raise ScriptError(
                f"Evidence path {parsed['path']!r} must be relative to the repository root."
            )
        target = (root_path / relative).resolve()
        try:
            target.relative_to(root_path)
        except ValueError:
            raise ScriptError(
                f"Evidence path {parsed['path']!r} is outside the repository at {root_path}."
            ) from None
        if not target.exists():
            raise ScriptError(
                f"Evidence path {parsed['path']!r} does not exist at HEAD in {root_path}."
            )
        if not target.is_file():
            raise ScriptError(f"Evidence path {parsed['path']!r} is not a file.")
        text = target.read_text(encoding="utf-8", errors="replace")
        line_count = len(text.splitlines())
        if parsed["line"] > line_count:
            raise ScriptError(
                f"Evidence {parsed['path']}:{parsed['line']} is past the end of "
                f"{parsed['path']} ({line_count} lines at HEAD)."
            )
        verified.append(parsed)
    return verified

