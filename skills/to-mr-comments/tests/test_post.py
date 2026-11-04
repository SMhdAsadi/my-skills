#!/usr/bin/env python3
"""Tests for preview payloads, posting gates, dedupe, and transport (no network)."""

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

# The staging endpoint this skill no longer uses. Built from parts so a grep for
# the literal name proves it is gone from the code while the tests still assert it.
REMOVED_ENDPOINT = "/draft" + "_notes"


def make_comment(
    cid: str = "C1",
    *,
    kind: str = "inline",
    status: str = "pending",
    verified_at: str = HEAD,
    note_id=None,
    discussion_id=None,
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
            "noteId": note_id,
            "discussionId": discussion_id,
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


def fake_gitlab(state_: dict, method: str, endpoint: str, payload=None):
    """A minimal transport: no discussions, one created note per POST."""
    if method == "GET":
        return []
    if endpoint.endswith("/discussions"):
        return {"id": "d1", "notes": [{"id": 500}]}
    return {"id": 700}


class PayloadTests(unittest.TestCase):
    def test_payload_maps_diff_refs(self):
        state = make_state([make_comment()])
        payload = post_comments.build_discussion_payload(state["comments"][0], state)
        self.assertEqual(payload["position"]["base_sha"], state["mr"]["diffRefs"]["base_sha"])
        self.assertEqual(payload["position"]["start_sha"], state["mr"]["diffRefs"]["start_sha"])
        self.assertEqual(payload["position"]["head_sha"], HEAD)

    def test_inline_payload_shape(self):
        state = make_state([make_comment(path="src/a.ts", line=12)])
        payload = post_comments.build_discussion_payload(state["comments"][0], state)
        position = payload["position"]
        self.assertEqual(set(payload), {"body", "position"})
        self.assertEqual(position["position_type"], "text")
        self.assertEqual(position["old_path"], "src/a.ts")
        self.assertEqual(position["new_path"], "src/a.ts")
        self.assertEqual(position["new_line"], 12)
        self.assertIn("**A title**", payload["body"])
        self.assertNotIn("note", payload)

    def test_file_payload_shape(self):
        state = make_state([make_comment(kind="file", path="src/a.ts")])
        payload = post_comments.build_discussion_payload(state["comments"][0], state)
        position = payload["position"]
        self.assertEqual(position["position_type"], "file")
        self.assertEqual(position["new_path"], "src/a.ts")
        self.assertNotIn("new_line", position)
        self.assertNotIn("old_path", position)

    def test_mr_anchor_produces_a_note_payload(self):
        state = make_state([make_comment(kind="mr")])
        self.assertIsNone(
            post_comments.build_discussion_payload(state["comments"][0], state)
        )
        entries = post_comments.preview_entries(state)
        self.assertEqual(entries[0]["kind"], "mr")
        self.assertTrue(entries[0]["endpoint"].endswith("/notes"))
        self.assertEqual(set(entries[0]["payload"]), {"body"})
        self.assertIn("### A title", entries[0]["payload"]["body"])

    def test_inline_preview_targets_discussions(self):
        state = make_state([make_comment()])
        entries = post_comments.preview_entries(state)
        self.assertTrue(entries[0]["endpoint"].endswith("/discussions"))
        self.assertIn("position", entries[0]["payload"])

    def test_missing_diff_refs_is_an_error(self):
        state = make_state([make_comment()])
        state["mr"]["diffRefs"] = {}
        with self.assertRaises(_common.ScriptError):
            post_comments.build_discussion_payload(state["comments"][0], state)


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
        self.assertIn("/discussions", output)
        self.assertIn("Preview only", output)
        self.assertNotIn(REMOVED_ENDPOINT, output)


class PostGateTests(unittest.TestCase):
    def test_post_refuses_unapproved(self):
        state = make_state([make_comment(status="pending")])
        with mock.patch.object(post_comments, "ensure_head", return_value=(Path("."), HEAD)):
            with mock.patch.object(post_comments, "request", side_effect=AssertionError):
                with self.assertRaises(_common.ScriptError) as caught:
                    post_comments.cmd_post(Path("state.json"), state, "C1")
        self.assertIn("not approved", str(caught.exception))

    def test_post_refuses_when_head_moved(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "repo"
        helpers.build_repo(root)
        old_cwd = Path.cwd()
        self.addCleanup(os.chdir, old_cwd)
        os.chdir(root)
        state = make_state([make_comment(status="approved")], head=OLD)
        with mock.patch.object(post_comments, "request", side_effect=AssertionError):
            with self.assertRaises(_common.ScriptError) as caught:
                post_comments.cmd_post(Path("state.json"), state, None)
        self.assertIn("HEAD moved", str(caught.exception))

    def test_post_refuses_already_posted_with_one(self):
        state = make_state(
            [make_comment(status="posted", note_id=12, discussion_id="d1")]
        )
        with mock.patch.object(post_comments, "ensure_head", return_value=(Path("."), HEAD)):
            with mock.patch.object(post_comments, "request", side_effect=AssertionError):
                with self.assertRaises(_common.ScriptError) as caught:
                    post_comments.cmd_post(Path("state.json"), state, "C1")
        self.assertIn("already posted", str(caught.exception))


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

    def test_system_note_is_ignored(self):
        comment = make_comment()
        note = {
            "id": 99,
            "system": True,
            "body": post_comments.comments_cmd.body_for(comment, "inline"),
            "position": {"new_path": "a.ts", "new_line": 4},
        }
        self.assertIsNone(post_comments.find_duplicate_note(comment, [note]))

    def test_post_skips_duplicate_discussion(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = make_state([make_comment(status="approved")])
            _common.save_state(path, state)
            note = {
                "id": 99,
                "body": post_comments.comments_cmd.body_for(state["comments"][0], "inline"),
                "position": {"new_path": "a.ts", "new_line": 4},
            }
            calls = []

            def fake_request(state_, method, endpoint, payload=None):
                calls.append((method, endpoint))
                if "discussions" in endpoint and method == "GET":
                    return [{"id": "d1", "notes": [note]}]
                raise AssertionError("unexpected call")

            with mock.patch.object(
                post_comments, "ensure_head", return_value=(Path("."), HEAD)
            ), mock.patch.object(post_comments, "verify_selected"), mock.patch.object(
                post_comments, "request", side_effect=fake_request
            ):
                _, output = silence(
                    lambda: post_comments.cmd_post(path, state, None)
                )
            saved = _common.load_state(path)
        self.assertIn("skipped-duplicate", output)
        self.assertEqual(saved["comments"][0]["posted"]["noteId"], 99)
        self.assertEqual(saved["comments"][0]["posted"]["discussionId"], "d1")
        self.assertTrue(
            any(event["kind"] == "skipped-duplicate" for event in saved["events"])
        )
        self.assertFalse(any(method == "POST" for method, _ in calls))


class PostTests(unittest.TestCase):
    def test_post_creates_inline_discussion_and_records_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = make_state([make_comment(status="approved")])
            _common.save_state(path, state)
            calls = []

            def fake_request(state_, method, endpoint, payload=None):
                calls.append((method, endpoint, payload))
                return fake_gitlab(state_, method, endpoint, payload)

            with mock.patch.object(
                post_comments, "ensure_head", return_value=(Path("."), HEAD)
            ), mock.patch.object(post_comments, "verify_selected"), mock.patch.object(
                post_comments, "request", side_effect=fake_request
            ):
                _, output = silence(lambda: post_comments.cmd_post(path, state, None))
            saved = _common.load_state(path)
        posts = [call for call in calls if call[0] == "POST"]
        self.assertEqual(len(posts), 1)
        self.assertTrue(posts[0][1].endswith("/discussions"))
        self.assertEqual(set(posts[0][2]), {"body", "position"})
        comment = saved["comments"][0]
        self.assertEqual(comment["status"], "posted")
        self.assertEqual(comment["posted"]["noteId"], 500)
        self.assertEqual(comment["posted"]["discussionId"], "d1")
        self.assertIn("#note_500", output)

    def test_post_creates_mr_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = make_state([make_comment(kind="mr", status="approved")])
            _common.save_state(path, state)
            calls = []

            def fake_request(state_, method, endpoint, payload=None):
                calls.append((method, endpoint, payload))
                return fake_gitlab(state_, method, endpoint, payload)

            with mock.patch.object(
                post_comments, "ensure_head", return_value=(Path("."), HEAD)
            ), mock.patch.object(post_comments, "verify_selected"), mock.patch.object(
                post_comments, "request", side_effect=fake_request
            ):
                _, output = silence(lambda: post_comments.cmd_post(path, state, None))
            saved = _common.load_state(path)
        posts = [call for call in calls if call[0] == "POST"]
        self.assertEqual(len(posts), 1)
        self.assertTrue(posts[0][1].endswith("/notes"))
        self.assertEqual(set(posts[0][2]), {"body"})
        self.assertEqual(saved["comments"][0]["posted"]["noteId"], 700)
        self.assertIn("#note_700", output)

    def test_one_scopes_post(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = make_state(
                [
                    make_comment(cid="C1", status="approved"),
                    make_comment(cid="C2", status="approved", body="Second body."),
                ]
            )
            _common.save_state(path, state)
            posts = []

            def fake_request(state_, method, endpoint, payload=None):
                if method == "GET":
                    return []
                posts.append(payload)
                return {"id": "d1", "notes": [{"id": 22}]}

            with mock.patch.object(
                post_comments, "ensure_head", return_value=(Path("."), HEAD)
            ), mock.patch.object(post_comments, "verify_selected"), mock.patch.object(
                post_comments, "request", side_effect=fake_request
            ):
                silence(lambda: post_comments.cmd_post(path, state, "C2"))
            saved = _common.load_state(path)
        self.assertEqual(len(posts), 1)
        self.assertEqual(saved["comments"][0]["status"], "approved")
        self.assertIsNone(saved["comments"][0]["posted"]["noteId"])
        self.assertEqual(saved["comments"][1]["status"], "posted")
        self.assertEqual(saved["comments"][1]["posted"]["noteId"], 22)

    def test_204_response_marks_comment_posted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = make_state([make_comment(status="approved")])
            _common.save_state(path, state)
            posts = {"count": 0}

            def fake_run(cmd, **kwargs):
                if "--method" in cmd:
                    posts["count"] += 1
                    return mock.Mock(stdout="", stderr="", returncode=0)
                return mock.Mock(stdout="[]", stderr="", returncode=0)

            with mock.patch.object(
                post_comments, "ensure_head", return_value=(Path("."), HEAD)
            ), mock.patch.object(post_comments, "verify_selected"), mock.patch.object(
                post_comments, "run", side_effect=fake_run
            ):
                _, output = silence(lambda: post_comments.cmd_post(path, state, None))
            saved = _common.load_state(path)
        self.assertEqual(posts["count"], 1)
        self.assertEqual(saved["comments"][0]["status"], "posted")
        self.assertIsNone(saved["comments"][0]["posted"]["noteId"])
        self.assertIsNotNone(saved["comments"][0]["posted"]["postedAt"])
        self.assertIn("posted", output)

    def test_no_request_touches_removed_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = make_state(
                [
                    make_comment(cid="C1", status="approved"),
                    make_comment(cid="C2", kind="mr", status="approved", body="Second body."),
                ]
            )
            _common.save_state(path, state)
            endpoints = []

            def fake_request(state_, method, endpoint, payload=None):
                endpoints.append(endpoint)
                return fake_gitlab(state_, method, endpoint, payload)

            with mock.patch.object(
                post_comments, "ensure_head", return_value=(Path("."), HEAD)
            ), mock.patch.object(post_comments, "verify_selected"), mock.patch.object(
                post_comments, "request", side_effect=fake_request
            ):
                silence(lambda: post_comments.cmd_post(path, state, None))
        self.assertTrue(endpoints)
        self.assertFalse(any(REMOVED_ENDPOINT in endpoint for endpoint in endpoints))

    def test_partial_failure_reports_posted_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = make_state(
                [
                    make_comment(cid="C1", status="approved"),
                    make_comment(cid="C2", status="approved", body="Second body."),
                ]
            )
            _common.save_state(path, state)
            posts = {"count": 0}

            def fake_request(state_, method, endpoint, payload=None):
                if method == "GET":
                    return []
                posts["count"] += 1
                if posts["count"] == 1:
                    return {"id": "d1", "notes": [{"id": 11}]}
                raise _common.ScriptError("boom")

            with mock.patch.object(
                post_comments, "ensure_head", return_value=(Path("."), HEAD)
            ), mock.patch.object(post_comments, "verify_selected"), mock.patch.object(
                post_comments, "request", side_effect=fake_request
            ):
                with self.assertRaises(_common.ScriptError) as caught:
                    silence(lambda: post_comments.cmd_post(path, state, None))
            saved = _common.load_state(path)
        message = str(caught.exception)
        self.assertIn("C1", message)
        self.assertIn("--one C2", message)
        self.assertEqual(saved["comments"][0]["status"], "posted")
        self.assertEqual(saved["comments"][0]["posted"]["noteId"], 11)
        self.assertEqual(saved["comments"][1]["status"], "approved")
        self.assertIsNone(saved["comments"][1]["posted"]["noteId"])


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

    def test_empty_get_response_is_an_error(self):
        proc = mock.Mock(stdout="", stderr="", returncode=0)
        with mock.patch.object(post_comments, "run", return_value=proc):
            with self.assertRaises(_common.ScriptError):
                post_comments.glab_json("gitlab.example.com", "GET", "projects/x")

    def test_empty_non_get_response_is_success_and_not_retried(self):
        # GitLab answers 204 No Content after a successful write. Parsing that
        # as a failure would look like an error and invite a duplicate retry.
        proc = mock.Mock(stdout="", stderr="", returncode=0)
        with mock.patch.object(post_comments, "run", return_value=proc) as run_mock:
            result = post_comments.glab_json(
                "gitlab.example.com",
                "POST",
                "projects/team%2Fapi/merge_requests/2340/discussions",
                {"body": "hi"},
            )
        self.assertEqual(result, {})
        self.assertEqual(run_mock.call_count, 1)

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
