#!/usr/bin/env python3
"""Create, verify, approve, and render GitLab merge request comments.

The state file is the single source of truth. Comments enter it through `add`,
which validates the claim and verifies the anchor before writing anything.
`render` is the only output path; `post_comments.py` is the only network path.

Subcommands:
    path      Print the resolved state path
    init      Create or refresh the state for one merge request
    add       Validate and add one comment
    update    Edit or re-anchor an existing comment
    list      List comments in render order
    verify    Re-check every anchor against HEAD
    approve   Parse an approval expression and move comments to approved/dropped
    drop      Drop one comment without deleting it
    render    Write mr-comments.md and print its path
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

from _common import (
    BUDGET_MAX,
    BUDGET_TARGET,
    CONFIDENCES,
    DECISIONS,
    SCHEMA_VERSION,
    SEVERITIES,
    SEVERITY_ORDER,
    SOURCES,
    TYPES,
    ScriptError,
    add_event,
    comment_number,
    find_comment,
    load_state,
    now_iso,
    parse_remote,
    repo_root,
    resolve_state_dir,
    run,
    save_state,
    state_filename,
)
import verify_anchors


# ---------------------------------------------------------------------------
# State resolution and Git helpers
# ---------------------------------------------------------------------------


def resolve_state_file(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.exists():
            raise ScriptError(f"No state file at {path}")
        return path

    directory, _ = resolve_state_dir()
    candidates = sorted(
        path for path in directory.glob("mr-comments-*.json")
        if not path.name.endswith(".tmp")
    )
    if not candidates:
        raise ScriptError(
            f"No comment state in {directory}. Run `comments.py init` first."
        )
    if len(candidates) > 1:
        listing = "\n".join(f"  {path}" for path in candidates)
        raise ScriptError(
            "Multiple comment states found; pass --state to disambiguate:\n" + listing
        )
    return candidates[0]


def git_head(root: Path) -> str:
    proc = run(["git", "rev-parse", "HEAD"], cwd=root, check=False)
    if proc.returncode != 0:
        raise ScriptError("Could not resolve HEAD; run this inside the MR checkout.")
    return proc.stdout.strip()


def current_branch(root: Path) -> str:
    proc = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root, check=False)
    if proc.returncode != 0:
        raise ScriptError("Could not resolve the current branch.")
    return proc.stdout.strip()


def remote_info(root: Path) -> tuple[str, str] | None:
    proc = run(["git", "remote", "get-url", "origin"], cwd=root, check=False)
    if proc.returncode != 0:
        return None
    return parse_remote(proc.stdout.strip())


def detect_base(root: Path) -> str:
    proc = run(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        cwd=root,
        check=False,
    )
    if proc.returncode == 0:
        upstream = proc.stdout.strip()
        return upstream.split("/", 1)[-1] if "/" in upstream else upstream
    for candidate in ("main", "master", "develop"):
        exists = run(
            ["git", "rev-parse", "--verify", "--quiet", candidate],
            cwd=root,
            check=False,
        )
        if exists.returncode == 0:
            return candidate
    raise ScriptError("Could not resolve a base branch. Pass --base <ref>.")


_NON_GITLAB_MARKERS = ("github", "bitbucket", "gitea", "azure")


def glab_available() -> bool:
    try:
        proc = run(["glab", "--version"], check=False)
    except ScriptError:
        return False
    return proc.returncode == 0


def is_gitlab_host(host: str) -> bool:
    if not host:
        return False
    lowered = host.lower()
    if any(marker in lowered for marker in _NON_GITLAB_MARKERS):
        return False
    if "gitlab" in lowered:
        return True
    try:
        proc = run(["glab", "api", "--hostname", host, "version"], check=False)
    except ScriptError:
        return False
    return proc.returncode == 0


def glab_json(host: str, endpoint: str, method: str = "GET", payload=None):
    cmd = ["glab", "api", "--hostname", host]
    if method != "GET":
        cmd += ["--method", method]
    cmd.append(endpoint)
    input_text = None
    if payload is not None:
        input_text = json.dumps(payload)
        cmd += ["--input", "-"]
    try:
        proc = run(cmd, input_text=input_text)
    except ScriptError as error:
        message = str(error)
        if "not installed" in message:
            raise ScriptError(
                "`glab` is not installed or not on PATH. Install it from "
                "https://gitlab.com/gitlab-org/cli#installation, or use the "
                "rendered mr-comments.md copy blocks instead."
            ) from error
        if any(
            marker in message.lower()
            for marker in ("401", "403", "unauthorized", "forbidden")
        ):
            raise ScriptError(
                f"`{' '.join(cmd)}` failed:\n{message}\n"
                f"The token for {host} needs `api` scope."
            ) from error
        raise ScriptError(f"`{' '.join(cmd)}` failed:\n{message}") from error
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as error:
        raise ScriptError(
            f"`{' '.join(cmd)}` returned non-JSON output: {proc.stdout[:200]!r}"
        ) from error


def discover_iid(host: str, project: str, root: Path) -> str:
    branch = current_branch(root)
    endpoint = (
        f"projects/{quote(project, safe='')}/merge_requests"
        f"?source_branch={quote(branch, safe='')}&state=opened&per_page=1"
    )
    data = glab_json(host, endpoint)
    if not isinstance(data, list) or not data:
        raise ScriptError(
            f"No open merge request found for branch {branch!r} in {project}. "
            "Pass --iid explicitly."
        )
    return str(data[0]["iid"])


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


_EVIDENCE_PATTERNS = (
    re.compile(r"\S+:\d+"),
    re.compile(r"`[^`]+`"),
    re.compile(r"https?://\S+"),
    re.compile(r"\d+\s*(?:ms|s|fps|%|x|KB|MB|GB)\b", re.IGNORECASE),
)


def looks_like_evidence(text: str) -> bool:
    """True when the evidence string cites a location, command, URL, or measurement."""
    return any(pattern.search(text or "") for pattern in _EVIDENCE_PATTERNS)


def count_words(text: str) -> int:
    return len((text or "").split())


def normalize_body(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[#*`_>\[\]()!~]", "", text)
    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
    return " ".join(text.split())


def anchor_label(anchor: dict | None) -> str:
    anchor = anchor or {}
    kind = anchor.get("kind")
    if kind == "inline":
        label = f"{anchor.get('path')}:{anchor.get('line')}"
        if anchor.get("endLine"):
            label += f"-{anchor['endLine']}"
        return label
    if kind == "file":
        return anchor.get("path") or "file"
    return "MR-level"


def build_anchor(
    path: str | None,
    line: int | None,
    end_line: int | None,
) -> dict:
    if line is not None and not path:
        raise ScriptError("--line requires --path.")
    if end_line is not None and line is None:
        raise ScriptError("--end-line requires --line; an inline anchor needs both.")
    if path and line is not None:
        if line < 1:
            raise ScriptError("--line must be a positive line number.")
        if end_line is not None and end_line < line:
            raise ScriptError("--end-line must not be smaller than --line.")
        return {
            "kind": "inline",
            "path": path,
            "line": line,
            "endLine": end_line,
            "inDiff": None,
            "verifiedAt": None,
            "verifiedHash": None,
            "verifiedText": None,
        }
    if path:
        return {
            "kind": "file",
            "path": path,
            "line": None,
            "endLine": None,
            "inDiff": None,
            "verifiedAt": None,
            "verifiedHash": None,
            "verifiedText": None,
        }
    return {
        "kind": "mr",
        "path": None,
        "line": None,
        "endLine": None,
        "inDiff": None,
        "verifiedAt": None,
        "verifiedHash": None,
        "verifiedText": None,
    }


def refresh_anchor(anchor: dict, root: Path, head: str) -> None:
    """Stamp a known-good anchor with the verification metadata for this HEAD."""
    kind = anchor.get("kind")
    anchor["verifiedAt"] = head
    if kind == "inline":
        path = anchor["path"]
        line = anchor["line"]
        end = anchor.get("endLine") or line
        anchor["inDiff"] = True
        anchor["verifiedHash"] = verify_anchors.range_hash(path, line, end, root)
        anchor["verifiedText"] = verify_anchors.line_text(path, line, root)
    else:
        anchor["verifiedHash"] = None
        anchor["verifiedText"] = None
        anchor["inDiff"] = None if kind == "mr" else True


def stamp_anchor(anchor: dict, ranges, root: Path, head: str) -> None:
    status, detail = verify_anchors.verify_anchor(anchor, ranges, root, head)
    if status == "ok":
        refresh_anchor(anchor, root, head)
        return
    hint = "Use a `file` or `mr` anchor instead."
    if status in ("missing", "moved"):
        hint = "Re-read the file at HEAD and re-anchor or drop the comment."
    if status == "head-moved":
        hint = "Run `comments.py verify` after the branch is stable."
    raise ScriptError(f"Anchor rejected ({status}): {detail}. {hint}")


def validate_comment(comment: dict, state: dict) -> None:
    ctype = comment.get("type")
    if ctype not in TYPES:
        raise ScriptError(f"type must be one of {', '.join(TYPES)}, got {ctype!r}.")
    severity = comment.get("severity")
    if severity not in SEVERITIES:
        raise ScriptError(
            f"severity must be one of {', '.join(SEVERITIES)}, got {severity!r}."
        )

    title = (comment.get("title") or "").strip()
    if not title:
        raise ScriptError("title is required.")
    if len(title) > 60:
        raise ScriptError(f"title is {len(title)} chars; the limit is 60.")

    body = (comment.get("body") or "").strip()
    if not body:
        raise ScriptError("body is required.")
    limit = 250 if comment.get("long") else 120
    words = count_words(body)
    if words > limit:
        raise ScriptError(
            f"body is {words} words; the limit is {limit}. Tighten it or pass --long."
        )

    evidence = (comment.get("evidence") or "").strip()
    if not evidence:
        raise ScriptError(
            "evidence is required: cite `path:line`, a backticked command, a URL, "
            "or a measurement."
        )
    if not looks_like_evidence(evidence):
        raise ScriptError(
            "evidence must cite `path:line`, a backticked command, a URL, or a "
            "measurement with units."
        )

    source = comment.get("source") or {}
    if source.get("kind") not in SOURCES:
        raise ScriptError(f"source must be one of {', '.join(SOURCES)}.")
    decision = source.get("decision")
    if decision not in DECISIONS:
        raise ScriptError(f"decision must be one of {', '.join(DECISIONS)}.")
    confidence = source.get("confidence")
    if confidence not in CONFIDENCES:
        raise ScriptError(f"confidence must be one of {', '.join(CONFIDENCES)}.")

    if ctype == "blocker":
        if decision != "agreed":
            raise ScriptError("blocker comments require --decision agreed.")
        if confidence == "low":
            raise ScriptError("blocker comments cannot have low confidence; drop it instead.")

    suggestion = comment.get("suggestion")
    if ctype == "suggestion":
        if decision != "agreed":
            raise ScriptError("suggestion comments require --decision agreed.")
        if not (suggestion or "").strip():
            raise ScriptError("suggestion comments require --suggestion-file.")
        if len(suggestion.strip("\n").splitlines()) > 5:
            raise ScriptError("suggestion replacement must be 5 lines or fewer.")
    elif suggestion:
        raise ScriptError("only type=suggestion may carry a suggestion block.")

    anchor = comment.get("anchor") or {}
    if anchor.get("kind") == "inline" and not (
        anchor.get("path") and isinstance(anchor.get("line"), int)
    ):
        raise ScriptError("inline anchors require both path and line.")


def find_duplicate(state: dict, comment: dict) -> dict | None:
    anchor = comment.get("anchor") or {}
    body = normalize_body(comment.get("body") or "")
    for other in state.get("comments", []):
        if other.get("id") == comment.get("id"):
            continue
        other_anchor = other.get("anchor") or {}
        if (
            other_anchor.get("path") == anchor.get("path")
            and other_anchor.get("line") == anchor.get("line")
            and normalize_body(other.get("body") or "") == body
        ):
            return other
    return None


# ---------------------------------------------------------------------------
# Ordering and rendering
# ---------------------------------------------------------------------------


def order_comments(state: dict, include_dropped: bool = False) -> list[dict]:
    comments = state.get("comments", [])
    if not include_dropped:
        comments = [c for c in comments if c.get("status") != "dropped"]

    def key(comment: dict):
        anchor = comment.get("anchor") or {}
        return (
            SEVERITY_ORDER.get(comment.get("severity"), 9),
            1 if anchor.get("kind") == "mr" else 0,
            anchor.get("path") or "",
            anchor.get("line") or 0,
            comment_number(comment.get("id", "C0")),
        )

    return sorted(comments, key=key)


def dropped_rows(state: dict) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for item in state.get("dropped", []):
        rows.append((item.get("claim") or "candidate", item.get("reason") or "rejected"))
    for comment in state.get("comments", []):
        if comment.get("status") == "dropped":
            rows.append(
                (
                    comment.get("title") or (comment.get("body") or "")[:60],
                    comment.get("dropReason") or "dropped",
                )
            )
    return rows


def longest_backtick_run(text: str) -> int:
    return max((len(match.group(0)) for match in re.finditer(r"`+", text)), default=0)


def body_for(comment: dict, mode: str) -> str:
    title = (comment.get("title") or "").strip()
    body = (comment.get("body") or "").strip()
    anchor = comment.get("anchor") or {}

    if mode == "summary":
        parts = [f"### {title}"]
        if anchor.get("kind") != "mr":
            parts.append(f"**Target:** `{anchor_label(anchor)}`")
    else:
        parts = [f"**{title}**"]

    if body:
        parts.append(body)
    if comment.get("type") == "suggestion" and (comment.get("suggestion") or "").strip():
        replacement = comment["suggestion"].strip("\n")
        parts.append("```suggestion:-0+0\n" + replacement + "\n```")
    return "\n\n".join(parts)


def render_comment(comment: dict, mode: str) -> str:
    anchor = comment.get("anchor") or {}
    parts = [f"#### {comment.get('id')} · {comment.get('type')} · {anchor_label(anchor)}"]
    if mode == "inline":
        parts.append(f"**Anchor:** `{anchor_label(anchor)}`")
    block = body_for(comment, mode)
    fence = "`" * max(4, longest_backtick_run(block) + 1)
    parts.append(f"{fence}markdown\n{block}\n{fence}")
    return "\n\n".join(parts)


def dropped_table(rows: list[tuple[str, str]]) -> str:
    lines = ["| Candidate | Reason |", "|---|---|"]
    for claim, reason in rows:
        lines.append(f"| {claim} | {reason} |")
    return "\n".join(lines)


def footer(state: dict) -> str:
    ordered = order_comments(state)
    total = len(ordered)
    head = ((state.get("mr") or {}).get("headSha") or "")
    verified = sum(
        1 for comment in ordered
        if (comment.get("anchor") or {}).get("verifiedAt") == head
    )
    dropped = len(dropped_rows(state))
    label = "comment" if total == 1 else "comments"
    sha = head[:7] or "unknown"
    return (
        f"{total} {label} · {verified}/{total} anchors verified at {sha} · "
        f"{dropped} dropped · lang={state.get('lang', 'en')}"
    )


def render_markdown(state: dict, mode: str = "inline") -> str:
    ordered = order_comments(state)
    rows = dropped_rows(state)
    chunks: list[str] = []

    if not ordered:
        if rows:
            chunks.append(f"No actionable comments. {len(rows)} candidates were dropped:")
            chunks.append(dropped_table(rows))
        else:
            chunks.append("No actionable comments.")
    else:
        chunks.extend(render_comment(comment, mode) for comment in ordered)
        if rows:
            chunks.append("**Dropped candidates**")
            chunks.append(dropped_table(rows))

    chunks.append(footer(state))
    return "\n\n".join(chunks) + "\n"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_path(args: argparse.Namespace) -> int:
    path = resolve_state_file(args.state)
    directory, source = resolve_state_dir()
    print(path)
    print(f"# dir={directory} source={source}", file=sys.stderr)
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    root = repo_root()
    if root is None:
        raise ScriptError("Not inside a git repository. Run init inside the MR checkout.")

    remote = remote_info(root)
    host = args.host or (remote[0] if remote else None)
    project = args.project or (remote[1] if remote else None)
    iid = str(args.iid) if args.iid is not None else None

    if not host:
        raise ScriptError("Could not resolve the GitLab host. Pass --host explicitly.")
    if not project:
        raise ScriptError("Could not resolve the project path. Pass --project explicitly.")

    if not is_gitlab_host(host):
        known_other = any(
            marker in host.lower() for marker in _NON_GITLAB_MARKERS
        )
        asserted = bool(args.host and args.project) and not glab_available()
        if known_other or not asserted:
            raise ScriptError(
                f"`to-mr-comments` is GitLab-only in v1. The remote `{host}` is not a "
                "confirmed GitLab instance. Stopping without generating comments."
            )

    mr_payload: dict | None = None
    if args.from_mr:
        if iid is None:
            iid = discover_iid(host, project, root)
        payload = glab_json(
            host, f"projects/{quote(project, safe='')}/merge_requests/{iid}"
        )
        if not isinstance(payload, dict):
            raise ScriptError(f"Unexpected GitLab response for {project}!{iid}.")
        mr_payload = payload
        references = payload.get("references") or {}
        full = references.get("full") or ""
        if "!" in full:
            project = full.rsplit("!", 1)[0] or project
    elif iid is None:
        raise ScriptError("Pass --iid, or use --from-mr to discover it from the branch.")
    elif not args.offline:
        try:
            payload = glab_json(
                host, f"projects/{quote(project, safe='')}/merge_requests/{iid}"
            )
        except ScriptError:
            payload = None
        if isinstance(payload, dict):
            mr_payload = payload
            references = payload.get("references") or {}
            full = references.get("full") or ""
            if "!" in full:
                project = full.rsplit("!", 1)[0] or project

    head = git_head(root)
    base = args.base
    if not base and mr_payload:
        base = (mr_payload.get("target_branch") or "").strip() or None
    if not base:
        base = detect_base(root)
    exists = run(["git", "rev-parse", "--verify", "--quiet", base], cwd=root, check=False)
    if exists.returncode != 0:
        raise ScriptError(f"Base ref {base!r} does not exist in this repository.")

    if mr_payload:
        diff_refs = mr_payload.get("diff_refs") or {}
        web_url = mr_payload.get("web_url")
        target_branch = mr_payload.get("target_branch") or base
    else:
        merge_base = run(["git", "merge-base", base, head], cwd=root, check=False)
        base_sha = (
            merge_base.stdout.strip()
            if merge_base.returncode == 0
            else run(["git", "rev-parse", base], cwd=root).stdout.strip()
        )
        diff_refs = {"base_sha": base_sha, "start_sha": base_sha, "head_sha": head}
        web_url = f"https://{host}/{project}/-/merge_requests/{iid}"
        target_branch = base

    directory, _ = resolve_state_dir(root)
    state_path = (
        Path(args.state).expanduser()
        if getattr(args, "state", None)
        else directory / state_filename(project, iid)
    )

    existing = load_state(state_path) if state_path.exists() else None
    state = {
        "schemaVersion": SCHEMA_VERSION,
        "lang": args.lang or ((existing or {}).get("lang")) or "en",
        "createdAt": (existing or {}).get("createdAt") or now_iso(),
        "mr": {
            "provider": "gitlab",
            "host": host,
            "project": project,
            "iid": iid,
            "webUrl": web_url,
            "base": base,
            "sourceBranch": current_branch(root),
            "targetBranch": target_branch,
            "headSha": head,
            "diffRefs": diff_refs,
        },
        "budget": (existing or {}).get("budget")
        or {"target": BUDGET_TARGET, "max": BUDGET_MAX, "forced": False},
        "comments": (existing or {}).get("comments", []),
        "dropped": (existing or {}).get("dropped", []),
        "events": (existing or {}).get("events", []),
    }
    if existing and existing.get("mr", {}).get("headSha") != head:
        state.setdefault("warnings", []).append(
            f"HEAD moved from {str(existing['mr'].get('headSha'))[:7]} to {head[:7]}; "
            "run `comments.py verify`."
        )
    add_event(
        state,
        "created" if existing is None else "updated",
        f"{project}!{iid} at {head[:7]}",
    )
    save_state(state_path, state)

    print(state_path.resolve())
    print(f"MR:      {host}/{project}!{iid}")
    print(f"base:    {base}  HEAD: {head[:7]}")
    print(
        "diffRefs: "
        f"base={str(diff_refs.get('base_sha'))[:7]} "
        f"start={str(diff_refs.get('start_sha'))[:7]} "
        f"head={str(diff_refs.get('head_sha'))[:7]}"
    )
    print(f"lang:    {state['lang']}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    state_path = resolve_state_file(args.state)
    state = load_state(state_path)
    root = repo_root()
    if root is None:
        raise ScriptError("Not inside a git repository.")
    head = git_head(root)

    if args.line is not None and not args.path:
        raise ScriptError("--line requires --path.")
    kind = "mr" if not args.path else ("inline" if args.line is not None else "file")
    ranges: dict = {}
    if kind != "mr":
        ranges = verify_anchors.parse_diff(state["mr"]["base"], head, root)

    anchor = build_anchor(args.path, args.line, args.end_line)
    stamp_anchor(anchor, ranges, root, head)

    body = Path(args.body_file).read_text(encoding="utf-8").strip()
    suggestion = None
    if args.suggestion_file:
        suggestion = Path(args.suggestion_file).read_text(encoding="utf-8").strip("\n")

    comment = {
        "id": "C0",
        "status": "pending",
        "type": args.type,
        "severity": args.severity,
        "anchor": anchor,
        "evidence": (args.evidence or "").strip(),
        "source": {
            "kind": args.source,
            "decision": args.decision,
            "confidence": args.confidence,
            "quote": args.quote,
        },
        "title": (args.title or "").strip(),
        "body": body,
        "suggestion": suggestion,
        "long": bool(args.long),
        "posted": {"noteId": None, "discussionId": None, "postedAt": None},
    }
    validate_comment(comment, state)

    duplicate = find_duplicate(state, comment)
    if duplicate:
        raise ScriptError(
            f"Duplicate of {duplicate['id']}: same anchor and body already exist."
        )

    live = [c for c in state.get("comments", []) if c.get("status") != "dropped"]
    budget = state.setdefault(
        "budget", {"target": BUDGET_TARGET, "max": BUDGET_MAX, "forced": False}
    )
    if len(live) + 1 > int(budget.get("max", BUDGET_MAX)) and not args.force:
        raise ScriptError(
            f"Comment budget is {budget.get('max', BUDGET_MAX)}; pass --force to exceed it."
        )
    if len(live) + 1 > int(budget.get("max", BUDGET_MAX)):
        budget["forced"] = True

    next_number = max(
        [comment_number(c.get("id", "C0")) for c in state.get("comments", [])] or [0]
    ) + 1
    comment["id"] = f"C{next_number}"

    state.setdefault("comments", []).append(comment)
    add_event(state, "created", comment["id"])

    new_live = len(live) + 1
    if new_live == int(budget.get("target", BUDGET_TARGET)) and not budget.get("warned"):
        budget["warned"] = True
        print(
            f"warning: reached the target budget of {budget.get('target')} comments; "
            "the hard max is "
            f"{budget.get('max')}.",
            file=sys.stderr,
        )

    save_state(state_path, state)
    print(
        f"{comment['id']}  {comment['status']}  {comment['type']}/{comment['severity']}  "
        f"{anchor_label(anchor)}"
    )
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    state_path = resolve_state_file(args.state)
    state = load_state(state_path)
    comment = find_comment(state, args.cid)
    if comment.get("status") == "posted":
        raise ScriptError(f"{comment['id']} is posted and cannot be edited.")

    root = repo_root()
    if root is None:
        raise ScriptError("Not inside a git repository.")
    head = git_head(root)

    if args.reanchor:
        if args.path is None:
            raise ScriptError("--reanchor requires --path (and --line for an inline anchor).")
        ranges = verify_anchors.parse_diff(state["mr"]["base"], head, root)
        anchor = build_anchor(args.path, args.line, args.end_line)
        stamp_anchor(anchor, ranges, root, head)
        comment["anchor"] = anchor
    elif args.path is not None or args.line is not None or args.end_line is not None:
        raise ScriptError(
            "Changing the anchor requires --reanchor so the new position is verified."
        )

    if args.title is not None:
        comment["title"] = args.title.strip()
    if args.body_file:
        comment["body"] = Path(args.body_file).read_text(encoding="utf-8").strip()
    if args.severity is not None:
        comment["severity"] = args.severity
    if args.type is not None:
        comment["type"] = args.type
    if args.evidence is not None:
        comment["evidence"] = args.evidence.strip()
    if args.suggestion_file:
        comment["suggestion"] = (
            Path(args.suggestion_file).read_text(encoding="utf-8").strip("\n")
        )
    if args.quote is not None:
        comment.setdefault("source", {})["quote"] = args.quote
    if args.long is not None:
        comment["long"] = bool(args.long)

    validate_comment(comment, state)

    if comment.get("status") == "approved":
        comment["status"] = "pending"
    add_event(state, "updated", comment["id"])
    save_state(state_path, state)
    print(
        f"{comment['id']}  {comment['status']}  {comment['type']}/{comment['severity']}  "
        f"{anchor_label(comment.get('anchor'))}"
    )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    state = load_state(resolve_state_file(args.state))
    ordered = order_comments(state)
    if args.json:
        print(
            json.dumps(
                {
                    "comments": ordered,
                    "dropped": state.get("dropped", []),
                    "budget": state.get("budget", {}),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    if not ordered:
        print("No comments yet.")
        return 0
    for comment in ordered:
        print(
            f"{comment['id']:<4} {comment.get('type', ''):<10} "
            f"{comment.get('severity', ''):<15} {comment.get('status', ''):<9} "
            f"{anchor_label(comment.get('anchor')):<45} "
            f"{comment.get('title', '')}"
        )
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    state_path = resolve_state_file(args.state)
    state = load_state(state_path)
    root = repo_root()
    if root is None:
        raise ScriptError("Not inside a git repository.")
    head = git_head(root)
    base = args.base or state["mr"]["base"]
    ranges = verify_anchors.parse_diff(base, head, root)

    checked = 0
    failures: list[tuple[str, str, str]] = []
    for comment in state.get("comments", []):
        if comment.get("status") in ("dropped", "posted"):
            continue
        checked += 1
        anchor = comment.get("anchor") or {}
        status, detail = verify_anchors.verify_anchor(anchor, ranges, root, head)
        if status == "ok":
            refresh_anchor(anchor, root, head)
        else:
            failures.append((comment["id"], status, detail))
        print(
            f"{comment['id']:<4} {comment.get('status', ''):<9} {status:<11} "
            f"{anchor_label(anchor)}"
        )
        if status != "ok":
            print(f"     {detail}")

    if not failures:
        state["mr"]["headSha"] = head
        add_event(state, "verified", f"{checked} anchors at {head[:7]}")
    save_state(state_path, state)

    if failures:
        print(
            f"\n{len(failures)} anchor(s) need attention at {head[:7]}. "
            "Re-anchor with `update --reanchor`, or drop the comment."
        )
        return 1
    print(f"\n{checked} anchor(s) verified at {head[:7]}.")
    return 0


def parse_approval(
    expression: str, comments: list[dict]
) -> tuple[list[int], list[int], dict[int, str]]:
    """Parse an approval expression into (approved, skipped, overrides).

    Accepts: "all", "1, 3", "skip 2", "2=APPROVE", "3=DROP", "4=PENDING".
    """
    text = expression.lower().strip()
    text = re.sub(r"^(approve|approved|ok|yes)\b[:,]?\s*", "", text)
    tokens = [token for token in re.split(r"[,\s;]+", text) if token]

    known = {comment_number(comment["id"]) for comment in comments}
    overrides: dict[int, str] = {}
    selected: set[int] = set()
    skipped: set[int] = set()
    everything = False

    actions = {"approve": "APPROVE", "approved": "APPROVE", "drop": "DROP",
               "pending": "PENDING"}

    index = 0
    while index < len(tokens):
        token = tokens[index]
        token = re.sub(r"^#?[cC](?=-?\d)", "", token).lstrip("#")
        if token in ("all", "everything", "*"):
            everything = True
        elif token in ("skip", "except", "without"):
            index += 1
            if index >= len(tokens):
                raise ScriptError(f"'skip' needs a comment number in {expression!r}")
            next_token = re.sub(r"^#?[cC](?=-?\d)", "", tokens[index]).lstrip("#")
            if not next_token.lstrip("-").isdigit():
                raise ScriptError(f"'skip' needs a comment number in {expression!r}")
            skipped.add(int(next_token.lstrip("-")))
        elif re.fullmatch(r"#?-?\d+=.+", token):
            number, _, action = token.partition("=")
            number_int = int(number.lstrip("#-"))
            action_name = actions.get(action.lower())
            if action_name is None:
                raise ScriptError(
                    f"Unknown action {action!r}; expected APPROVE, DROP, or PENDING."
                )
            overrides[number_int] = action_name
            selected.add(number_int)
        elif re.fullmatch(r"#?-?\d+", token):
            number_int = int(token.lstrip("#-"))
            if token.startswith("-"):
                skipped.add(number_int)
            else:
                selected.add(number_int)
        else:
            raise ScriptError(f"Could not parse {token!r} in {expression!r}")
        index += 1

    if everything:
        selected = set(known)
    selected -= skipped

    unknown = (selected | skipped) - known
    if unknown:
        raise ScriptError(
            f"Comment(s) {sorted(unknown)} are not in the state. "
            f"Known comments: {sorted(known)}"
        )
    return sorted(selected), sorted(skipped), overrides


def cmd_approve(args: argparse.Namespace) -> int:
    state_path = resolve_state_file(args.state)
    state = load_state(state_path)
    comments = state.get("comments", [])
    if not comments:
        raise ScriptError("No comments yet. Add them with `comments.py add` first.")

    approved, skipped, overrides = parse_approval(args.expr, comments)

    newly_approved: list[dict] = []
    newly_dropped: list[dict] = []
    unapproved: list[dict] = []

    for comment in comments:
        number = comment_number(comment["id"])
        if comment.get("status") == "posted":
            continue
        action = overrides.get(number)
        if number in approved:
            if action == "DROP":
                comment["status"] = "dropped"
                comment["dropReason"] = "dropped by approval expression"
                newly_dropped.append(comment)
            elif action == "PENDING":
                comment["status"] = "pending"
            else:
                comment["status"] = "approved"
                newly_approved.append(comment)
        elif number in skipped:
            comment["status"] = "dropped"
            comment["dropReason"] = "skipped by approval expression"
            newly_dropped.append(comment)
        elif comment.get("status") == "approved":
            comment["status"] = "pending"
            unapproved.append(comment)

    add_event(
        state,
        "approved",
        f"approved={[c['id'] for c in newly_approved]} "
        f"dropped={[c['id'] for c in newly_dropped]} "
        f"unapproved={[c['id'] for c in unapproved]}",
    )
    save_state(state_path, state)

    print("Approved for posting:")
    if newly_approved:
        for comment in newly_approved:
            print(
                f"  {comment['id']}  {comment.get('type', ''):<10} "
                f"{anchor_label(comment.get('anchor')):<45} {comment.get('title', '')}"
            )
    else:
        print("  (none)")
    if newly_dropped:
        print("\nDropped:")
        for comment in newly_dropped:
            print(f"  {comment['id']}  {comment.get('title', '')}")
    if unapproved:
        print("\nNo longer approved (this expression replaces the previous plan):")
        for comment in unapproved:
            print(f"  {comment['id']}  {comment.get('title', '')}")
    return 0


def cmd_drop(args: argparse.Namespace) -> int:
    state_path = resolve_state_file(args.state)
    state = load_state(state_path)
    comment = find_comment(state, args.cid)
    if comment.get("status") == "posted":
        raise ScriptError(f"{comment['id']} is posted and cannot be dropped.")
    comment["status"] = "dropped"
    comment["dropReason"] = args.reason.strip()
    add_event(state, "dropped", f"{comment['id']}: {args.reason.strip()}")
    save_state(state_path, state)
    print(f"{comment['id']}  dropped  {comment.get('title', '')}")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    state_path = resolve_state_file(args.state)
    state = load_state(state_path)
    mode = "inline" if args.mode == "auto" else args.mode
    markdown = render_markdown(state, mode)

    out = (
        Path(args.out).expanduser()
        if args.out
        else state_path.parent / "mr-comments.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    print(out.resolve())
    print(footer(state))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create, verify, approve, and render GitLab MR comments."
    )
    parser.add_argument("--state", help="Explicit path to the state JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("path", help="Print the resolved state path")

    init_parser = subparsers.add_parser("init", help="Create or refresh the state")
    init_parser.add_argument("--project", help="group/project")
    init_parser.add_argument("--iid", type=int, help="Merge request IID")
    init_parser.add_argument("--base", help="Base ref, e.g. main")
    init_parser.add_argument("--host", help="GitLab host, e.g. gitlab.example.com")
    init_parser.add_argument("--lang", help="Comment language code, e.g. en or fa")
    init_parser.add_argument(
        "--offline", action="store_true", help="Derive diff refs from git, no network"
    )
    init_parser.add_argument(
        "--from-mr", action="store_true", help="Read MR metadata through glab"
    )

    add_parser = subparsers.add_parser("add", help="Validate and add one comment")
    add_parser.add_argument("--type", required=True, choices=TYPES)
    add_parser.add_argument("--severity", required=True, choices=SEVERITIES)
    add_parser.add_argument("--title", required=True)
    add_parser.add_argument("--body-file", required=True)
    add_parser.add_argument("--evidence", required=True)
    add_parser.add_argument("--source", required=True, choices=SOURCES)
    add_parser.add_argument("--decision", required=True, choices=DECISIONS)
    add_parser.add_argument("--confidence", required=True, choices=CONFIDENCES)
    add_parser.add_argument("--quote", help="Provenance quote; never rendered")
    add_parser.add_argument("--path", help="File path for an inline or file anchor")
    add_parser.add_argument("--line", type=int, help="Line number for an inline anchor")
    add_parser.add_argument("--end-line", type=int, help="Display-only range end")
    add_parser.add_argument("--suggestion-file", help="Replacement lines for a suggestion")
    add_parser.add_argument("--long", action="store_true", default=False)
    add_parser.add_argument("--force", action="store_true", help="Exceed the budget")

    update_parser = subparsers.add_parser("update", help="Edit or re-anchor a comment")
    update_parser.add_argument("cid")
    update_parser.add_argument("--title")
    update_parser.add_argument("--body-file")
    update_parser.add_argument("--severity", choices=SEVERITIES)
    update_parser.add_argument("--type", choices=TYPES)
    update_parser.add_argument("--evidence")
    update_parser.add_argument("--suggestion-file")
    update_parser.add_argument("--quote")
    update_parser.add_argument("--long", action="store_true", default=None)
    update_parser.add_argument("--reanchor", action="store_true")
    update_parser.add_argument("--path")
    update_parser.add_argument("--line", type=int)
    update_parser.add_argument("--end-line", type=int)

    list_parser = subparsers.add_parser("list", help="List comments in render order")
    list_parser.add_argument("--json", action="store_true")

    verify_parser = subparsers.add_parser("verify", help="Re-check every anchor at HEAD")
    verify_parser.add_argument("--base")

    approve_parser = subparsers.add_parser("approve", help="Parse an approval expression")
    approve_parser.add_argument(
        "expr", help='e.g. "all", "1, 3", "skip 2", or "2=APPROVE"'
    )

    drop_parser = subparsers.add_parser("drop", help="Drop one comment")
    drop_parser.add_argument("cid")
    drop_parser.add_argument("--reason", required=True)

    render_parser = subparsers.add_parser("render", help="Write mr-comments.md")
    render_parser.add_argument(
        "--mode", choices=("auto", "inline", "summary"), default="auto"
    )
    render_parser.add_argument("--out", help="Output path")

    for sub in subparsers.choices.values():
        sub.add_argument("--state", help=argparse.SUPPRESS, default=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "state") or args.state is None:
        args.state = None
    handlers = {
        "path": cmd_path,
        "init": cmd_init,
        "add": cmd_add,
        "update": cmd_update,
        "list": cmd_list,
        "verify": cmd_verify,
        "approve": cmd_approve,
        "drop": cmd_drop,
        "render": cmd_render,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ScriptError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
