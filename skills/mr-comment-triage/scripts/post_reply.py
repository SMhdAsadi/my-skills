#!/usr/bin/env python3
"""Post a prepared reply to a review thread — dry-run unless --post is given.

Posting is visible to the whole team, so it is gated twice: the caller must pass
--post, and the item must already be approved. The item's stored reply draft is
the default body; --body and --body-file are explicit overrides.

Each thread is journaled on its own: the reply is posted, resolved if asked, and
saved to the state file before the next thread starts. A partial failure keeps
every successful record and leaves the failed thread resumable, so a retry never
posts the same reply twice.

Usage:
    python3 post_reply.py --item 3                        # preview the draft
    python3 post_reply.py --item 3 --post                 # send the draft
    python3 post_reply.py --item 3 --body "Thanks" --post # explicit override
    python3 post_reply.py --item 3 --thread gl:abc --post # one thread only
    python3 post_reply.py --item 3 --post --resolve       # reply and resolve
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


def read_body(args: argparse.Namespace, item: dict) -> tuple[str, str]:
    """Return the exact body to post and where it came from.

    The item's stored reply draft is the default; an explicit --body or
    --body-file is an override and is recorded as such.
    """
    if args.body_file:
        if args.body_file == "-":
            body = sys.stdin.read()
        else:
            body = Path(args.body_file).read_text(encoding="utf-8")
        source = "override"
    elif args.body is not None:
        body = args.body
        source = "override"
    else:
        body = item.get("replyDraft") or ""
        source = "draft"
    body = body.strip()
    if not body:
        raise ScriptError(
            f"Refusing to post an empty reply for item #{item['n']}. "
            "Set a reply draft with triage_state.py set --reply, or pass --body."
        )
    if len(body) > 60000:
        raise ScriptError(f"Reply is {len(body)} characters; that is too long for a review comment.")
    return body, source


def target_threads(state: dict, item: dict, explicit: str | None) -> list[dict]:
    index = {thread["id"]: thread for thread in state.get("threads", [])}
    wanted = [explicit] if explicit else item.get("threadIds", [])
    if not wanted:
        raise ScriptError(f"Item #{item['n']} has no thread ids. Set them with triage_state.py set.")
    # Defensive dedupe: a repeated id must never receive the same reply twice.
    deduped = list(dict.fromkeys(wanted))
    missing = [thread_id for thread_id in deduped if thread_id not in index]
    if missing:
        raise ScriptError(f"Unknown thread id(s): {', '.join(missing)}")
    return [index[thread_id] for thread_id in deduped]


def find_post(item: dict, thread_id: str) -> dict | None:
    """The journal record for one thread, if this thread was already posted."""
    for post in item.get("posts") or []:
        if post.get("threadId") == thread_id:
            return post
    return None


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
    parser.add_argument("--body-file", help="File with the reply text; use - for stdin (overrides the draft)")
    parser.add_argument("--body", help="Inline reply text (overrides the stored reply draft)")
    parser.add_argument("--post", action="store_true", help="Actually send the reply")
    parser.add_argument("--resolve", action="store_true", help="Resolve the thread after replying")
    return parser


def report_batch_failure(
    item: dict,
    threads: list[dict],
    index: int,
    succeeded: list[str],
    already_posted: list[str],
    error: ScriptError,
    *,
    resolve_failed: bool = False,
):
    """Report exactly which threads are recorded and which failed, then stop.

    The successful records are already on disk, so the failed thread stays
    resumable: re-running the command skips every thread with a post record.
    """
    failed = threads[index]["id"]
    if resolve_failed:
        succeeded = [*succeeded, failed]
    print(f"Succeeded:     {', '.join(succeeded) if succeeded else '(none)'}")
    print(f"Failed:        {failed}" + (" (resolve)" if resolve_failed else ""))
    if already_posted:
        print(f"Already posted: {', '.join(already_posted)}")
    remaining = [thread["id"] for thread in threads[index + 1 :]]
    if remaining:
        print(f"Not attempted: {', '.join(remaining)}")
    raise ScriptError(
        f"Posting stopped at thread {failed} (item #{item['n']}). "
        f"{len(succeeded)} thread(s) are recorded. Re-run the same command to "
        "resume; threads with a journal record are never posted twice. "
        f"glab reported: {error}"
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = resolve_state_file(args.state)
    state = load_state(path)
    item = find_item(state, args.item)

    if args.resolve and not args.post:
        raise ScriptError("--resolve requires --post; refusing to resolve silently.")

    status = item.get("status")
    # A fully posted but unresolved item is not re-postable, but a resolve-only
    # retry must still be allowed to finish the journal.
    resolve_retry = status == "posted" and args.resolve
    if status not in POSTABLE_STATUSES and not resolve_retry:
        raise ScriptError(
            f"Item #{args.item} is '{status}'; posting needs an approved item. "
            f"Run `triage_state.py approve {args.item}` first (Gate 1)."
        )

    threads = target_threads(state, item, args.thread)
    pending_ids = {
        thread["id"]
        for thread in threads
        if not (find_post(item, thread["id"]) or {}).get("postedAt")
    }
    if pending_ids or not args.post:
        body, source = read_body(args, item)
    else:
        body, source = None, None
    host = state["host"]

    print(f"{'post' if args.post else 'dry-run'}  gitlab:{state['repo']}!{state['target']['number']}")
    print(f"item     #{item['n']} {item['verdict']} ({item['status']})")
    for thread in threads:
        decision = "post" if thread["id"] in pending_ids else "already posted"
        print(f"thread   {thread['id']}  @{thread.get('author')}  ({decision})")
    print(f"resolve  {'yes' if args.resolve else 'no'}")
    if body is not None:
        print(f"body     {source}")
        print("-" * 60)
        print(body)
        print("-" * 60)

    if not args.post:
        print("Preview only. Re-run with --post to send.")
        return 0

    succeeded: list[str] = []
    already_posted: list[str] = []
    for index, thread in enumerate(threads):
        record = find_post(item, thread["id"])
        if record is not None and record.get("postedAt"):
            if args.resolve and not record.get("resolvedAt"):
                try:
                    gitlab_resolve(host, state, thread["remoteId"])
                except ScriptError as error:
                    report_batch_failure(
                        item,
                        threads,
                        index,
                        succeeded,
                        already_posted,
                        error,
                        resolve_failed=True,
                    )
                record["resolvedAt"] = now_iso()
                add_event(
                    state, "resolved", f"item #{item['n']} thread {thread['id']}"
                )
                item["updatedAt"] = now_iso()
                refresh_item_status(item)
                save_state(path, state)
                print(f"resolved {thread['id']}  (already posted; no duplicate reply)")
            else:
                already_posted.append(thread["id"])
                print(f"skipped  {thread['id']}  (already posted)")
            continue

        try:
            result = gitlab_reply(host, state, thread["remoteId"], body)
        except ScriptError as error:
            report_batch_failure(
                item, threads, index, succeeded, already_posted, error
            )

        if record is None:
            record = {"threadId": thread["id"]}
            item.setdefault("posts", []).append(record)
        record.update(
            {
                "threadId": thread["id"],
                "postedAt": now_iso(),
                "resolvedAt": None,
                "body": body,
                "url": (result or {}).get("url"),
                "source": source,
            }
        )
        add_event(state, "posted", f"item #{item['n']} thread {thread['id']}")

        if args.resolve:
            try:
                gitlab_resolve(host, state, thread["remoteId"])
            except ScriptError as error:
                # The reply is published: journal it before reporting the
                # resolve failure so a retry can finish without re-posting.
                item["updatedAt"] = now_iso()
                refresh_item_status(item)
                save_state(path, state)
                report_batch_failure(
                    item,
                    threads,
                    index,
                    succeeded,
                    already_posted,
                    error,
                    resolve_failed=True,
                )
            record["resolvedAt"] = now_iso()
            add_event(state, "resolved", f"item #{item['n']} thread {thread['id']}")

        item["updatedAt"] = now_iso()
        refresh_item_status(item)
        # Journal this thread before the next external call, so an interrupted
        # batch can resume without re-posting anything.
        save_state(path, state)
        succeeded.append(thread["id"])
        print(
            f"posted   {thread['id']}"
            + (" (resolved)" if record["resolvedAt"] else "")
        )

    print(f"state    {path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ScriptError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
