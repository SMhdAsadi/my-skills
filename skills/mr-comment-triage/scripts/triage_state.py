#!/usr/bin/env python3
"""Inspect and mutate the mr-comment-triage state file.

The state file is the single source of truth for verdicts, approval status, and
applied fixes. Nothing here touches the repository.

Subcommands:
    path      Print the resolved state path
    threads   List fetched threads with their anchors
    set       Create or update one triaged item
    approve   Parse an approval expression and mark items approved/skipped
    show      Print the current plan
    render    Print the plan as a Markdown table
"""

from __future__ import annotations

import argparse
import copy
import re
import sys
from pathlib import Path

from _common import (
    APPROVED_STATES,
    ITEM_STATUSES,
    MATERIAL_FIELDS,
    NON_EXECUTABLE,
    SEVERITIES,
    VERDICTS,
    ScriptError,
    add_event,
    approval_hash,
    ensure_item_defaults,
    find_item,
    invalidate_approval,
    load_state,
    now_iso,
    resolve_state_dir,
    resolve_state_file,
    save_state,
)

SEVERITY_ORDER = {"blocking": 0, "correctness": 1, "maintainability": 2, "nit": 3}
# Statuses a direct `set --status` may write. Everything else has an owner.
SETTABLE_STATUSES = ("proposed", "applied", "verified", "skipped")


def truncate(text: str | None, width: int = 88) -> str:
    clean = " ".join((text or "").split())
    return clean if len(clean) <= width else clean[: width - 1] + "…"


def side_suffix(anchor: dict) -> str:
    """Show which diff side a line anchor refers to (`old` for deletions)."""
    side = anchor.get("side")
    return f" ({side})" if side else ""


def anchor_label(item: dict, threads: dict) -> str:
    anchors = []
    for thread_id in item.get("threadIds", []):
        thread = threads.get(thread_id)
        if not thread:
            continue
        anchor = thread["anchor"]
        if anchor["kind"] == "inline":
            label = f"`{anchor['path']}:{anchor['line']}{side_suffix(anchor)}`"
        elif anchor["kind"] == "file":
            label = f"`{anchor['path']}`"
        else:
            label = "MR-level"
        if label not in anchors:
            anchors.append(label)
    return ", ".join(anchors) or "—"


def execution_order(items: list[dict]) -> list[dict]:
    return sorted(
        items,
        key=lambda item: (SEVERITY_ORDER.get(item.get("severity"), 9), item.get("n", 0)),
    )


def cmd_path(args: argparse.Namespace) -> int:
    path = resolve_state_file(args.state, must_exist=False)
    directory, source = resolve_state_dir()
    print(path if path is not None else directory)
    print(f"# dir={directory} source={source}", file=sys.stderr)
    return 0


def cmd_threads(args: argparse.Namespace) -> int:
    state = load_state(resolve_state_file(args.state))
    threads = state.get("threads", [])
    if not threads:
        print("No threads in state.")
        return 0
    for thread in threads:
        anchor = thread["anchor"]
        if anchor["kind"] == "inline":
            where = f"{anchor['path']}:{anchor['line']}{side_suffix(anchor)}"
        elif anchor["kind"] == "file":
            where = anchor["path"] or "MR-level"
        else:
            where = "MR-level"
        flags = []
        if thread.get("stale"):
            flags.append("stale")
        if thread.get("resolved"):
            flags.append("resolved")
        suffix = f" [{','.join(flags)}]" if flags else ""
        print(
            f"{thread['id']}  {where}{suffix}  "
            f"@{thread.get('author')}({thread.get('authorKind')})  "
            f"{truncate(thread.get('body'), 70)}"
        )
    return 0


def parse_evidence(entries: list[str]) -> list[dict]:
    """Parse `path:line[:note]` into the evidence list."""
    parsed = []
    for entry in entries:
        match = re.match(r"^(?P<path>[^:]+):(?P<line>\d+)(?::(?P<note>.*))?$", entry.strip())
        if not match:
            raise ScriptError(
                f"--evidence expects path:line or path:line:note, got {entry!r}"
            )
        parsed.append(
            {
                "path": match.group("path"),
                "line": int(match.group("line")),
                "note": (match.group("note") or "").strip(),
            }
        )
    return parsed


