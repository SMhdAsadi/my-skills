#!/usr/bin/env python3
"""Preview or post review-thread replies — dry-run unless --post is given.

Posting is visible to the whole team, so it is gated. `--item` selects one item
for a correction; `--all-approved` selects every eligible item in one batch, so
ten threads are still one preview and one `--post`. The item's stored reply
draft is the default body; --body and --body-file are explicit overrides.

Eligibility is the Gate 2 rule: an item in approved/applied/verified, or a
reply-only item (not ACCEPT/ALTERNATIVE) still in proposed. The latter is the
one-gate fast path; a code item in proposed is never posted, and a plan that
contains one is refused until Gate 1 approves it.

Each thread is journaled on its own: the reply is posted, resolved if asked, and
saved to the state file before the next thread starts. A partial failure keeps
every successful record and leaves the failed thread resumable, so a retry never
posts the same reply twice.

Usage:
    python3 post_reply.py --all-approved                  # preview every reply
    python3 post_reply.py --all-approved --post           # send the batch
    python3 post_reply.py --all-approved --resolve --post # reply and resolve
    python3 post_reply.py --item 3                        # preview one item
    python3 post_reply.py --item 3 --post                 # send one item
    python3 post_reply.py --item 3 --body "Thanks" --post # explicit override
    python3 post_reply.py --item 3 --thread gl:abc --post # one thread only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote

from _common import (
    CODE_VERDICTS,
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
# A code item in one of these states cannot authorise a reply batch and is not
# eligible on its own; the fast path must stand down until Gate 1 runs.
UNFINISHED_CODE_STATUSES = {"proposed"}


def anchor_label(thread: dict) -> str:
    """Where the thread is anchored, in the same shape as triage_state."""
    anchor = thread.get("anchor") or {}
    kind = anchor.get("kind")
    if kind == "inline" and anchor.get("path"):
        side = anchor.get("side")
        return f"{anchor['path']}:{anchor.get('line')}" + (f" ({side})" if side else "")
    if kind == "file" and anchor.get("path"):
        return anchor["path"]
    return "MR-level"


def read_body(item: dict, *, body: str | None = None, body_file: str | None = None):
    """Return the exact body to post and where it came from.

    The item's stored reply draft is the default; an explicit body or body file
    is an override and is recorded as such.
    """
    if body_file:
        if body_file == "-":
            body = sys.stdin.read()
        else:
            body = Path(body_file).read_text(encoding="utf-8")
        source = "override"
    elif body is not None:
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
    refuse_orphaned(item)
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


def refuse_orphaned(item: dict) -> None:
    """Never post to an item whose threads disappeared from the merge request."""
    if not item.get("orphaned"):
        return
    missing = ", ".join(item.get("missingThreadIds") or []) or "one or more threads"
    raise ScriptError(
        f"Item #{item['n']} is orphaned: {missing} is no longer in the merge request. "
        "Re-fetch and re-plan the item, or drop it, before posting."
    )


def find_post(item: dict, thread_id: str) -> dict | None:
    """The journal record for one thread, if this thread was already posted."""
    for post in item.get("posts") or []:
        if post.get("threadId") == thread_id:
            return post
    return None


def is_eligible(item: dict) -> bool:
    """Gate 2 eligibility, including the reply-only fast path."""
    status = item.get("status")
    if status in POSTABLE_STATUSES:
        return True
    return status == "proposed" and item.get("verdict") not in CODE_VERDICTS


def select_eligible(items: list[dict]) -> list[dict]:
    return [item for item in items if is_eligible(item)]


def unfinished_code_items(items: list[dict]) -> list[dict]:
    """Code items that still owe a Gate 1 decision."""
    return [
        item
        for item in items
        if item.get("verdict") in CODE_VERDICTS
        and item.get("status") in UNFINISHED_CODE_STATUSES
    ]


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
    parser = argparse.ArgumentParser(description="Preview or post review-thread replies.")
    parser.add_argument("--state", help="Explicit path to the state JSON")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--item", type=int, help="One item number")
    selection.add_argument(
        "--all-approved",
        action="store_true",
        help="Every eligible item: approved, or reply-only and proposed",
    )
    parser.add_argument("--thread", help="Reply to one thread id instead of all threads on the item")
    parser.add_argument("--body-file", help="File with the reply text; use - for stdin (overrides the draft)")
    parser.add_argument("--body", help="Inline reply text (overrides the stored reply draft)")
    parser.add_argument("--post", action="store_true", help="Actually send the replies")
    parser.add_argument("--resolve", action="store_true", help="Resolve the threads after replying")
    return parser


def single_item_entries(state: dict, args: argparse.Namespace) -> tuple[list[dict], list[dict]]:
    item = find_item(state, args.item)

    status = item.get("status")
    # A fully posted but unresolved item is not re-postable, but a resolve-only
    # retry must still be allowed to finish the journal.
    resolve_retry = status == "posted" and args.resolve
    if status not in POSTABLE_STATUSES and not resolve_retry:
        if status == "proposed":
            hint = (
                f"Run `triage_state.py approve {args.item}` first (Gate 1)."
                if item.get("verdict") in CODE_VERDICTS
                else "Reply-only items can be posted with --all-approved, or approve it first."
            )
        else:
            hint = f"Run `triage_state.py approve {args.item}` first (Gate 1)."
        raise ScriptError(f"Item #{args.item} is '{status}'; posting needs an approved item. {hint}")

    threads = target_threads(state, item, args.thread)
    pending_ids = {
        thread["id"]
        for thread in threads
        if not (find_post(item, thread["id"]) or {}).get("postedAt")
    }
    if pending_ids or not args.post:
        body, source = read_body(item, body=args.body, body_file=args.body_file)
    else:
        body, source = None, None
    entries = [
        {"item": item, "thread": thread, "body": body, "source": source}
        for thread in threads
    ]
    return [item], entries


def batch_entries(state: dict, args: argparse.Namespace) -> tuple[list[dict], list[dict]]:
    items = state.get("items") or []
    if not items:
        raise ScriptError("No triaged items. Plan the review first with triage_state.py plan.")

    selected = select_eligible(items)
    blocking = unfinished_code_items(items)
    # The fast path stands down when nothing was approved and the plan still
    # owes Gate 1 a decision on a code item. Skipped/posted code items are not
    # executable, so they do not block a reply-only batch.
    if not any(item.get("status") in POSTABLE_STATUSES for item in selected) and blocking:
        numbers = ", ".join("#" + str(item["n"]) for item in blocking)
        raise ScriptError(
            "The reply-only fast path cannot post a plan that still contains an "
            f"unapproved code item: {numbers}. "
            "Gate 1 is required: run `triage_state.py approve all` (or skip those "
            "items), then re-run --all-approved."
        )
    if not selected:
        raise ScriptError(
            "No eligible items to post. An item is eligible when it is approved, "
            "applied, or verified, or when it is reply-only and still proposed."
        )

    if args.body is not None or args.body_file:
        raise ScriptError(
            "--body and --body-file are single-item overrides; they cannot apply one "
            "text to every item in --all-approved. Use --item for a manual body."
        )

    entries: list[dict] = []
    for item in sorted(selected, key=lambda entry: entry.get("n", 0)):
        body, source = read_body(item)
        threads = target_threads(state, item, None)
        entries.extend(
            {"item": item, "thread": thread, "body": body, "source": source}
            for thread in threads
        )
    return selected, entries


def print_preview(
    state: dict,
    selected: list[dict],
    entries: list[dict],
    *,
    args: argparse.Namespace,
    batch: bool,
) -> None:
    print(f"{'post' if args.post else 'dry-run'}  gitlab:{state['repo']}!{state['target']['number']}")
    if batch:
        already = sum(
            1
            for entry in entries
            if (find_post(entry["item"], entry["thread"]["id"]) or {}).get("postedAt")
        )
        print(
            f"batch    {len(selected)} item(s), {len(entries)} thread(s) "
            f"({already} already posted)"
        )
    previous = None
    for entry in entries:
        item = entry["item"]
        thread = entry["thread"]
        if item is not previous:
            if previous is not None:
                print()
            print(f"item     #{item['n']} {item['verdict']} ({item['status']})")
            previous = item
        record = find_post(item, thread["id"])
        decision = "already posted" if (record or {}).get("postedAt") else "post"
        print(
            f"thread   {thread['id']}  @{thread.get('author')}  "
            f"({decision})  {anchor_label(thread)}"
        )
        if entry["body"] is not None:
            print(f"body     {entry['source']}")
            print("-" * 60)
            print(entry["body"])
            print("-" * 60)
    print(f"resolve  {'yes' if args.resolve else 'no'}")


def report_batch_failure(
    entries: list[dict],
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
    failed = entries[index]["thread"]["id"]
    failed_item = entries[index]["item"]["n"]
    if resolve_failed:
        succeeded = [*succeeded, failed]
    print(f"Succeeded:     {', '.join(succeeded) if succeeded else '(none)'}")
    print(f"Failed:        {failed} (item #{failed_item})" + (" (resolve)" if resolve_failed else ""))
    if already_posted:
        print(f"Already posted: {', '.join(already_posted)}")
    remaining = [entry["thread"]["id"] for entry in entries[index + 1 :]]
    if remaining:
        print(f"Not attempted: {', '.join(remaining)}")
    raise ScriptError(
        f"Posting stopped at thread {failed} (item #{failed_item}). "
        f"{len(succeeded)} thread(s) are recorded. Re-run the same command to "
        "resume; threads with a journal record are never posted twice. "
        f"glab reported: {error}"
    )


def post_entries(
    path: Path,
    state: dict,
    entries: list[dict],
    *,
    resolve: bool,
) -> int:
    """Post the flat batch; journal each thread before the next call."""
    host = state["host"]
    succeeded: list[str] = []
    already_posted: list[str] = []

    for index, entry in enumerate(entries):
        item = entry["item"]
        thread = entry["thread"]
        record = find_post(item, thread["id"])

        if record is not None and record.get("postedAt"):
            if resolve and not record.get("resolvedAt"):
                try:
                    gitlab_resolve(host, state, thread["remoteId"])
                except ScriptError as error:
                    report_batch_failure(
                        entries,
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
                save_state(path, state)
                print(f"resolved {thread['id']}  (already posted; no duplicate reply)")
            else:
                already_posted.append(thread["id"])
                print(f"skipped  {thread['id']}  (already posted)")
            continue

        try:
            result = gitlab_reply(host, state, thread["remoteId"], entry["body"])
        except ScriptError as error:
            report_batch_failure(entries, index, succeeded, already_posted, error)

        if record is None:
            record = {"threadId": thread["id"]}
            item.setdefault("posts", []).append(record)
        record.update(
            {
                "threadId": thread["id"],
                "postedAt": now_iso(),
                "resolvedAt": None,
                "body": entry["body"],
                "url": (result or {}).get("url"),
                "source": entry["source"],
            }
        )
        add_event(state, "posted", f"item #{item['n']} thread {thread['id']}")

        if resolve:
            try:
                gitlab_resolve(host, state, thread["remoteId"])
            except ScriptError as error:
                # The reply is published: journal it before reporting the
                # resolve failure so a retry can finish without re-posting.
                item["updatedAt"] = now_iso()
                refresh_item_status(item)
                save_state(path, state)
                report_batch_failure(
                    entries,
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.thread and not args.item:
        raise ScriptError("--thread requires --item; it cannot select a thread in a batch.")

    path = resolve_state_file(args.state)
    state = load_state(path)

    if args.all_approved:
        selected, entries = batch_entries(state, args)
    else:
        selected, entries = single_item_entries(state, args)

    print_preview(state, selected, entries, args=args, batch=args.all_approved)

    if not args.post:
        print("Preview only. Re-run with --post to send.")
        return 0

    return post_entries(path, state, entries, resolve=args.resolve)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ScriptError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
