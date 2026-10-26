#!/usr/bin/env python3
"""Collect unresolved review threads from GitHub or GitLab.

Both providers are normalized into a single thread model so every later phase
is provider-agnostic. This command only reads from the forge; its sole write is
the triage state file in a gitignored scratch directory.

Usage:
    python3 fetch_threads.py                       # current branch, auto-detect
    python3 fetch_threads.py --number 14783 --repo cli/cli
    python3 fetch_threads.py --provider gitlab --host code.example.com --repo team/api --number 2340
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

from _common import (
    SCHEMA_VERSION,
    ScriptError,
    add_event,
    now_iso,
    repo_root,
    resolve_state_dir,
    run,
    save_state,
    state_path,
)

GITHUB_QUERY = """
query($owner: String!, $repo: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      number
      title
      url
      headRefOid
      baseRefOid
      reviewThreads(first: 100, after: $cursor) {
        totalCount
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          startLine
          originalLine
          diffSide
          comments(first: 50) {
            nodes {
              id
              author { login __typename }
              body
              createdAt
              path
              line
              originalLine
            }
          }
        }
      }
    }
  }
}
""".strip()

BOT_SUFFIXES = ("[bot]", "-bot", "_bot")
KNOWN_BOTS = {
    "copilot-pull-request-reviewer",
    "github-actions",
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


def detect_provider(host: str) -> str:
    return "github" if "github" in host.lower() else "gitlab"


def classify_author(login: str | None, typename: str | None = None, self_login: str | None = None) -> str:
    if not login:
        return "unknown"
    if self_login and login == self_login:
        return "self"
    if typename == "Bot":
        return "bot"
    lowered = login.lower()
    if lowered.endswith(BOT_SUFFIXES) or lowered in KNOWN_BOTS:
        return "bot"
    return "human"


def _anchor(path: str | None, line: int | None, end_line: int | None, side: str) -> dict:
    if not path:
        return {"kind": "mr", "path": None, "line": None, "endLine": None, "side": None}
    if not line:
        return {"kind": "file", "path": path, "line": None, "endLine": None, "side": None}
    return {"kind": "inline", "path": path, "line": line, "endLine": end_line, "side": side}


def normalize_github_thread(node: dict, self_login: str | None = None) -> dict | None:
    comments = (node.get("comments") or {}).get("nodes") or []
    if not comments:
        return None
    first = comments[0]
    author = first.get("author") or {}
    login = author.get("login")

    path = node.get("path") or first.get("path")
    line = (
        node.get("line")
        or first.get("line")
        or node.get("originalLine")
        or first.get("originalLine")
    )
    start_line = node.get("startLine")
    end_line = max(start_line, line) if (start_line and line) else None
    side = "old" if (node.get("diffSide") or "").upper() == "LEFT" else "new"

    return {
        "id": f"gh:{node['id']}",
        "remoteId": node["id"],
        "anchor": _anchor(path, line, end_line, side),
        "author": login,
        "authorKind": classify_author(login, author.get("__typename"), self_login),
        "body": first.get("body") or "",
        "createdAt": first.get("createdAt"),
        "resolvable": True,
        "resolved": bool(node.get("isResolved")),
        "stale": bool(node.get("isOutdated")),
        "replies": [
            {
                "author": (reply.get("author") or {}).get("login"),
                "authorKind": classify_author(
                    (reply.get("author") or {}).get("login"),
                    (reply.get("author") or {}).get("__typename"),
                    self_login,
                ),
                "body": reply.get("body") or "",
                "createdAt": reply.get("createdAt"),
            }
            for reply in comments[1:]
        ],
    }


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
    path = position.get("new_path") or position.get("old_path")
    new_line = position.get("new_line")
    old_line = position.get("old_line")
    line_range = position.get("line_range") or {}
    range_end = line_range.get("end") or {}
    range_start = line_range.get("start") or {}

    line = new_line or old_line or range_end.get("new_line") or range_end.get("old_line")
    end_line = None
    if range_start and range_end:
        first_line = range_start.get("new_line") or range_start.get("old_line")
        last_line = range_end.get("new_line") or range_end.get("old_line")
        if first_line and last_line and last_line > first_line:
            line, end_line = first_line, last_line

    side = "new" if new_line else ("old" if old_line else None)
    note_sha = position.get("head_sha")
    author = root.get("author") or {}
    login = author.get("username")

    return {
        "id": f"gl:{discussion['id']}",
        "remoteId": discussion["id"],
        "anchor": _anchor(path, line, end_line, side),
        "author": login,
        "authorKind": classify_author(login, None, self_login),
        "body": root.get("body") or "",
        "createdAt": root.get("created_at"),
        "resolvable": True,
        "resolved": bool(root.get("resolved")),
        "stale": bool(head_sha and note_sha and note_sha != head_sha),
        "replies": [
            {
                "author": (note.get("author") or {}).get("username"),
                "authorKind": classify_author(
                    (note.get("author") or {}).get("username"), None, self_login
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


def github_api(args: list[str], host: str) -> dict:
    env = {"GH_HOST": host} if host != "github.com" else None
    proc = run(["gh", *args], env=env)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ScriptError(f"Unexpected non-JSON output from gh: {proc.stdout[:200]}") from exc


def fetch_github(repo: str, host: str, number: int | None) -> tuple[dict, list[dict], list[str]]:
    spec = repo if host == "github.com" else f"{host}/{repo}"
    warnings: list[str] = []

    if number is None:
        payload = github_api(["pr", "view", "-R", spec, "--json", "number"], host)
        number = payload["number"]

    owner, _, name = repo.rpartition("/")
    if not owner:
        raise ScriptError(f"GitHub repo must be OWNER/REPO, got {repo!r}")

    proc = run(["gh", "api", "user", "--jq", ".login"], env={"GH_HOST": host} if host != "github.com" else None, check=False)
    self_login = proc.stdout.strip() or None

    threads: list[dict] = []
    cursor: str | None = None
    target: dict = {}
    total = 0
    for _ in range(20):
        cmd = [
            "api", "graphql",
            "-F", f"owner={owner}",
            "-F", f"repo={name}",
            "-F", f"number={number}",
            "-f", f"query={GITHUB_QUERY}",
        ]
        if cursor:
            cmd.extend(["-F", f"cursor={cursor}"])
        payload = github_api(cmd, host)

        if payload.get("errors"):
            raise ScriptError("GitHub GraphQL error: " + json.dumps(payload["errors"])[:400])

        pr = payload["data"]["repository"]["pullRequest"]
        if not target:
            target = {
                "kind": "pr",
                "number": pr["number"],
                "title": pr.get("title"),
                "url": pr.get("url"),
                "headSha": pr.get("headRefOid"),
                "baseSha": pr.get("baseRefOid"),
            }
        connection = pr["reviewThreads"]
        total = connection.get("totalCount", total)
        for node in connection.get("nodes") or []:
            normalized = normalize_github_thread(node, self_login)
            if normalized:
                threads.append(normalized)
        page = connection.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        cursor = page.get("endCursor")
    else:
        warnings.append("Stopped after 20 pages; some threads may be missing.")

    if total > len(threads):
        warnings.append(f"Fetched {len(threads)} of {total} threads reported by GitHub.")
    return target, threads, warnings


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

    encoded = quote(repo, safe="")
    base = f"projects/{encoded}/merge_requests/{number}"
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


def merge_existing(state: dict, fresh: dict) -> dict:
    """Keep prior verdicts and statuses when the same MR is re-fetched."""
    previous = {item["n"]: item for item in state.get("items", [])}
    if not previous:
        return fresh

    fresh["items"] = sorted(previous.values(), key=lambda item: item["n"])
    add_event(fresh, "refetched", f"{len(fresh['threads'])} thread(s) after re-fetch")

    old_head = (state.get("target") or {}).get("headSha")
    new_head = (fresh.get("target") or {}).get("headSha")
    if old_head and new_head and old_head != new_head:
        add_event(fresh, "head-moved", f"{old_head[:8]} -> {new_head[:8]}")
        fresh["warnings"] = fresh.get("warnings", []) + [
            f"HEAD moved since the last fetch ({old_head[:8]} -> {new_head[:8]}). "
            "Existing verdicts may be stale; re-verify before applying."
        ]
    return fresh


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect unresolved PR/MR review threads into the triage state file."
    )
    parser.add_argument("--provider", choices=("auto", "github", "gitlab"), default="auto")
    parser.add_argument("--repo", help="GitHub OWNER/REPO or GitLab GROUP/PROJECT")
    parser.add_argument("--host", help="Forge host; inferred from the git remote by default")
    parser.add_argument("--number", type=int, help="PR/MR number; inferred from the current branch")
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
    host = args.host or (remote[0] if remote else "github.com")
    provider = args.provider if args.provider != "auto" else detect_provider(host)
    repo = args.repo or (remote[1] if remote else None)
    if not repo:
        raise ScriptError(
            "Could not determine the repository from the git remote. Pass --repo."
        )

    if provider == "github":
        target, threads, warnings = fetch_github(repo, host, args.number)
    else:
        target, threads, warnings = fetch_gitlab(repo, host, args.number)

    unresolved = [thread for thread in threads if not thread["resolved"]]
    kept = threads if args.include_resolved else unresolved

    fetched_at = now_iso()
    state = {
        "schemaVersion": SCHEMA_VERSION,
        "provider": provider,
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
    path = state_path(directory, provider, repo, target["number"])

    if path.exists() and not args.reset:
        state = merge_existing(json.loads(path.read_text(encoding="utf-8")), state)

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
    print(f"target  {provider}:{repo}!{target['number']} @ {str(target.get('headSha'))[:8]}")
    print(f"threads {len(kept)} unresolved" + (f" of {len(threads)}" if args.include_resolved else ""))
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
