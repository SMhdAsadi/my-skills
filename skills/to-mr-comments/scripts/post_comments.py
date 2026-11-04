#!/usr/bin/env python3
"""Stage and publish rendered comments as GitLab notes.

No flag  → preview the exact payloads and positions. Zero network calls.
--create → create GitLab draft notes (author-only) for draft/approved comments.
--publish → publish approved draft notes and post MR-level notes.

Every gate is checked before the first network call: HEAD must match the state,
anchors must be clean, and only approved comments may be published.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

from _common import (
    ScriptError,
    add_event,
    load_state,
    now_iso,
    repo_root,
    run,
    save_state,
)
import comments as comments_cmd
import verify_anchors


# ---------------------------------------------------------------------------
# Payload builders (pure, so they can be tested without a network)
# ---------------------------------------------------------------------------


def mr_endpoint(state: dict, suffix: str = "") -> str:
    mr = state["mr"]
    project = quote(mr["project"], safe="")
    return f"projects/{project}/merge_requests/{mr['iid']}{suffix}"


def _diff_refs(state: dict) -> dict:
    refs = (state.get("mr") or {}).get("diffRefs") or {}
    missing = [key for key in ("base_sha", "start_sha", "head_sha") if not refs.get(key)]
    if missing:
        raise ScriptError(
            "diff refs are missing from the state. Re-run "
            "`comments.py init --from-mr` before creating GitLab notes."
        )
    return refs


def build_draft_payload(comment: dict, state: dict) -> dict | None:
    """Build a draft-note payload, or None for an MR-level comment."""
    anchor = comment.get("anchor") or {}
    kind = anchor.get("kind")
    if kind == "mr":
        return None

    refs = _diff_refs(state)
    position = {
        "base_sha": refs["base_sha"],
        "start_sha": refs["start_sha"],
        "head_sha": refs["head_sha"],
    }
    if kind == "inline":
        position.update(
            {
                "position_type": "text",
                "old_path": anchor["path"],
                "new_path": anchor["path"],
                "new_line": anchor["line"],
            }
        )
    elif kind == "file":
        position.update(
            {"position_type": "file", "new_path": anchor["path"]}
        )
    else:
        return None
    return {
        "body": comments_cmd.body_for(comment, "inline"),
        "position": position,
    }


def build_note_payload(comment: dict, state: dict) -> dict:
    """A regular MR note carries no position."""
    return {"body": comments_cmd.body_for(comment, "summary")}


def preview_entries(state: dict, one: str | None = None) -> list[dict]:
    entries = []
    for comment in creatable(state, one):
        anchor = comment.get("anchor") or {}
        if anchor.get("kind") == "mr":
            entries.append(
                {
                    "id": comment["id"],
                    "kind": "mr",
                    "method": "POST",
                    "endpoint": mr_endpoint(state, "/notes"),
                    "payload": build_note_payload(comment, state),
                }
            )
        else:
            entries.append(
                {
                    "id": comment["id"],
                    "kind": anchor.get("kind"),
                    "method": "POST",
                    "endpoint": mr_endpoint(state, "/draft_notes"),
                    "payload": build_draft_payload(comment, state),
                }
            )
    return entries


# ---------------------------------------------------------------------------
# Selection and dedupe
# ---------------------------------------------------------------------------


def normalize_id(cid: str | None) -> str | None:
    if not cid:
        return None
    text = cid.strip().upper()
    return text if text.startswith("C") else f"C{text}"


def creatable(state: dict, one: str | None = None) -> list[dict]:
    wanted = normalize_id(one)
    result = []
    for comment in state.get("comments", []):
        if wanted and comment.get("id") != wanted:
            continue
        if comment.get("status") not in ("draft", "approved"):
            continue
        posted = comment.get("posted") or {}
        if posted.get("draftNoteId") or posted.get("noteId"):
            continue
        result.append(comment)
    return result


def publishable(state: dict, one: str | None = None) -> list[dict]:
    wanted = normalize_id(one)
    result = []
    for comment in state.get("comments", []):
        if wanted and comment.get("id") != wanted:
            continue
        if comment.get("status") != "approved":
            continue
        if (comment.get("posted") or {}).get("postedAt"):
            continue
        result.append(comment)
    return result


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[#*`_>\[\]()!~]", "", text)
    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
    return " ".join(text.split())


def similarity(comment: dict, note_body: str) -> float:
    note = normalize_text(note_body)
    if not note:
        return 0.0
    rendered = normalize_text(comments_cmd.body_for(comment, "inline"))
    raw = normalize_text(comment.get("body") or "")
    return max(
        difflib.SequenceMatcher(None, rendered, note).ratio(),
        difflib.SequenceMatcher(None, raw, note).ratio(),
    )


def note_anchor(note: dict) -> tuple[str | None, int | None]:
    position = note.get("position") or {}
    path = position.get("new_path") or position.get("old_path")
    line = position.get("new_line") or position.get("old_line")
    return path, line


def find_duplicate_note(comment: dict, notes: list[dict]) -> dict | None:
    anchor = comment.get("anchor") or {}
    path = anchor.get("path")
    line = anchor.get("line")
    for note in notes:
        if note.get("system"):
            continue
        note_path, note_line = note_anchor(note)
        if note_path != path or note_line != line:
            continue
        if similarity(comment, note.get("body") or "") >= 0.9:
            return note
    return None


# ---------------------------------------------------------------------------
# glab transport
# ---------------------------------------------------------------------------


def glab_json(host: str, method: str, endpoint: str, payload=None):
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
                "https://gitlab.com/gitlab-org/cli#installation. The rendered "
                "mr-comments.md still works as copy-paste."
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


def request(state: dict, method: str, endpoint: str, payload=None):
    return glab_json(state["mr"]["host"], method, endpoint, payload)


def list_draft_notes(state: dict) -> list[dict]:
    data = request(state, "GET", mr_endpoint(state, "/draft_notes?per_page=100"))
    return data if isinstance(data, list) else []


def list_notes(state: dict) -> list[dict]:
    notes: list[dict] = []
    for page in range(1, 21):
        data = request(
            state,
            "GET",
            mr_endpoint(state, f"/discussions?per_page=100&page={page}"),
        )
        if not isinstance(data, list) or not data:
            break
        for discussion in data:
            for note in discussion.get("notes") or []:
                notes.append(note)
        if len(data) < 100:
            break
    return notes


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


def current_head() -> tuple[Path, str]:
    root = repo_root()
    if root is None:
        raise ScriptError("Not inside a git repository.")
    proc = run(["git", "rev-parse", "HEAD"], cwd=root, check=False)
    if proc.returncode != 0:
        raise ScriptError("Could not resolve HEAD.")
    return root, proc.stdout.strip()


def ensure_head(state: dict) -> tuple[Path, str]:
    root, head = current_head()
    expected = (state.get("mr") or {}).get("headSha")
    if expected and head != expected:
        raise ScriptError(
            f"HEAD moved from {str(expected)[:7]} to {head[:7]}. Run "
            "`comments.py verify` and `comments.py render` before posting."
        )
    return root, head


def verify_selected(state: dict, selected: list[dict], root: Path, head: str) -> None:
    if not selected:
        return
    ranges = verify_anchors.parse_diff(state["mr"]["base"], head, root)
    for comment in selected:
        status, detail = verify_anchors.verify_anchor(
            comment.get("anchor") or {}, ranges, root, head
        )
        if status != "ok":
            raise ScriptError(
                f"{comment['id']} anchor is {status}: {detail}. Run "
                "`comments.py verify` and re-anchor or drop it."
            )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_preview(state: dict, one: str | None) -> int:
    entries = preview_entries(state, one)
    if not entries:
        print("Nothing to stage: no draft or approved comments without a posted note.")
        return 0
    for entry in entries:
        print(f"{entry['id']}  {entry['kind']:<7} {entry['method']} {entry['endpoint']}")
    print("\nPayloads:\n")
    print(json.dumps(entries, indent=2, ensure_ascii=False))
    print(
        "\nPreview only. Re-run with --create to create author-only draft notes."
    )
    return 0


def cmd_create(state_path: Path, state: dict, one: str | None) -> int:
    root, head = ensure_head(state)
    selected = creatable(state, one)
    if not selected:
        print("Nothing to create: no draft or approved comments without a draft note.")
        return 0

    verify_selected(state, selected, root, head)

    existing_drafts = list_draft_notes(state)
    existing_ids = {note.get("id") for note in existing_drafts}
    notes = list_notes(state)

    created: list[str] = []
    for comment in selected:
        posted = comment.setdefault("posted", {})
        draft_id = posted.get("draftNoteId")
        if draft_id and draft_id in existing_ids:
            continue
        if draft_id and draft_id not in existing_ids:
            # The draft was published or deleted outside this run.
            continue
        if posted.get("noteId"):
            continue

        duplicate = find_duplicate_note(comment, notes)
        if duplicate:
            posted["noteId"] = duplicate.get("id")
            add_event(
                state,
                "skipped-duplicate",
                f"{comment['id']} already discussed in note {duplicate.get('id')}",
            )
            save_state(state_path, state)
            print(
                f"{comment['id']}  skipped-duplicate  existing note "
                f"{duplicate.get('id')}"
            )
            continue

        if (comment.get("anchor") or {}).get("kind") == "mr":
            # Draft notes require a position; MR-level notes post at publish time.
            continue

        payload = build_draft_payload(comment, state)
        try:
            response = request(state, "POST", mr_endpoint(state, "/draft_notes"), payload)
        except ScriptError as error:
            created_text = ", ".join(created) if created else "none"
            hint = ""
            if "400" in str(error):
                hint = " The position may be invalid; run `comments.py verify` first."
            raise ScriptError(
                f"Creating {comment['id']} failed. Draft notes created before the "
                f"failure: {created_text}. Nothing was published.{hint}\n{error}"
            ) from error
        posted["draftNoteId"] = (response or {}).get("id")
        created.append(comment["id"])
        add_event(
            state, "draft-created", f"{comment['id']} draft={posted.get('draftNoteId')}"
        )
        save_state(state_path, state)
        print(f"{comment['id']}  draft-created  draft_note={posted.get('draftNoteId')}")

    if created:
        print(
            f"\n{len(created)} draft note(s) created. They are visible only to you. "
            "Run --publish when you are ready."
        )
    else:
        print("No new draft notes were created.")
    return 0


def _map_published(result, comments: list[dict]) -> dict:
    """Map published notes back to comments by path and line when possible."""
    mapping: dict[str, int] = {}
    if not isinstance(result, list):
        return mapping
    by_position = {}
    for note in result:
        if not isinstance(note, dict):
            continue
        position = note.get("position") or {}
        key = (position.get("new_path"), position.get("new_line"))
        if key != (None, None):
            by_position[key] = note.get("id")
    for comment in comments:
        anchor = comment.get("anchor") or {}
        key = (anchor.get("path"), anchor.get("line"))
        if key in by_position:
            mapping[comment["id"]] = by_position[key]
    return mapping


def cmd_publish(state_path: Path, state: dict, one: str | None) -> int:
    root, head = ensure_head(state)
    wanted = normalize_id(one)

    if wanted:
        matches = [
            comment for comment in state.get("comments", [])
            if comment.get("id") == wanted
        ]
        if not matches:
            raise ScriptError(f"{wanted} does not exist.")
        candidate = matches[0]
        if candidate.get("status") != "approved" or (
            candidate.get("posted") or {}
        ).get("postedAt"):
            raise ScriptError(
                f"{wanted} is not approved or was already posted; refusing to publish."
            )

    selected = publishable(state, one)
    if not selected:
        print("Nothing to publish: no approved comments are waiting.")
        return 0

    stale = [
        comment["id"]
        for comment in selected
        if (comment.get("anchor") or {}).get("verifiedAt") != head
    ]
    if stale:
        raise ScriptError(
            f"Verification is stale for {', '.join(stale)}. Run "
            "`comments.py verify` at the current HEAD before publishing."
        )

    draft_comments = [
        comment
        for comment in selected
        if (comment.get("anchor") or {}).get("kind") != "mr"
    ]
    mr_comments = [
        comment for comment in selected
        if (comment.get("anchor") or {}).get("kind") == "mr"
    ]

    for comment in draft_comments:
        posted = comment.get("posted") or {}
        if not posted.get("draftNoteId"):
            raise ScriptError(
                f"{comment['id']} has no draft note. Run `post_comments.py --create` first."
            )

    # GitLab's bulk endpoint publishes every pending draft, including drafts the
    # user has not approved. Fall back to per-note publishing when the state
    # knows about a draft outside the approved set.
    approved_ids = {comment["id"] for comment in selected}
    unapproved_drafts = [
        comment for comment in state.get("comments", [])
        if (comment.get("posted") or {}).get("draftNoteId")
        and comment.get("id") not in approved_ids
        and comment.get("status") != "posted"
    ]
    use_bulk = not wanted and not unapproved_drafts and len(draft_comments) > 1

    published_map: dict[str, int] = {}
    if draft_comments:
        if wanted or not use_bulk:
            for comment in draft_comments:
                draft_id = comment["posted"]["draftNoteId"]
                response = request(
                    state,
                    "PUT",
                    mr_endpoint(state, f"/draft_notes/{draft_id}/publish"),
                    {},
                )
                mapped = _map_published(
                    response if isinstance(response, list) else [response],
                    [comment],
                )
                published_map.update(mapped)
                comment["status"] = "posted"
                comment.setdefault("posted", {})["postedAt"] = now_iso()
                if comment["id"] in mapped:
                    comment["posted"]["noteId"] = mapped[comment["id"]]
                add_event(state, "published", f"{comment['id']}")
                save_state(state_path, state)
        else:
            response = request(
                state, "POST", mr_endpoint(state, "/draft_notes/bulk_publish"), {}
            )
            published_map = _map_published(response, draft_comments)
            for comment in draft_comments:
                comment["status"] = "posted"
                comment.setdefault("posted", {})["postedAt"] = now_iso()
                if comment["id"] in published_map:
                    comment["posted"]["noteId"] = published_map[comment["id"]]
                add_event(state, "published", f"{comment['id']}")
            save_state(state_path, state)

    for comment in mr_comments:
        payload = build_note_payload(comment, state)
        try:
            response = request(state, "POST", mr_endpoint(state, "/notes"), payload)
        except ScriptError as error:
            raise ScriptError(
                "Draft notes were published, but the MR-level note for "
                f"{comment['id']} failed. Review the MR before retrying.\n{error}"
            ) from error
        comment["status"] = "posted"
        comment.setdefault("posted", {})["noteId"] = (response or {}).get("id")
        comment["posted"]["postedAt"] = now_iso()
        add_event(state, "published", f"{comment['id']}")
        save_state(state_path, state)

    print(f"Published {len(selected)} comment(s) at {head[:7]}.")
    for comment in selected:
        note_id = (comment.get("posted") or {}).get("noteId")
        suffix = f" note={note_id}" if note_id else ""
        print(f"  {comment['id']}{suffix}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview, stage, and publish GitLab MR comments."
    )
    parser.add_argument("--create", action="store_true", help="Create draft notes")
    parser.add_argument("--publish", action="store_true", help="Publish approved notes")
    parser.add_argument("--one", help="Limit to one comment id, e.g. C2")
    parser.add_argument("--state", help="Explicit path to the state JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.create and args.publish:
        raise ScriptError("Pass either --create or --publish, not both.")

    state_path = comments_cmd.resolve_state_file(args.state)
    state = load_state(state_path)

    if args.create:
        return cmd_create(state_path, state, args.one)
    if args.publish:
        return cmd_publish(state_path, state, args.one)
    return cmd_preview(state, args.one)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ScriptError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
