#!/usr/bin/env python3
"""Preview and post rendered comments to a GitLab merge request.

No flag → preview the exact payloads and positions. Zero network calls.
--post  → create the real comments: discussions for inline/file anchors,
          regular notes for MR-level comments.
--one C2 → restrict the run to one comment.

One gate. Every check runs before the first write: HEAD must equal the state
HEAD, every selected comment must be approved, every anchor must verify at that
HEAD, and a near-identical live discussion is skipped instead of repeated.
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
            "`comments.py init --from-mr` before posting comments."
        )
    return refs


def build_discussion_payload(comment: dict, state: dict) -> dict | None:
    """Build a discussion payload, or None for an MR-level comment.

    The discussions endpoint takes the note text under `body`, not `note`.
    """
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
    """A regular MR note carries no position and takes the text under `body`."""
    return {"body": comments_cmd.body_for(comment, "summary")}


def post_endpoint(state: dict, comment: dict) -> str:
    if (comment.get("anchor") or {}).get("kind") == "mr":
        return mr_endpoint(state, "/notes")
    return mr_endpoint(state, "/discussions")


def preview_entries(state: dict, one: str | None = None) -> list[dict]:
    entries = []
    for comment in postable(state, one):
        if (comment.get("anchor") or {}).get("kind") == "mr":
            payload = build_note_payload(comment, state)
        else:
            payload = build_discussion_payload(comment, state)
        entries.append(
            {
                "id": comment["id"],
                "status": comment.get("status"),
                "kind": (comment.get("anchor") or {}).get("kind"),
                "method": "POST",
                "endpoint": post_endpoint(state, comment),
                "payload": payload,
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


def postable(state: dict, one: str | None = None) -> list[dict]:
    """Comments that still need a note: not dropped, not posted, no note yet."""
    wanted = normalize_id(one)
    result = []
    for comment in state.get("comments", []):
        if wanted and comment.get("id") != wanted:
            continue
        if comment.get("status") in ("dropped", "posted"):
            continue
        if (comment.get("posted") or {}).get("noteId"):
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


def note_ids(response) -> tuple[int | None, str | None]:
    """Return `(note_id, discussion_id)` from a note or a discussion response."""
    if not isinstance(response, dict):
        return None, None
    notes = response.get("notes")
    if isinstance(notes, list):
        note_id = notes[0].get("id") if notes else None
        return note_id, response.get("id")
    return response.get("id"), None


def note_link(state: dict, note_id) -> str:
    if not note_id:
        return ""
    web_url = (state.get("mr") or {}).get("webUrl") or ""
    return f"{web_url}#note_{note_id}"


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

    stdout = (proc.stdout or "").strip()
    if not stdout:
        # GitLab answers 204 No Content for writes that return no body. The
        # write succeeded; treating that as a parse failure invites a retry
        # that would duplicate the note.
        if method != "GET":
            return {}
        raise ScriptError(f"`{' '.join(cmd)}` returned an empty response.")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as error:
        raise ScriptError(
            f"`{' '.join(cmd)}` returned non-JSON output: {stdout[:200]!r}"
        ) from error


def request(state: dict, method: str, endpoint: str, payload=None):
    return glab_json(state["mr"]["host"], method, endpoint, payload)


def list_notes(state: dict) -> list[dict]:
    """Flatten every live discussion note, keeping its discussion id."""
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
                note.setdefault("discussion_id", discussion.get("id"))
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
        print("Nothing to post: no pending or approved comments without a note.")
        return 0
    for entry in entries:
        print(
            f"{entry['id']}  {entry['status']:<8} {entry['kind']:<7} "
            f"{entry['method']} {entry['endpoint']}"
        )
    print("\nPayloads:\n")
    print(json.dumps(entries, indent=2, ensure_ascii=False))
    print(
        "\nPreview only. Nothing was sent. After explicit approval, re-run "
        "with --post."
    )
    return 0


def cmd_post(state_path: Path, state: dict, one: str | None) -> int:
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
        if candidate.get("status") == "dropped":
            raise ScriptError(f"{wanted} was dropped; nothing to post.")
        if candidate.get("status") == "posted" or (
            candidate.get("posted") or {}
        ).get("noteId"):
            raise ScriptError(f"{wanted} is already posted; nothing to do.")

    selected = postable(state, one)
    if not selected:
        print("Nothing to post: no approved comments are waiting.")
        return 0

    unapproved = [
        comment["id"] for comment in selected
        if comment.get("status") != "approved"
    ]
    if unapproved:
        raise ScriptError(
            f"{', '.join(unapproved)} not approved. Run `comments.py approve` "
            "first: --post never sends a pending comment."
        )

    verify_selected(state, selected, root, head)
    notes = list_notes(state)

    posted_ids: list[str] = []
    skipped: list[str] = []
    for comment in selected:
        duplicate = find_duplicate_note(comment, notes)
        if duplicate:
            comment.setdefault("posted", {}).update(
                {
                    "noteId": duplicate.get("id"),
                    "discussionId": duplicate.get("discussion_id"),
                }
            )
            add_event(
                state,
                "skipped-duplicate",
                f"{comment['id']} already discussed in note {duplicate.get('id')}",
            )
            save_state(state_path, state)
            skipped.append(comment["id"])
            print(
                f"{comment['id']}  skipped-duplicate  existing note "
                f"{duplicate.get('id')}"
            )
            continue

        endpoint = post_endpoint(state, comment)
        if (comment.get("anchor") or {}).get("kind") == "mr":
            payload = build_note_payload(comment, state)
        else:
            payload = build_discussion_payload(comment, state)

        try:
            response = request(state, "POST", endpoint, payload)
        except ScriptError as error:
            done = ", ".join(posted_ids) if posted_ids else "none"
            hint = ""
            if "400" in str(error):
                hint = " The position may be invalid; run `comments.py verify` first."
            raise ScriptError(
                f"Posting {comment['id']} failed. Posted before the failure: "
                f"{done}. Retry just this comment with `--one {comment['id']}`."
                f"{hint}\n{error}"
            ) from error

        note_id, discussion_id = note_ids(response)
        comment["status"] = "posted"
        comment.setdefault("posted", {}).update(
            {
                "noteId": note_id,
                "discussionId": discussion_id,
                "postedAt": now_iso(),
            }
        )
        posted_ids.append(comment["id"])
        add_event(state, "posted", f"{comment['id']} note={note_id}")
        save_state(state_path, state)
        link = note_link(state, note_id)
        print(f"{comment['id']}  posted  {link}" if link else f"{comment['id']}  posted")

    if posted_ids:
        print(f"\nPosted {len(posted_ids)} comment(s) at {head[:7]}.")
    else:
        print("No new comments were posted.")
    if skipped:
        print(
            f"Skipped {len(skipped)} duplicate(s): "
            f"{', '.join(skipped)}. Nothing was repeated."
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview and post GitLab MR comments."
    )
    parser.add_argument("--post", action="store_true", help="Post approved comments")
    parser.add_argument("--one", help="Limit to one comment id, e.g. C2")
    parser.add_argument("--state", help="Explicit path to the state JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    state_path = comments_cmd.resolve_state_file(args.state)
    state = load_state(state_path)

    if args.post:
        return cmd_post(state_path, state, args.one)
    return cmd_preview(state, args.one)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ScriptError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