def cmd_set(args: argparse.Namespace) -> int:
    path = resolve_state_file(args.state)
    state = load_state(path)

    existing = next((i for i in state.get("items", []) if i.get("n") == args.item), None)
    if existing is None:
        if args.verdict is None:
            raise ScriptError(f"Item #{args.item} does not exist yet; pass --verdict.")
        existing = ensure_item_defaults({"n": args.item, "verdict": args.verdict})
        existing["severity"] = args.severity or existing.get("severity") or "correctness"
        state.setdefault("items", []).append(existing)
    else:
        ensure_item_defaults(existing)

    if args.status and args.status not in SETTABLE_STATUSES:
        if args.status == "approved":
            raise ScriptError(
                f"Item #{args.item} cannot be set to 'approved' with `set`. "
                f"Run `triage_state.py approve {args.item}`; it is the only writer "
                "of an approval and it records the approval hash."
            )
        raise ScriptError(
            f"Item #{args.item} cannot be set to {args.status!r} with `set`. "
            "Only the reply phase (`post_reply.py`) may mark a thread posted or resolved."
        )

    before = {field: copy.deepcopy(existing.get(field)) for field in MATERIAL_FIELDS}

    if args.verdict:
        if args.verdict not in VERDICTS:
            raise ScriptError(f"--verdict must be one of {', '.join(VERDICTS)}")
        existing["verdict"] = args.verdict
    if args.severity:
        if args.severity not in SEVERITIES:
            raise ScriptError(f"--severity must be one of {', '.join(SEVERITIES)}")
        existing["severity"] = args.severity
    if args.claim is not None:
        existing["claim"] = args.claim
    if args.action is not None:
        existing["action"] = args.action
    if args.threads:
        known = {thread["id"] for thread in state.get("threads", [])}
        ids = [part.strip() for part in args.threads.split(",") if part.strip()]
        unknown = [thread_id for thread_id in ids if thread_id not in known]
        if unknown:
            raise ScriptError(f"Unknown thread id(s): {', '.join(unknown)}")
        existing["threadIds"] = ids
    if args.evidence:
        existing["evidence"] = parse_evidence(args.evidence)
    if args.reply_file:
        existing["replyDraft"] = Path(args.reply_file).read_text(encoding="utf-8").strip()
    if args.reply is not None:
        existing["replyDraft"] = args.reply
    if args.commit:
        existing["commitSha"] = args.commit

    changed = [
        field for field in MATERIAL_FIELDS if existing.get(field) != before.get(field)
    ]
    if changed and (
        existing.get("status") in APPROVED_STATES
        or existing.get("approvalHash")
        or existing.get("approvedAt")
    ):
        invalidate_approval(existing, "material edit")
        add_event(
            state,
            "approval-invalidated",
            f"item #{existing['n']}: {', '.join(changed)} changed",
        )

    if args.status:
        current = existing.get("status") or "proposed"
        target = args.status
        if target == "proposed":
            if current in APPROVED_STATES and not changed:
                invalidate_approval(existing, "reset to proposed")
                add_event(
                    state, "approval-invalidated", f"item #{existing['n']}: reset to proposed"
                )
            existing["status"] = "proposed"
            existing["approvedAt"] = None
            existing["approvalHash"] = None
        elif target == "applied":
            if current != "approved":
                raise ScriptError(
                    f"Item #{existing['n']} is {current!r}; only an approved item can "
                    "move to 'applied'. Run `triage_state.py approve` first."
                )
            existing["status"] = "applied"
        elif target == "verified":
            if current not in ("approved", "applied"):
                raise ScriptError(
                    f"Item #{existing['n']} is {current!r}; only an approved or applied "
                    "item can move to 'verified'. Run `triage_state.py approve` first."
                )
            existing["status"] = "verified"
        elif target == "skipped":
            if current not in ("proposed", "approved"):
                raise ScriptError(
                    f"Item #{existing['n']} is {current!r}; only a proposed or approved "
                    "item can be skipped."
                )
            if current == "approved":
                invalidate_approval(existing, "skipped")
            existing["status"] = "skipped"
            add_event(state, "skipped", f"item #{existing['n']}")

    existing["updatedAt"] = now_iso()
    state["items"] = sorted(state["items"], key=lambda item: item["n"])
    save_state(path, state)
    print(f"#{existing['n']} {existing['verdict']} / {existing['severity']} / {existing['status']}")
    return 0


