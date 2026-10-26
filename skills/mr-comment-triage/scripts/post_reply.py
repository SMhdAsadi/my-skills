#!/usr/bin/env python3
"""Post a prepared reply to a review thread — dry-run unless --post is given.

Posting is visible to the whole team, so it is gated twice: the caller must pass
--post, and the item must already be approved. Resolving a thread is a separate
flag on top of that, because a reviewer owns their own thread.

Usage:
    python3 post_reply.py --item 3 --body-file reply.md            # preview only
    python3 post_reply.py --item 3 --body-file reply.md --post      # send
    python3 post_reply.py --item 3 --body-file reply.md --post --resolve
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote

from _common import (
    ScriptError,
    add_event,
    find_item,
    load_state,
    now_iso,
    resolve_state_dir,
    run,
    save_state,
)

REPLY_MUTATION = """
mutation($threadId: ID!, $body: String!) {
  addPullRequestReviewThreadReply(
    input: {pullRequestReviewThreadId: $threadId, body: $body}
  ) {
    comment { id url }
  }
}
""".strip()

RESOLVE_MUTATION = """
mutation($threadId: ID!) {
  resolveReviewThread(input: {threadId: $threadId}) {
    thread { id isResolved }
  }
}
""".strip()

POSTABLE_STATUSES = {"approved", "applied", "verified"}


def resolve_state_file(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.exists():
            raise ScriptError(f"No state file at {path}")
        return path
    directory, _ = resolve_state_dir()
    candidates = sorted(
        path for path in directory.glob("*.json") if not path.name.endswith(".tmp")
    )
    if len(candidates) != 1:
        raise ScriptError(
            f"Expected exactly one state file in {directory}, found {len(candidates)}. "
            "Pass --state."
        )
    return candidates[0]


def read_body(args: argparse.Namespace) -> str:
    if args.body_file:
        if args.body_file == "-":
            body = sys.stdin.read()
        else:
            body = Path(args.body_file).read_text(encoding="utf-8")
    elif args.body:
        body = args.body
    else:
        raise ScriptError("Provide --body-file or --body.")
    body = body.strip()
    if not body:
        raise ScriptError("Refusing to post an empty reply.")
    if len(body) > 60000:
        raise ScriptError(f"Reply is {len(body)} characters; that is too long for a review comment.")
    return body


def target_threads(state: dict, item: dict, explicit: str | None) -> list[dict]:
    index = {thread["id"]: thread for thread in state.get("threads", [])}
    wanted = [explicit] if explicit else item.get("threadIds", [])
    if not wanted:
        raise ScriptError(f"Item #{item['n']} has no thread ids. Set them with triage_state.py set.")
    missing = [thread_id for thread_id in wanted if thread_id not in index]
    if missing:
        raise ScriptError(f"Unknown thread id(s): {', '.join(missing)}")
    return [index[thread_id] for thread_id in wanted]


def github_reply(host: str, thread_id: str, body: str) -> dict:
    env = {"GH_HOST": host} if host != "github.com" else None
    proc = run(
        [
            "gh", "api", "graphql",
            "-f", f"query={REPLY_MUTATION}",
            "-f", f"threadId={thread_id}",
            "-f", f"body={body}",
        ],
        env=env,
    )
    payload = json.loads(proc.stdout)
    if payload.get("errors"):
        raise ScriptError("GitHub rejected the reply: " + json.dumps(payload["errors"])[:400])
    return (payload.get("data") or {}).get("addPullRequestReviewThreadReply", {}).get("comment", {})


def github_resolve(host: str, thread_id: str) -> None:
    env = {"GH_HOST": host} if host != "github.com" else None
    proc = run(
        ["gh", "api", "graphql", "-f", f"query={RESOLVE_MUTATION}", "-f", f"threadId={thread_id}"],
        env=env,
    )
    payload = json.loads(proc.stdout)
    if payload.get("errors"):
        raise ScriptError("GitHub rejected the resolve: " + json.dumps(payload["errors"])[:400])


def gitlab_endpoint(state: dict, discussion_id: str) -> str:
    encoded = quote(state["repo"], safe="")
    return f"projects/{encoded}/merge_requests/{state['target']['number']}/discussions/{discussion_id}"


def gitlab_reply(host: str, state: dict, discussion_id: str, body: str) -> dict:
    proc = run(
        [
            "glab", "api", "--hostname", host,
            "--method", "POST",
            f"{gitlab_endpoint(state, discussion_id)}/notes",
            "-f", f"body={body}",
        ]
    )
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def gitlab_resolve(host: str, state: dict, discussion_id: str) -> None:
    run(
        [
            "glab", "api", "--hostname", host,
            "--method", "PUT",
            f"{gitlab_endpoint(state, discussion_id)}?resolved=true",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preview or post a review-thread reply.")
    parser.add_argument("--state", help="Explicit path to the state JSON")
    parser.add_argument("--item", type=int, required=True)
    parser.add_argument("--thread", help="Reply to one thread id instead of all threads on the item")
    parser.add_argument("--body-file", help="File with the reply text; use - for stdin")
    parser.add_argument("--body", help="Inline reply text")
    parser.add_argument("--post", action="store_true", help="Actually send the reply")
    parser.add_argument("--resolve", action="store_true", help="Resolve the thread after replying")
    parser.add_argument("--force", action="store_true", help="Post again even if already posted")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = resolve_state_file(args.state)
    state = load_state(path)
    item = find_item(state, args.item)
    body = read_body(args)

    if args.resolve and not args.post:
        raise ScriptError("--resolve requires --post; refusing to resolve silently.")
    if item.get("status") not in POSTABLE_STATUSES and not args.force:
        raise ScriptError(
            f"Item #{args.item} is '{item.get('status')}', not approved. "
            "Approve it first, or pass --force if you know what you are doing."
        )
    if item.get("postedAt") and not args.force:
        raise ScriptError(
            f"Item #{args.item} was already posted at {item['postedAt']}. "
            "Use --force to post again."
        )

    threads = target_threads(state, item, args.thread)
    provider = state["provider"]
    host = state["host"]

    print(f"{'post' if args.post else 'dry-run'}  {provider}:{state['repo']}!{state['target']['number']}")
    print(f"item     #{item['n']} {item['verdict']} ({item['status']})")
    for thread in threads:
        print(f"thread   {thread['id']}  @{thread.get('author')}")
    print(f"resolve  {'yes' if args.resolve else 'no'}")
    print("-" * 60)
    print(body)
    print("-" * 60)

    if not args.post:
        print("Preview only. Re-run with --post to send.")
        return 0

    posted = []
    for thread in threads:
        if provider == "github":
            result = github_reply(host, thread["remoteId"], body)
            if args.resolve:
                github_resolve(host, thread["remoteId"])
        else:
            result = gitlab_reply(host, state, thread["remoteId"], body)
            if args.resolve:
                gitlab_resolve(host, state, thread["remoteId"])
        posted.append(
            {
                "threadId": thread["id"],
                "at": now_iso(),
                "url": (result or {}).get("url"),
            }
        )
        print(f"posted   {thread['id']}")

    item["postedAt"] = now_iso()
    item["postedReplies"] = posted
    item["status"] = "resolved" if args.resolve else "posted"
    add_event(
        state,
        "posted",
        f"item #{item['n']} -> {[entry['threadId'] for entry in posted]}"
        + (" (resolved)" if args.resolve else ""),
    )
    save_state(path, state)
    print(f"state    {path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ScriptError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
