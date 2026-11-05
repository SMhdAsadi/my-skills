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


REDACTED = "***"
# A reply body is a whole argument, so everything after `body=` is hidden.
_BODY_INLINE = re.compile(r"(?i)\b(body=).*$", re.MULTILINE)
# Credentials and queries live in URLs, where `&` ends the value.
_SENSITIVE_INLINE = re.compile(r"(?i)\b(private_token|token|query)=([^&\n]*)")


def redact_text(text: str) -> str:
    """Mask credential and reply-content values inside free-form diagnostics."""
    text = _BODY_INLINE.sub(rf"\1{REDACTED}", text or "")
    return _SENSITIVE_INLINE.sub(rf"\1={REDACTED}", text)


def render_command(cmd) -> str:
    """Render a command for an error while hiding bodies and tokens.

    The tool, subcommand, host and endpoint stay visible so authentication and
    routing failures remain diagnosable.
    """
    parts = [str(part) for part in cmd]
    rendered: list[str] = []
    index = 0
    while index < len(parts):
        part = parts[index]
        if part == "--body":
            rendered.append(part)
            index += 1
            if index < len(parts):
                rendered.append(REDACTED)
                index += 1
            continue
        if part == "-f" and index + 2 < len(parts) and parts[index + 1] == "body":
            rendered.extend([part, parts[index + 1], REDACTED])
            index += 3
            continue
        rendered.append(redact_text(part))
        index += 1
    return " ".join(rendered)


def now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def run(cmd, *, cwd=None, check=True, env=None):
    """Run a command; on failure report the redacted command and stderr tail."""
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
            f"`{cmd[0]}` is not installed or not on PATH. Install it and re-run."
        ) from exc
    if check and proc.returncode != 0:
        detail = redact_text((proc.stderr or proc.stdout or "").strip())
        lines = detail.splitlines()[:6]
        label = " ".join(str(part) for part in cmd[:2])
        message = [
            f"`{label}` failed with exit code {proc.returncode}.",
            f"command: {render_command(cmd)}",
            *lines,
        ]
        raise ScriptError("\n".join(message))
    return proc


def repo_root(start=None) -> Path | None:
    proc = run(["git", "rev-parse", "--show-toplevel"], cwd=start, check=False)
    if proc.returncode != 0:
        return None
    return Path(proc.stdout.strip())


def is_gitignored(root: Path, relpath: str) -> bool:
    proc = run(["git", "check-ignore", "-q", relpath], cwd=root, check=False)
    return proc.returncode == 0


def _nearest_existing(path: Path) -> Path:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return probe


def _guard_override(target: Path) -> None:
    """Refuse an override that would write triage state into a tracked path.

    The override is checked against whichever repository contains it, not the
    caller's repository, so an override elsewhere on disk is unaffected.
    """
    resolved = target.resolve()
    probe = _nearest_existing(resolved)
    if not probe.is_dir():
        probe = probe.parent
    repo = repo_root(probe)
    if repo is None:
        return
    try:
        relative = resolved.relative_to(repo)
    except ValueError:
        return
    if relative != Path(".") and is_gitignored(repo, str(relative)):
        return
    raise ScriptError(
        f"MR_TRIAGE_DIR={target} is inside the git repository at {repo} but is not "
        "gitignored, so triage state (including comment bodies) would be tracked. "
        "Choose a path outside the repository or add it to .gitignore."
    )


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
        if not target.is_absolute():
            target = Path.cwd() / target
        _guard_override(target)
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