def parse_approval(expression: str, items: list[dict]) -> tuple[list[int], list[int], dict[int, str]]:
    """Parse an approval expression into (approved, skipped, overrides).

    Accepts: "all", "1, 3", "skip 2", "2=ACCEPT", "3:alternative", and "and"
    between item numbers.
    """
    text = expression.strip()
    text = re.sub(r"^(?:approve|approved|ok|yes)\b[:,]?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\band\b", ",", text, flags=re.IGNORECASE)
    tokens = [token for token in re.split(r"[,\s;]+", text) if token]
    if not tokens:
        raise ScriptError("Empty approval expression.")

    known = {item["n"] for item in items}
    overrides: dict[int, str] = {}
    selected: set[int] = set()
    skipped: set[int] = set()
    everything = False
    explicit = False

    index = 0
    while index < len(tokens):
        token = tokens[index]
        lowered = token.lower()
        if lowered in ("all", "everything", "*"):
            everything = True
        elif lowered in ("skip", "except", "without"):
            index += 1
            if index >= len(tokens) or not tokens[index].lstrip("#").isdigit():
                raise ScriptError(f"'skip' needs an item number in {expression!r}")
            skipped.add(int(tokens[index].lstrip("#")))
        elif re.fullmatch(r"#?\d+\s*[=:]\s*\S+", token):
            number, verdict = re.split(r"\s*[=:]\s*", token, maxsplit=1)
            number_int = int(number.lstrip("#"))
            verdict_name = verdict.upper().replace("-", "_")
            if verdict_name not in VERDICTS:
                raise ScriptError(f"Unknown verdict {verdict!r}; expected {', '.join(VERDICTS)}")
            overrides[number_int] = verdict_name
            selected.add(number_int)
            explicit = True
        elif re.fullmatch(r"#?\d+", token):
            selected.add(int(token.lstrip("#")))
            explicit = True
        elif re.fullmatch(r"-\d+", token):
            skipped.add(int(token[1:]))
        else:
            raise ScriptError(f"Could not parse {token!r} in {expression!r}")
        index += 1

    if everything or not explicit:
        # A bare "skip 2" means "everything except 2".
        if everything or skipped:
            selected = set(known)
    selected -= skipped

    unknown = (selected | skipped) - known
    if unknown:
        raise ScriptError(
            f"Item(s) {sorted(unknown)} are not in the plan. Known items: {sorted(known)}"
        )
    return sorted(selected), sorted(skipped), overrides


