#!/usr/bin/env python3
"""Parse a branch diff and verify comment anchors against HEAD.

The only authority on whether a line can carry an inline GitLab note is the
MR diff. This module keeps that check deterministic and separate from the
state CLI so it can be unit tested without a network or a GitLab instance.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from _common import ScriptError, repo_root, run

_HUNK_RE = re.compile(r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
                      r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@")
_BINARY_RE = re.compile(r"^Binary files (?P<old>.+) and (?P<new>.+) differ$")


def _clean_path(raw: str, prefix: str) -> str | None:
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    if raw == "/dev/null":
        return None
    if raw.startswith(prefix):
        raw = raw[len(prefix):]
    return raw


def parse_changes(
    diff_text: str,
) -> tuple[dict[str, list[tuple[int, int]]], dict[str, str]]:
    """Parse a unified diff into anchor ranges and a rename map.

    Returns `(ranges, renames)` where `ranges` maps each destination path to
    the new-file ranges a note may target, and `renames` maps a destination
    path to its pre-rename (or pre-copy) source path. A key with an empty
    range list means "changed, but no anchorable new lines" — a deleted file,
    a binary file, or a pure mode change. That distinction matters: `file`
    anchors are allowed there, `inline` anchors are not.
    """
    ranges: dict[str, list[tuple[int, int]]] = {}
    renames: dict[str, str] = {}
    old_path: str | None = None
    new_path: str | None = None
    source_path: str | None = None

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            old_path = None
            new_path = None
            source_path = None
            continue

        if line.startswith("rename from ") or line.startswith("copy from "):
            source_path = _clean_path(line.split(" from ", 1)[1], "")
            continue

        if line.startswith("rename to ") or line.startswith("copy to "):
            target = _clean_path(line.split(" to ", 1)[1], "")
            if target:
                ranges.setdefault(target, [])
                new_path = target
                if source_path and source_path != target:
                    renames[target] = source_path
            continue

        if line.startswith("--- "):
            old_path = _clean_path(line[4:], "a/")
            if old_path and not source_path:
                source_path = old_path
            continue

        if line.startswith("+++ "):
            new_path = _clean_path(line[4:], "b/")
            target = new_path or old_path
            if target:
                ranges.setdefault(target, [])
            continue

        if line.startswith("@@"):
            target = new_path or old_path
            if not target:
                continue
            match = _HUNK_RE.match(line)
            if not match:
                continue
            new_start = int(match.group("new_start"))
            new_count = (
                int(match.group("new_count"))
                if match.group("new_count") is not None
                else 1
            )
            ranges.setdefault(target, [])
            if new_count > 0:
                ranges[target].append((new_start, new_start + new_count - 1))
            continue

        binary = _BINARY_RE.match(line)
        if binary:
            target = (
                _clean_path(binary.group("new"), "b/")
                or _clean_path(binary.group("old"), "a/")
                or new_path
                or old_path
                or source_path
            )
            if target:
                ranges.setdefault(target, [])

    for path in ranges:
        ranges[path].sort()
    return ranges, renames


def hunk_ranges(diff_text: str) -> dict[str, list[tuple[int, int]]]:
    """Map each destination path to the new-file ranges a note may target."""
    return parse_changes(diff_text)[0]


def _diff_text(base: str, head: str, cwd=None) -> str:
    ref = f"{base}...{head}"
    proc = run(
        ["git", "diff", "--unified=3", "--no-color", "--no-ext-diff", ref],
        cwd=cwd,
    )
    return proc.stdout


def parse_diff(base: str, head: str, cwd=None) -> dict[str, list[tuple[int, int]]]:
    """Return the new-file visible ranges of `base...head`, keyed by path."""
    return parse_changes(_diff_text(base, head, cwd))[0]


def parse_diff_changes(
    base: str, head: str, cwd=None
) -> tuple[dict[str, list[tuple[int, int]]], dict[str, str]]:
    """Return `(ranges, renames)` for `base...head` in one git invocation."""
    return parse_changes(_diff_text(base, head, cwd))


def _read_lines(path: str, root: Path | None = None) -> list[str]:
    root = Path(root) if root is not None else repo_root()
    if root is None:
        raise ScriptError("Not inside a git repository; cannot read anchor text.")
    full = root / path
    if not full.is_file():
        raise ScriptError(f"Anchor file {path} does not exist at HEAD.")
    return full.read_text(encoding="utf-8").splitlines()


def line_text(path: str, line: int, root: Path | None = None) -> str:
    lines = _read_lines(path, root)
    if line < 1 or line > len(lines):
        raise ScriptError(f"{path}:{line} is outside the file ({len(lines)} lines).")
    return lines[line - 1]


def range_hash(
    path: str, start: int, end: int | None = None, root: Path | None = None
) -> str:
    """sha256 of the exact line range at HEAD, prefixed for readability."""
    start = int(start)
    end = int(end) if end is not None else start
    if end < start:
        raise ScriptError(f"Invalid anchor range {path}:{start}-{end}.")
    lines = _read_lines(path, root)
    chunk = "\n".join(lines[start - 1:end])
    return "sha256:" + hashlib.sha256(chunk.encode("utf-8")).hexdigest()


def verify_anchor(
    anchor: dict,
    ranges: dict[str, list[tuple[int, int]]],
    root: Path,
    head_sha: str | None = None,
    state_head: str | None = None,
) -> tuple[str, str]:
    """Return `(status, detail)` for one anchor.

    status ∈ ok | moved | out-of-diff | missing | head-moved.
    `head-moved` short-circuits every content check: if the state was written
    against a different HEAD, the anchor has to be re-read, not guessed at.

    A `file` anchor only needs its path in the diff's changed-file set, so it
    works for a deleted file, a binary file, or a pure rename. Only `inline`
    anchors read the file at HEAD, because only they anchor a line of it.
    """
    if state_head is not None and head_sha is not None and state_head != head_sha:
        return "head-moved", f"state is at {state_head[:7]}, HEAD is {head_sha[:7]}"

    kind = anchor.get("kind") or "inline"
    if kind == "mr":
        return "ok", "MR-level"

    path = anchor.get("path")
    if not path:
        return "missing", "anchor has no path"

    if path not in ranges:
        return "out-of-diff", f"{path} is not in the diff"

    if kind == "file":
        return "ok", path

    full = Path(root) / path
    if not full.is_file():
        return "missing", f"{path} does not exist at HEAD"

    line = anchor.get("line")
    if not isinstance(line, int):
        return "missing", f"{path} has no line"

    end = anchor.get("endLine") or line
    if not isinstance(end, int):
        return "missing", f"{path} has an invalid end line"

    lines = _read_lines(path, root)
    if not 1 <= line <= end <= len(lines):
        return "missing", (
            f"{path}:{line}-{end} is outside the file ({len(lines)} lines)"
        )

    if not any(start <= line and end <= hunk_end for start, hunk_end in ranges[path]):
        return "out-of-diff", f"{path}:{line}-{end} is outside the diff hunks"

    verified_hash = anchor.get("verifiedHash")
    if verified_hash:
        try:
            current = range_hash(path, line, end, root)
        except ScriptError as error:
            return "missing", str(error)
        if current != verified_hash:
            return "moved", f"{path}:{line}-{end} changed since verification"

    return "ok", f"{path}:{line}"
