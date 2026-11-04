#!/usr/bin/env python3
"""Tests for preview payloads, publishing gates, and dedupe (no network)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

import _common  # noqa: E402
import helpers  # noqa: E402
import post_comments  # noqa: E402

HEAD = "a" * 40
OLD = "b" * 40


def make_comment(
    cid: str = "C1",
    *,
    kind: str = "inline",
    status: str = "draft",
    verified_at: str = HEAD,
    draft_id=None,
    note_id=None,
    title: str = "A title",
    body: str = "A body line.",
    path: str = "a.ts",
    line: int | None = 4,
) -> dict:
    anchor = {
        "kind": kind,
        "path": path if kind != "mr" else None,
        "line": line if kind == "inline" else None,
        "endLine": None,
        "inDiff": True if kind != "mr" else None,
        "verifiedAt": verified_at,
        "verifiedHash": None,
        "verifiedText": None,
    }
    return {
        "id": cid,
        "status": status,
        "type": "question",
        "severity": "nit",
        "anchor": anchor,
        "evidence": "a.ts:4",
        "source": {
            "kind": "diff",
            "decision": "open",
            "confidence": "medium",
            "quote": None,
        },
        "title": title,
        "body": body,
        "suggestion": None,
        "long": False,
        "posted": {
            "draftNoteId": draft_id,
            "noteId": note_id,
            "postedAt": None,
        },
    }


def make_state(comments: list[dict], head: str = HEAD) -> dict:
    return {
        "schemaVersion": 1,
        "lang": "en",
        "createdAt": "2026-11-04T10:00:00Z",
        "mr": {
            "provider": "gitlab",
            "host": "gitlab.example.com",
            "project": "team/api",
            "iid": "2340",
            "webUrl": "https://gitlab.example.com/team/api/-/merge_requests/2340",
            "base": "main",
            "sourceBranch": "feat",
            "targetBranch": "main",
            "headSha": head,
            "diffRefs": {
                "base_sha": "1111111111111111111111111111111111111111",
                "start_sha": "2222222222222222222222222222222222222222",
                "head_sha": head,
            },
        },
        "budget": {"target": 5, "max": 10, "forced": False},
        "comments": comments,
        "dropped": [],
        "events": [],
    }


def silence(fn):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
        result = fn()
    return result, buffer.getvalue()


class PayloadTests(unittest.TestCase):
    def test_payload_maps_diff_refs(self):
        state = make_state([make_comment()])
        payload = post_comments.build_draft_payload(state["comments"][0], state)
        self.assertEqual(payload["position"]["base_sha"], state["mr"]["diffRefs"]["base_sha"])
        self.assertEqual(payload["position"]["start_sha"], state["mr"]["diffRefs"]["start_sha"])
        self.assertEqual(payload["position"]["head_sha"], HEAD)

    def test_inline_payload_shape(self):
        state = make_state([make_comment(path="src/a.ts", line=12)])
        payload = post_comments.build_draft_payload(state["comments"][0], state)
        position = payload["position"]
        self.assertEqual(position["position_type"], "text")
        self.assertEqual(position["old_path"], "src/a.ts")
        self.assertEqual(position["new_path"], "src/a.ts")
        self.assertEqual(position["new_line"], 12)
        self.assertIn("**A title**", payload["body"])

    def test_file_payload_shape(self):
        state = make_state([make_comment(kind="file", path="src/a.ts")])
        payload = post_comments.build_draft_payload(state["comments"][0], state)
        position = payload["position"]
        self.assertEqual(position["position_type"], "file")
        self.assertEqual(position["new_path"], "src/a.ts")
        self.assertNotIn("new_line", position)
        self.assertNotIn("old_path", position)

    def test_mr_anchor_produces_a_note_payload(self):
        state = make_state([make_comment(kind="mr")])
        self.assertIsNone(post_comments.build_draft_payload(state["comments"][0], state))
        entries = post_comments.preview_entries(state)
        self.assertEqual(entries[0]["kind"], "mr")
        self.assertTrue(entries[0]["endpoint"].endswith("/notes"))
        self.assertIn("### A title", entries[0]["payload"]["body"])

    def test_missing_diff_refs_is_an_error(self):
        state = make_state([make_comment()])
        state["mr"]["diffRefs"] = {}
        with self.assertRaises(_common.ScriptError):
            post_comments.build_draft_payload(state["comments"][0], state)


class PreviewTests(unittest.TestCase):
    def test_preview_makes_zero_subprocess_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            _common.save_state(path, make_state([make_comment()]))
            with mock.patch.object(
                post_comments, "run", side_effect=AssertionError("no subprocess")
            ):
                _, output = silence(
                    lambda: post_comments.main(["--state", str(path)])
                )
        self.assertIn("draft_notes", output)
        self.assertIn("Preview only", output)


class PublishGateTests(unittest.TestCase):
    def test_publish_refuses_unapproved(self):
        state = make_state([make_comment(status="draft", draft_id=3)])
        with mock.patch.object(post_comments, "ensure_head", return_value=(Path("."), HEAD)):
            with mock.patch.object(post_comments, "request", side_effect=AssertionError):
                with self.assertRaises(_common.ScriptError) as caught:
                    post_comments.cmd_publish(Path("state.json"), state, "C1")
        self.assertIn("not approved", str(caught.exception))

    def test_publish_refuses_when_head_moved(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "repo"
        helpers.build_repo(root)
        old_cwd = Path.cwd()
        self.addCleanup(os.chdir, old_cwd)
        os.chdir(root)
        state = make_state([make_comment(status="approved", draft_id=3)], head=OLD)
        with mock.patch.object(post_comments, "request", side_effect=AssertionError):
            with self.assertRaises(_common.ScriptError) as caught:
                post_comments.cmd_publish(Path("state.json"), state, None)
        self.assertIn("HEAD moved", str(caught.exception))

    def test_publish_refuses_stale_verification(self):
        state = make_state(
            [make_comment(status="approved", draft_id=3, verified_at=OLD)]
        )
        with mock.patch.object(post_comments, "ensure_head", return_value=(Path("."), HEAD)):
            with mock.patch.object(post_comments, "request", side_effect=AssertionError):
                with self.assertRaises(_common.ScriptError) as caught:
                    post_comments.cmd_publish(Path("state.json"), state, None)
        self.assertIn("Verification is stale", str(caught.exception))

    def test_publish_refuses_missing_draft_note(self):
        state = make_state([make_comment(status="approved")])
        with mock.patch.object(post_comments, "ensure_head", return_value=(Path("."), HEAD)):
            with mock.patch.object(post_comments, "request", side_effect=AssertionError):
                with self.assertRaises(_common.ScriptError) as caught:
                    post_comments.cmd_publish(Path("state.json"), state, None)
        self.assertIn("--create", str(caught.exception))


class DedupeTests(unittest.TestCase):
    def test_near_identical_note_is_a_duplicate(self):
        comment = make_comment()
        body = post_comments.comments_cmd.body_for(comment, "inline")
        note = {"id": 99, "body": body, "position": {"new_path": "a.ts", "new_line": 4}}
        self.assertIs(post_comments.find_duplicate_note(comment, [note]), note)

    def test_different_anchor_is_not_a_duplicate(self):
        comment = make_comment()
        note = {
            "id": 99,
            "body": post_comments.comments_cmd.body_for(comment, "inline"),
            "position": {"new_path": "b.ts", "new_line": 4},
        }
        self.assertIsNone(post_comments.find_duplicate_note(comment, [note]))

    def test_create_records_skipped_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = make_state([make_comment()])
            _common.save_state(path, state)
            note = {
                "id": 99,
                "body": post_comments.comments_cmd.body_for(state["comments"][0], "inline"),
                "position": {"new_path": "a.ts", "new_line": 4},
            }
            calls = []

            def fake_request(state_, method, endpoint, payload=None):
                calls.append((method, endpoint))
                if "/draft_notes?per_page" in endpoint:
                    return []
                if "discussions" in endpoint:
                    return [{"id": "d1", "notes": [note]}]
                raise AssertionError("unexpected call")

            with mock.patch.object(
                post_comments, "ensure_head", return_value=(Path("."), HEAD)
            ), mock.patch.object(post_comments, "verify_selected"), mock.patch.object(
                post_comments, "request", side_effect=fake_request
            ):
                _, output = silence(
                    lambda: post_comments.cmd_create(path, state, None)
                )
            saved = _common.load_state(path)
        self.assertIn("skipped-duplicate", output)
        self.assertEqual(saved["comments"][0]["posted"]["noteId"], 99)
        self.assertTrue(
            any(event["kind"] == "skipped-duplicate" for event in saved["events"])
        )
        self.assertFalse(any(method == "POST" for method, _ in calls))


class CreateTests(unittest.TestCase):
    def test_create_is_idempotent_when_a_draft_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = make_state([make_comment(draft_id=5)])
            _common.save_state(path, state)
            with mock.patch.object(
                post_comments, "ensure_head", return_value=(Path("."), HEAD)
            ), mock.patch.object(
                post_comments, "request", side_effect=AssertionError("no network")
            ):
                _, output = silence(
                    lambda: post_comments.cmd_create(path, state, None)
                )
        self.assertIn("Nothing to create", output)

    def test_partial_batch_failure_reports_created_drafts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = make_state(
                [make_comment(cid="C1"), make_comment(cid="C2", body="Second body.")]
            )
            _common.save_state(path, state)
            calls = []
            posts = {"count": 0}

            def fake_request(state_, method, endpoint, payload=None):
                calls.append((method, endpoint))
                if "/draft_notes?per_page" in endpoint:
                    return []
                if "discussions" in endpoint:
                    return []
                posts["count"] += 1
                if posts["count"] == 1:
                    return {"id": 11}
                raise _common.ScriptError("boom")

            with mock.patch.object(
                post_comments, "ensure_head", return_value=(Path("."), HEAD)
            ), mock.patch.object(post_comments, "verify_selected"), mock.patch.object(
                post_comments, "request", side_effect=fake_request
            ):
                with self.assertRaises(_common.ScriptError) as caught:
                    silence(lambda: post_comments.cmd_create(path, state, None))
            saved = _common.load_state(path)
        message = str(caught.exception)
        self.assertIn("C1", message)
        self.assertIn("Nothing was published", message)
        self.assertEqual(saved["comments"][0]["posted"]["draftNoteId"], 11)
        self.assertIsNone(saved["comments"][1]["posted"]["draftNoteId"])
        self.assertFalse(any("publish" in endpoint for _, endpoint in calls))

    def test_one_scopes_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = make_state(
                [make_comment(cid="C1"), make_comment(cid="C2", body="Second body.")]
            )
            _common.save_state(path, state)
            posts = []

            def fake_request(state_, method, endpoint, payload=None):
                if "/draft_notes?per_page" in endpoint:
                    return []
                if "discussions" in endpoint:
                    return []
                posts.append(payload)
                return {"id": 22}

            with mock.patch.object(
                post_comments, "ensure_head", return_value=(Path("."), HEAD)
            ), mock.patch.object(post_comments, "verify_selected"), mock.patch.object(
                post_comments, "request", side_effect=fake_request
            ):
                silence(lambda: post_comments.cmd_create(path, state, "C2"))
            saved = _common.load_state(path)
        self.assertEqual(len(posts), 1)
        self.assertIsNone(saved["comments"][0]["posted"]["draftNoteId"])
        self.assertEqual(saved["comments"][1]["posted"]["draftNoteId"], 22)


class PublishScopeTests(unittest.TestCase):
    def test_one_scopes_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = make_state(
                [
                    make_comment(cid="C1", status="approved", draft_id=1),
                    make_comment(cid="C2", status="approved", draft_id=2, body="Second body."),
                ]
            )
            _common.save_state(path, state)
            calls = []

            def fake_request(state_, method, endpoint, payload=None):
                calls.append((method, endpoint))
                return {"id": 202, "position": {"new_path": "a.ts", "new_line": 4}}

            with mock.patch.object(
                post_comments, "ensure_head", return_value=(Path("."), HEAD)
            ), mock.patch.object(
                post_comments, "request", side_effect=fake_request
            ):
                silence(lambda: post_comments.cmd_publish(path, state, "C2"))
            saved = _common.load_state(path)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "PUT")
        self.assertIn("/draft_notes/2/publish", calls[0][1])
        self.assertEqual(saved["comments"][0]["status"], "approved")
        self.assertEqual(saved["comments"][1]["status"], "posted")

    def test_bulk_publish_is_used_for_multiple_approved_drafts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = make_state(
                [
                    make_comment(cid="C1", status="approved", draft_id=1),
                    make_comment(cid="C2", status="approved", draft_id=2, body="Second body."),
                ]
            )
            _common.save_state(path, state)
            calls = []

            def fake_request(state_, method, endpoint, payload=None):
                calls.append((method, endpoint))
                return []

            with mock.patch.object(
                post_comments, "ensure_head", return_value=(Path("."), HEAD)
            ), mock.patch.object(
                post_comments, "request", side_effect=fake_request
            ):
                silence(lambda: post_comments.cmd_publish(path, state, None))
            saved = _common.load_state(path)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "POST")
        self.assertIn("bulk_publish", calls[0][1])
        self.assertEqual([comment["status"] for comment in saved["comments"]], ["posted", "posted"])


class TransportTests(unittest.TestCase):
    def test_missing_glab_is_actionable(self):
        error = _common.ScriptError("`glab` is not installed or not on PATH.")
        with mock.patch.object(post_comments, "run", side_effect=error):
            with self.assertRaises(_common.ScriptError) as caught:
                post_comments.glab_json("gitlab.example.com", "GET", "projects/x")
        self.assertIn("Install it from", str(caught.exception))

    def test_non_json_output_is_an_error(self):
        proc = mock.Mock(stdout="not json", stderr="", returncode=0)
        with mock.patch.object(post_comments, "run", return_value=proc):
            with self.assertRaises(_common.ScriptError) as caught:
                post_comments.glab_json("gitlab.example.com", "GET", "projects/x")
        self.assertIn("non-JSON", str(caught.exception))

    def test_auth_failure_mentions_api_scope(self):
        error = _common.ScriptError("401 Unauthorized")
        with mock.patch.object(post_comments, "run", side_effect=error):
            with self.assertRaises(_common.ScriptError) as caught:
                post_comments.glab_json("gitlab.example.com", "GET", "projects/x")
        self.assertIn("api` scope", str(caught.exception))

    def test_json_output_is_parsed(self):
        proc = mock.Mock(stdout=json.dumps({"id": 5}), stderr="", returncode=0)
        with mock.patch.object(post_comments, "run", return_value=proc):
            self.assertEqual(
                post_comments.glab_json("gitlab.example.com", "GET", "projects/x"),
                {"id": 5},
            )


if __name__ == "__main__":
    unittest.main()