def cmd_approve(args: argparse.Namespace) -> int:
    path = resolve_state_file(args.state)
    state = load_state(path)
    items = state.get("items", [])
    if not items:
        raise ScriptError("No triaged items yet. Add them with `set` before approving.")

    approved, skipped, overrides = parse_approval(args.expr, items)
    for number, verdict in overrides.items():
        find_item(state, number)["verdict"] = verdict

    executable: list[dict] = []
    held: list[dict] = []
    skipped_items: list[dict] = []
    unapproved: list[dict] = []
    now = now_iso()

    for item in items:
        if item["n"] in approved:
            if item["verdict"] in NON_EXECUTABLE:
                if item.get("status") == "approved":
                    invalidate_approval(item, "held")
                held.append(item)
                continue
            if item.get("status") in ("proposed", "approved", "skipped"):
                item["status"] = "approved"
                item["approvedAt"] = now
                item["approvalHash"] = approval_hash(item)
                item["updatedAt"] = now
            executable.append(item)
        elif item["n"] in skipped:
            if item.get("status") in ("proposed", "approved"):
                if item.get("status") == "approved":
                    invalidate_approval(item, "skipped")
                item["status"] = "skipped"
                item["updatedAt"] = now
                add_event(state, "skipped", f"item #{item['n']} via approve")
            skipped_items.append(item)
        elif item.get("status") == "approved":
            invalidate_approval(item, "unapproved")
            item["updatedAt"] = now
            unapproved.append(item)

    add_event(
        state,
        "approved",
        f"approved={[i['n'] for i in executable]} "
        f"held={[i['n'] for i in held]} "
        f"skipped={[i['n'] for i in skipped_items]} "
        f"unapproved={[i['n'] for i in unapproved]}",
    )

    if not args.dry_run:
        save_state(path, state)

    print("Approved for execution:")
    if executable:
        for item in execution_order(executable):
            print(
                f"  #{item['n']}  {item['verdict']:<13} {item['severity']:<15} "
                f"{truncate(item.get('action'), 60)}"
            )
    else:
        print("  (none)")

    if held:
        print("\nHeld back — needs a decision, not a patch:")
        for item in held:
            print(f"  #{item['n']}  {item['verdict']}: {truncate(item.get('claim'), 70)}")

    if skipped_items:
        print("\nSkipped:")
        for item in sorted(skipped_items, key=lambda entry: entry["n"]):
            print(f"  #{item['n']}  {item['verdict']}")

    if unapproved:
        print("\nNo longer approved (this expression replaces the previous plan):")
        for item in sorted(unapproved, key=lambda entry: entry["n"]):
            print(f"  #{item['n']}  {item['verdict']}")

    if overrides:
        applied = ", ".join(f"#{n}->{v}" for n, v in sorted(overrides.items()))
        print(f"\nOverrides applied: {applied}")

    if args.dry_run:
        print("\n(dry run — state not written)")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    state = load_state(resolve_state_file(args.state))
    target = state.get("target", {})
    print(
        f"gitlab:{state.get('repo')}!{target.get('number')} "
        f"@ {str(target.get('headSha'))[:8]}  ({len(state.get('threads', []))} threads)"
    )
    for warning in state.get("warnings") or []:
        print(f"warn: {warning}")
    items = state.get("items", [])
    if not items:
        print("No triaged items.")
        return 0
    threads = {thread["id"]: thread for thread in state.get("threads", [])}
    for item in items:
        print(
            f"#{item['n']:<3} {item['verdict']:<13} {item['severity']:<15} "
            f"{item['status']:<10} {anchor_label(item, threads)}"
        )
        print(f"     {truncate(item.get('claim'), 110)}")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    state = load_state(resolve_state_file(args.state))
    threads = {thread["id"]: thread for thread in state.get("threads", [])}
    items = state.get("items", [])
    if not items:
        print("No triaged items.")
        return 0

    print("| # | Anchor | Verdict | Severity | Status | Proposed action |")
    print("|---|---|---|---|---|---|")
    for item in sorted(items, key=lambda entry: entry["n"]):
        print(
            f"| {item['n']} | {anchor_label(item, threads)} | `{item['verdict']}` | "
            f"{item['severity']} | {item['status']} | {truncate(item.get('action'), 90)} |"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and update mr-comment-triage state.")
    parser.add_argument("--state", help="Explicit path to the state JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("path", help="Print the resolved state path")

    subparsers.add_parser("threads", help="List fetched threads")

    set_parser = subparsers.add_parser("set", help="Create or update one item")
    set_parser.add_argument("--item", type=int, required=True)
    set_parser.add_argument("--verdict", choices=VERDICTS)
    set_parser.add_argument("--severity", choices=SEVERITIES)
    set_parser.add_argument("--claim")
    set_parser.add_argument("--action")
    set_parser.add_argument("--threads", help="Comma-separated thread ids")
    set_parser.add_argument(
        "--evidence",
        action="append",
        help="path:line or path:line:note; repeat for multiple citations",
    )
    set_parser.add_argument("--reply-file", help="File containing the reply draft")
    set_parser.add_argument("--reply", help="Inline reply draft")
    set_parser.add_argument("--status", choices=ITEM_STATUSES)
    set_parser.add_argument("--commit", help="Commit SHA that applied the fix")

    approve_parser = subparsers.add_parser("approve", help="Parse an approval expression")
    approve_parser.add_argument("expr", help='e.g. "all" or "1, 3, skip 2" or "2=ACCEPT"')
    approve_parser.add_argument("--dry-run", action="store_true")

    subparsers.add_parser("show", help="Print the current plan")
    subparsers.add_parser("render", help="Print the plan as a Markdown table")

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
        "threads": cmd_threads,
        "set": cmd_set,
        "approve": cmd_approve,
        "show": cmd_show,
        "render": cmd_render,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ScriptError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
