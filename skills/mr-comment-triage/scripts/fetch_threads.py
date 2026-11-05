#!/usr/bin/env python3
"""Collect unresolved review threads from a GitLab merge request.

Threads are normalized into one model so every later phase stays independent of
the forge API. This command only reads from GitLab; its sole write is the triage
state file in a gitignored scratch directory.

Usage:
    python3 fetch_threads.py                       # current branch, auto-detect
    python3 fetch_threads.py --number 2340 --repo group/project
    python3 fetch_threads.py --host code.example.com --repo team/api --number 2340
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _common import (
    SCHEMA_VERSION,
    ScriptError,
    add_event,
    ensure_item_defaults,
    gitlab_mr_endpoint,
    invalidate_approval,
    load_state,
    now_iso,
    repo_root,
    resolve_state_dir,
    run,
    save_state,
    state_path,
)

BOT_SUFFIXES = ("[bot]", "-bot", "_bot")
# Forge-neutral automation accounts. GitHub-only logins are deliberately absent:
# this skill talks to GitLab, and a project may legitimately use those names.
KNOWN_BOTS = {
    "dependabot",
    "renovate",
    "codecov",
    "sonarqube",
    "gitlab-bot",
    "mergify",
}

_REMOTE_PATTERNS = (
    re.compile(r"^git@(?P<host>[^:]+):(?P<path>.+?)(?:\.git)?$"),
    re.compile(r"^ssh://[^@/]+@(?P<host>[^:/]+)(?::\d+)?/(?P<path>.+?)(?:\.git)?$"),
    re.compile(r"^https?://(?:[^@/]+@)?(?P<host>[^/]+)/(?P<path>.+?)(?:\.git)?/?$"),
)


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


def classify_author(login: str | None, self_login: str | None = None) -> str:
    if not login:
        return "unknown"
    if self_login and login == self_login:
        return "self"
    lowered = login.lower()
    if lowered.endswith(BOT_SUFFIXES) or lowered in KNOWN_BOTS:
        return "bot"
    return "human"


def _anchor(
    path: str | None,
    old_path: str | None,
    line: int | None,
    end_line: int | None,
    side: str | None,
) -> dict:
    """Build one anchor; ``oldPath`` survives a rename but never repeats ``path``."""
    old_path = old_path if old_path and old_path != path else None
    if not path:
        return {
            "kind": "mr",
            "path": None,
            "oldPath": None,
            "line": None,
            "endLine": None,
            "side": None,
        }
    if line is None:
        return {
            "kind": "file",
            "path": path,
            "oldPath": old_path,
            "line": None,
            "endLine": None,
            "side": None,
        }
    return {
        "kind": "inline",
        "path": path,
        "oldPath": old_path,
        "line": line,
        "endLine": end_line,
        # An inline anchor always has a side: an unresolved side is the new side.
        "side": side or "new",
    }


def _range_values(position: dict, side: str) -> list[int]:
    """Lines of one side declared by ``line_range.start``/``end``."""
    line_range = position.get("line_range") or {}
    key = f"{side}_line"
    parts = (line_range.get("start") or {}, line_range.get("end") or {})
    return [part[key] for part in parts if part.get(key) is not None]


def _anchor_side(position: dict) -> str | None:
    """Derive the diff side, preferring the new side for a mixed range.

    ``new_line`` marks a post-change anchor and ``old_line`` a deletion. When
    both are absent the side comes from ``line_range``: non-null ``new_line``
    values win over ``old_line`` values, so a range that mentions both sides is
    read against the new file.
    """
    if position.get("new_line") is not None:
        return "new"
    if position.get("old_line") is not None:
        return "old"
    if _range_values(position, "new"):
        return "new"
    if _range_values(position, "old"):
        return "old"
    return None


def _anchor_range(position: dict) -> tuple[int | None, int | None, str | None]:
    """Return (line, endLine, side) for a position, range or single-line."""
    side = _anchor_side(position)
    if side is None:
        return None, None, None
    values = _range_values(position, side)
    if not values:
        single = position.get(f"{side}_line")
        values = [single] if single is not None else []
    if not values:
        return None, None, side
    line, end_line = min(values), max(values)
    return line, (end_line if end_line != line else None), side


def normalize_gitlab_discussion(
    discussion: dict, head_sha: str | None = None, self_login: str | None = None
) -> dict | None:
    notes = discussion.get("notes") or []
    if not notes:
        return None
    # A discussion is a review thread when it carries a resolvable, non-system
    # note. Normally that is notes[0], but some flows prepend a system entry.
    root = next(
        (note for note in notes if not note.get("system") and note.get("resolvable")),
        None,
    )
    if root is None:
        return None

    position = root.get("position") or {}
    # A deleted file has no new path; its only surviving path is the old one.
    path = position.get("new_path") or position.get("old_path")
    old_path = position.get("old_path")
    line, end_line, side = _anchor_range(position)
    note_sha = position.get("head_sha")
    author = root.get("author") or {}
    login = author.get("username")

    return {
        "id": f"gl:{discussion['id']}",
        "remoteId": discussion["id"],
        "anchor": _anchor(path, old_path, line, end_line, side),
        "author": login,
        "authorKind": classify_author(login, self_login),
        "body": root.get("body") or "",
        "createdAt": root.get("created_at"),
        "resolvable": True,
        "resolved": bool(root.get("resolved")),
        "stale": bool(head_sha and note_sha and note_sha != head_sha),
        "replies": [
            {
                "author": (note.get("author") or {}).get("username"),
                "authorKind": classify_author(
                    (note.get("author") or {}).get("username"), self_login
                ),
                "body": note.get("body") or "",
                "createdAt": note.get("created_at"),
            }
            for note in notes
            if note is not root and not note.get("system")
        ],
    }


def git_remote(root: Path | None) -> tuple[str, str] | None:
    proc = run(["git", "remote", "get-url", "origin"], cwd=root, check=False)
    if proc.returncode != 0:
        return None
    return parse_remote(proc.stdout)


def gitlab_api(host: str, endpoint: str, *, check: bool = True) -> object:
    proc = run(["glab", "api", "--hostname", host, endpoint], check=check)
    if not check and proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ScriptError(f"Unexpected non-JSON output from glab: {proc.stdout[:200]}") from exc


def fetch_gitlab(repo: str, host: str, number: int | None) -> tuple[dict, list[dict], list[str]]:
    warnings: list[str] = []
    spec = f"{host}/{repo}"

    if number is None:
        payload = run(["glab", "mr", "view", "-R", spec, "-F", "json"]).stdout
        try:
            number = json.loads(payload)["iid"]
        except (json.JSONDecodeError, KeyError) as exc:
            raise ScriptError(f"Could not read the MR number from glab: {payload[:200]}") from exc

    base = gitlab_mr_endpoint(repo, number)
    mr = gitlab_api(host, base)
    if not isinstance(mr, dict):
        raise ScriptError(f"Unexpected GitLab response for {repo}!{number}")

    head_sha = (mr.get("diff_refs") or {}).get("head_sha") or mr.get("sha")
    target = {
        "kind": "mr",
        "number": number,
        "title": mr.get("title"),
        "url": mr.get("web_url"),
        "headSha": head_sha,
        "baseSha": (mr.get("diff_refs") or {}).get("base_sha"),
    }

    user = gitlab_api(host, "user", check=False)
    self_login = (user or {}).get("username") if isinstance(user, dict) else None

    discussions: list[dict] = []
    for page in range(1, 21):
        chunk = gitlab_api(host, f"{base}/discussions?per_page=100&page={page}")
        if not isinstance(chunk, list):
            break
        discussions.extend(chunk)
        if len(chunk) < 100:
            break
    else:
        warnings.append("Stopped after 20 pages; some threads may be missing.")

    threads = []
    for discussion in discussions:
        normalized = normalize_gitlab_discussion(discussion, head_sha, self_login)
        if normalized:
            threads.append(normalized)
    return target, threads, warnings


def reconcile_orphans(state: dict, fresh_threads: list[dict]) -> list[str]:
    """Mark items whose threads vanished and clear approval that no longer applies.

    The fresh thread list is authoritative, so a thread it does not contain can
    no longer receive a reply. A posted or resolved item already happened and
    keeps its status; every other item loses the approval that named the gone
    thread and must be re-planned or dropped.
    """
    known = {thread["id"] for thread in fresh_threads}
    warnings: list[str] = []
    for item in state.get("items", []):
        missing = [
            thread_id
            for thread_id in item.get("threadIds") or []
            if thread_id not in known
        ]
        if not missing:
            # The thread came back: the item is plannable again.
            item["orphaned"] = False
            item["missingThreadIds"] = []
            continue

        item["orphaned"] = True
        item["missingThreadIds"] = missing
        if item.get("status") not in ("posted", "resolved"):
            invalidate_approval(item, "threads missing from the re-fetch")

        joined = ", ".join(missing)
        add_event(state, "orphaned", f"item #{item.get('n')}: missing {joined}")
        warnings.append(
            f"Item #{item.get('n')} references missing thread(s) {joined}; "
            "re-plan or drop it before posting."
        )
    return warnings


def merge_existing(state: dict, fresh: dict) -> dict:
    """Keep prior items and history when the same MR is re-fetched.

    The fresh fetch replaces ``threads`` (it is authoritative) and appends to the
    event log. Triage work is not thrown away: items keep their verdicts,
    statuses, approval metadata and post journal unless a thread they named is
    gone, in which case they are orphaned and their approval is invalidated.
    """
    fresh["events"] = list(state.get("events") or []) + list(fresh.get("events") or [])
    fresh["items"] = sorted(
        (ensure_item_defaults(item) for item in state.get("items") or []),
        key=lambda item: item["n"],
    )
    add_event(fresh, "refetched", f"{len(fresh['threads'])} thread(s) after re-fetch")

    old_head = (state.get("target") or {}).get("headSha")
    new_head = (fresh.get("target") or {}).get("headSha")
    if old_head and new_head and old_head != new_head:
        add_event(fresh, "head-moved", f"{old_head[:8]} -> {new_head[:8]}")
        fresh["warnings"] = fresh.get("warnings", []) + [
            f"HEAD moved since the last fetch ({old_head[:8]} -> {new_head[:8]}). "
            "Existing verdicts may be stale; re-verify before applying."
        ]

    fresh["warnings"] = fresh.get("warnings", []) + reconcile_orphans(
        fresh, fresh["threads"]
    )
    return fresh


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect unresolved GitLab MR review threads into the triage state file."
    )
    parser.add_argument("--repo", help="GitLab GROUP/PROJECT")
    parser.add_argument("--host", help="GitLab host; inferred from the git remote by default")
    parser.add_argument("--number", type=int, help="MR number; inferred from the current branch")
    parser.add_argument(
        "--include-resolved",
        action="store_true",
        help="Keep resolved threads for duplicate detection",
    )
    parser.add_argument("--reset", action="store_true", help="Discard previously triaged items")
    parser.add_argument("--stdout", action="store_true", help="Print state as JSON instead of writing")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    root = repo_root()
    remote = git_remote(root)
    host = args.host or (remote[0] if remote else "gitlab.com")
    repo = args.repo or (remote[1] if remote else None)
    if not repo:
        raise ScriptError(
            "Could not determine the repository from the git remote. Pass --repo."
        )

    target, threads, warnings = fetch_gitlab(repo, host, args.number)

    unresolved = [thread for thread in threads if not thread["resolved"]]
    resolved = [thread for thread in threads if thread["resolved"]]
    kept = threads if args.include_resolved else unresolved

    fetched_at = now_iso()
    state = {
        "schemaVersion": SCHEMA_VERSION,
        "host": host,
        "repo": repo,
        "target": target,
        "fetchedAt": fetched_at,
        "warnings": warnings,
        "threads": kept,
        "items": [],
        "events": [
            {
                "at": fetched_at,
                "type": "fetched",
                "detail": f"{len(unresolved)} unresolved of {len(threads)} thread(s)",
            }
        ],
    }

    directory, source = resolve_state_dir(root)
    path = state_path(directory, repo, target["number"])

    if path.exists() and not args.reset:
        state = merge_existing(load_state(path), state)

    if args.stdout:
        json.dump(state, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    save_state(path, state)

    by_kind: dict[str, int] = {}
    by_author: dict[str, int] = {}
    for thread in kept:
        by_kind[thread["anchor"]["kind"]] = by_kind.get(thread["anchor"]["kind"], 0) + 1
        by_author[thread["authorKind"]] = by_author.get(thread["authorKind"], 0) + 1

    print(f"state   {path}")
    print(f"dir     {source}")
    print(f"target  gitlab:{repo}!{target['number']} @ {str(target.get('headSha'))[:8]}")
    summary = f"threads {len(unresolved)} unresolved"
    if args.include_resolved:
        summary += f", {len(resolved)} resolved kept"
    print(summary)
    print("anchors " + ", ".join(f"{k}={v}" for k, v in sorted(by_kind.items())))
    print("authors " + ", ".join(f"{k}={v}" for k, v in sorted(by_author.items())))
    for warning in state.get("warnings") or []:
        print(f"warn    {warning}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ScriptError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
