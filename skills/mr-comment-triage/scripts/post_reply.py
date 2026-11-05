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
    refresh_item_status,
    resolve_state_file,
    run,
    save_state,
)

POSTABLE_STATUSES = {"approved", "applied", "verified"}


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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = resolve_state_file(args.state)
    state = load_state(path)
    item = find_item(state, args.item)

    if item.get("status") not in POSTABLE_STATUSES:
        raise ScriptError(
            f"Item #{args.item} is '{item.get('status')}'; posting needs an approved item. "
            f"Run `triage_state.py approve {args.item}` first (Gate 1)."
        )
    if args.resolve and not args.post:
        raise ScriptError("--resolve requires --post; refusing to resolve silently.")

    body = read_body(args)
    threads = target_threads(state, item, args.thread)
    host = state["host"]

    print(f"{'post' if args.post else 'dry-run'}  gitlab:{state['repo']}!{state['target']['number']}")
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

    source = "override"
    for thread in threads:
        posted_at = now_iso()
        result = gitlab_reply(host, state, thread["remoteId"], body)
        resolved_at = None
        if args.resolve:
            gitlab_resolve(host, state, thread["remoteId"])
            resolved_at = now_iso()
        item.setdefault("posts", []).append(
            {
                "threadId": thread["id"],
                "postedAt": posted_at,
                "resolvedAt": resolved_at,
                "body": body,
                "url": (result or {}).get("url"),
                "source": source,
            }
        )
        print(f"posted   {thread['id']}")

    refresh_item_status(item)
    item["updatedAt"] = now_iso()
    add_event(
        state,
        "posted",
        f"item #{item['n']} -> {[thread['id'] for thread in threads]}"
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
