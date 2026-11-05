#!/usr/bin/env python3
"""State-machine and gate-integrity tests for mr-comment-triage v2."""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import helpers  # noqa: E402
import _common  # noqa: E402
import fetch_threads as fetch  # noqa: E402
import post_reply as reply  # noqa: E402
import triage_state as state_cmd  # noqa: E402


def run_state(case: helpers.RepoCase, *argv):
    cap = helpers.capture()
    cap.run(state_cmd.main, ["--state", str(case.state_path), *argv])
    return cap


def run_post(case: helpers.RepoCase, *argv):
    cap = helpers.capture()
    cap.run(reply.main, ["--state", str(case.state_path), *argv])
    return cap


class SchemaTests(helpers.RepoCase, unittest.TestCase):
    def test_state_filename_is_gitlab_specific(self):
        path = _common.state_path(Path("/tmp"), "Team/Api", 2340)
        self.assertEqual(path.name, "gitlab-team-api-2340.json")

    def test_current_schema_version_is_two(self):
        self.assertEqual(_common.SCHEMA_VERSION, 2)
        self.assertEqual(state_cmd.ITEM_STATUSES, _common.ITEM_STATUSES)

    def test_load_state_accepts_v2(self):
        self.write_state()
        self.assertEqual(self.read_state()["schemaVersion"], 2)

    def test_load_state_rejects_v1_with_a_refetch_instruction(self):
        self.write_state({"schemaVersion": 1, "items": []})
        with self.assertRaises(_common.ScriptError) as caught:
            self.read_state()
        message = str(caught.exception).lower()
        self.assertIn("schema", message)
        self.assertIn("fetch", message)

    def test_load_state_rejects_unknown_version(self):
        self.write_state({"schemaVersion": 3, "items": []})
        with self.assertRaises(_common.ScriptError):
            self.read_state()

    def test_path_works_without_a_state_file(self):
        self.assertFalse(self.state_path.exists())
        cap = helpers.capture()
        cap.run(state_cmd.main, ["path"])
        self.assertEqual(cap.code, 0)
        self.assertIn(str(self.state_dir), cap.stdout)

    def test_path_prints_the_existing_state_file(self):
        self.write_state()
        cap = helpers.capture()
        cap.run(state_cmd.main, ["path"])
        self.assertEqual(cap.code, 0)
        self.assertIn(str(self.state_path), cap.stdout)

    def test_state_file_resolution_is_shared_by_both_commands(self):
        self.assertIs(reply.resolve_state_file, _common.resolve_state_file)

    def test_status_vocabulary_dropped_rejected(self):
        self.assertNotIn("rejected", _common.ITEM_STATUSES)
        self.assertEqual(
            _common.ITEM_STATUSES,
            ("proposed", "approved", "applied", "verified", "posted", "resolved", "skipped"),
        )


class SetTransitionTests(helpers.RepoCase, unittest.TestCase):
    def test_set_cannot_write_approved(self):
        self.write_state(items=[helpers.make_item(1)])
        cap = run_state(self, "set", "--item", "1", "--status", "approved")
        self.assertEqual(cap.code, 1)
        self.assertIn("approve", cap.stderr)
        self.assertEqual(self.read_state()["items"][0]["status"], "proposed")

    def test_set_cannot_write_posted(self):
        self.write_state(items=[helpers.make_item(1)])
        cap = run_state(self, "set", "--item", "1", "--status", "posted")
        self.assertEqual(cap.code, 1)
        self.assertIn("post_reply", cap.stderr)
        self.assertEqual(self.read_state()["items"][0]["status"], "proposed")

    def test_set_cannot_write_resolved(self):
        self.write_state(items=[helpers.make_item(1)])
        cap = run_state(self, "set", "--item", "1", "--status", "resolved")
        self.assertEqual(cap.code, 1)
        self.assertIn("post_reply", cap.stderr)

    def test_proposed_cannot_become_applied(self):
        self.write_state(items=[helpers.make_item(1)])
        cap = run_state(self, "set", "--item", "1", "--status", "applied")
        self.assertEqual(cap.code, 1)
        self.assertIn("approve", cap.stderr.lower())
        self.assertEqual(self.read_state()["items"][0]["status"], "proposed")

    def test_proposed_cannot_become_verified(self):
        self.write_state(items=[helpers.make_item(1)])
        cap = run_state(self, "set", "--item", "1", "--status", "verified")
        self.assertEqual(cap.code, 1)
        self.assertEqual(self.read_state()["items"][0]["status"], "proposed")

    def test_approved_can_become_applied(self):
        self.write_state(items=[helpers.make_item(1)])
        run_state(self, "approve", "all")
        cap = run_state(self, "set", "--item", "1", "--status", "applied")
        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual(self.read_state()["items"][0]["status"], "applied")

    def test_approved_can_become_verified_directly(self):
        self.write_state(items=[helpers.make_item(1)])
        run_state(self, "approve", "all")
        cap = run_state(self, "set", "--item", "1", "--status", "verified")
        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual(self.read_state()["items"][0]["status"], "verified")

    def test_applied_can_become_verified(self):
        self.write_state(items=[helpers.make_item(1)])
        run_state(self, "approve", "all")
        run_state(self, "set", "--item", "1", "--status", "applied")
        cap = run_state(self, "set", "--item", "1", "--status", "verified")
        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual(self.read_state()["items"][0]["status"], "verified")

    def test_applied_cannot_be_skipped(self):
        self.write_state(items=[helpers.make_item(1)])
        run_state(self, "approve", "all")
        run_state(self, "set", "--item", "1", "--status", "applied")
        cap = run_state(self, "set", "--item", "1", "--status", "skipped")
        self.assertEqual(cap.code, 1)
        self.assertEqual(self.read_state()["items"][0]["status"], "applied")

    def test_proposed_can_be_skipped(self):
        self.write_state(items=[helpers.make_item(1)])
        cap = run_state(self, "set", "--item", "1", "--status", "skipped")
        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual(self.read_state()["items"][0]["status"], "skipped")

    def test_approved_can_be_skipped_and_loses_approval(self):
        self.write_state(items=[helpers.make_item(1)])
        run_state(self, "approve", "all")
        cap = run_state(self, "set", "--item", "1", "--status", "skipped")
        self.assertEqual(cap.code, 0, cap.stderr)
        item = self.read_state()["items"][0]
        self.assertEqual(item["status"], "skipped")
        self.assertIsNone(item["approvedAt"])
        self.assertIsNone(item["approvalHash"])

    def test_approved_can_be_reset_to_proposed_and_loses_approval(self):
        self.write_state(items=[helpers.make_item(1)])
        run_state(self, "approve", "all")
        cap = run_state(self, "set", "--item", "1", "--status", "proposed")
        self.assertEqual(cap.code, 0, cap.stderr)
        item = self.read_state()["items"][0]
        self.assertEqual(item["status"], "proposed")
        self.assertIsNone(item["approvedAt"])
        self.assertIsNone(item["approvalHash"])

    def test_failed_transition_leaves_the_state_byte_identical(self):
        self.write_state(items=[helpers.make_item(1)])
        before = self.state_path.read_bytes()
        cap = run_state(self, "set", "--item", "1", "--status", "applied")
        self.assertEqual(cap.code, 1)
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_new_item_carries_v2_fields(self):
        self.write_state()
        cap = run_state(self, "set", "--item", "5", "--verdict", "ACCEPT")
        self.assertEqual(cap.code, 0, cap.stderr)
        item = self.read_state()["items"][0]
        self.assertEqual(item["status"], "proposed")
        self.assertEqual(item["posts"], [])
        self.assertIsNone(item["approvedAt"])
        self.assertIsNone(item["approvalHash"])
        self.assertFalse(item["orphaned"])
        self.assertEqual(item["missingThreadIds"], [])


class ApprovalTests(helpers.RepoCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.write_state(
            items=[
                helpers.make_item(1, verdict="ACCEPT"),
                helpers.make_item(2, verdict="CLARIFY", action="", replyDraft="Which behaviour?"),
                helpers.make_item(3, verdict="PUSH_BACK"),
                helpers.make_item(4, verdict="DEFER", action="", replyDraft="Out of scope."),
            ]
        )

    def test_approve_sets_status_timestamp_and_hash(self):
        cap = run_state(self, "approve", "1")
        self.assertEqual(cap.code, 0, cap.stderr)
        item = self.read_state()["items"][0]
        self.assertEqual(item["status"], "approved")
        self.assertIsNotNone(item["approvedAt"])
        self.assertTrue(item["approvedAt"].endswith("Z"))

        payload = {
            "verdict": "ACCEPT",
            "threadIds": ["gl:d1"],
            "action": "Add the guard.",
            "evidence": [{"path": "src/app.py", "line": 3, "note": "no guard"}],
        }
        expected = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
                "utf-8"
            )
        ).hexdigest()
        self.assertEqual(item["approvalHash"], expected)

    def test_approve_all_holds_clarify_and_defer(self):
        cap = run_state(self, "approve", "all")
        self.assertEqual(cap.code, 0, cap.stderr)
        items = {item["n"]: item for item in self.read_state()["items"]}
        self.assertEqual(items[1]["status"], "approved")
        self.assertEqual(items[2]["status"], "proposed")
        self.assertIsNone(items[2]["approvedAt"])
        self.assertEqual(items[4]["status"], "proposed")
        self.assertIn("Held back", cap.stdout)

    def test_approve_reports_unapproved_items(self):
        run_state(self, "approve", "all")
        cap = run_state(self, "approve", "1")
        self.assertEqual(cap.code, 0, cap.stderr)
        items = {item["n"]: item for item in self.read_state()["items"]}
        self.assertEqual(items[1]["status"], "approved")
        self.assertEqual(items[3]["status"], "proposed")
        self.assertIsNone(items[3]["approvalHash"])
        self.assertIn("No longer approved", cap.stdout)

    def test_approve_skip_marks_skipped(self):
        cap = run_state(self, "approve", "all, skip 2")
        self.assertEqual(cap.code, 0, cap.stderr)
        items = {item["n"]: item for item in self.read_state()["items"]}
        self.assertEqual(items[2]["status"], "skipped")

    def test_approve_override_changes_verdict_and_hash(self):
        cap = run_state(self, "approve", "2=ACCEPT")
        self.assertEqual(cap.code, 0, cap.stderr)
        item = self.read_state()["items"][1]
        self.assertEqual(item["verdict"], "ACCEPT")
        self.assertEqual(item["status"], "approved")
        self.assertIsNotNone(item["approvalHash"])
        self.assertIn("Overrides applied", cap.stdout)

    def test_approve_is_dry_run_safe(self):
        before = self.state_path.read_bytes()
        cap = run_state(self, "approve", "all", "--dry-run")
        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertIn("dry run", cap.stdout)

    def test_hash_ignores_non_material_fields(self):
        run_state(self, "approve", "1")
        first = self.read_state()["items"][0]["approvalHash"]

        cap = run_state(
            self, "set", "--item", "1", "--severity", "nit", "--claim", "Softer claim", "--reply", "Hi"
        )
        self.assertEqual(cap.code, 0, cap.stderr)
        item = self.read_state()["items"][0]
        self.assertEqual(item["status"], "approved")
        self.assertEqual(item["approvalHash"], first)

    def test_material_edits_invalidate_approval(self):
        mutations = {
            "verdict": ("--verdict", "PUSH_BACK"),
            "action": ("--action", "Do something else."),
            "threadIds": ("--threads", "gl:d2"),
            "evidence": ("--evidence", "src/app.py:4:different line"),
        }
        for field, (flag, value) in mutations.items():
            with self.subTest(field=field):
                self.write_state(items=[helpers.make_item(1)])
                run_state(self, "approve", "1")
                cap = run_state(self, "set", "--item", "1", flag, value)
                self.assertEqual(cap.code, 0, cap.stderr)
                state = self.read_state()
                item = state["items"][0]
                self.assertEqual(item["status"], "proposed", field)
                self.assertIsNone(item["approvedAt"], field)
                self.assertIsNone(item["approvalHash"], field)
                self.assertIn("approval-invalidated", [event["type"] for event in state["events"]])

    def test_material_edit_then_applied_is_refused(self):
        run_state(self, "approve", "1")
        cap = run_state(
            self, "set", "--item", "1", "--action", "A different fix.", "--status", "applied"
        )
        self.assertEqual(cap.code, 1)
        self.assertIn("approve", cap.stderr.lower())
        item = self.read_state()["items"][0]
        self.assertEqual(item["status"], "approved")
        self.assertIsNotNone(item["approvalHash"])

    def test_approved_item_cannot_change_verdict_without_reset(self):
        run_state(self, "approve", "1")
        run_state(self, "set", "--item", "1", "--verdict", "PUSH_BACK")
        item = self.read_state()["items"][0]
        self.assertNotEqual(item["status"], "approved")

    def test_material_edit_invalidates_applied_and_verified(self):
        for status in ("applied", "verified"):
            with self.subTest(status=status):
                self.write_state(items=[helpers.make_item(1)])
                run_state(self, "approve", "1")
                run_state(self, "set", "--item", "1", "--status", status)
                run_state(self, "set", "--item", "1", "--action", "Rewrite it.")
                state = self.read_state()
                item = state["items"][0]
                self.assertEqual(item["status"], "proposed")
                self.assertIsNone(item["approvalHash"])
                self.assertIn("approval-invalidated", [event["type"] for event in state["events"]])

    def test_approving_again_refreshes_the_hash(self):
        run_state(self, "approve", "1")
        first = self.read_state()["items"][0]["approvalHash"]
        run_state(self, "set", "--item", "1", "--action", "A better fix.")
        run_state(self, "approve", "1")
        item = self.read_state()["items"][0]
        self.assertEqual(item["status"], "approved")
        self.assertNotEqual(item["approvalHash"], first)


class ApprovalParserTests(unittest.TestCase):
    def setUp(self):
        self.items = [{"n": n, "verdict": "ACCEPT"} for n in range(1, 5)]

    def parse(self, expression):
        return state_cmd.parse_approval(expression, self.items)

    def test_all(self):
        self.assertEqual(self.parse("all"), ([1, 2, 3, 4], [], {}))

    def test_numbers(self):
        self.assertEqual(self.parse("1, 3")[0], [1, 3])

    def test_and_separator(self):
        self.assertEqual(self.parse("1 and 3")[0], [1, 3])

    def test_standalone_skip_means_all_except(self):
        self.assertEqual(self.parse("skip 2"), ([1, 3, 4], [2], {}))

    def test_colon_override(self):
        self.assertEqual(self.parse("3:alternative"), ([3], [], {3: "ALTERNATIVE"}))

    def test_equals_override_is_case_insensitive(self):
        self.assertEqual(self.parse("2=alternative"), ([2], [], {2: "ALTERNATIVE"}))

    def test_approve_prefix_is_tolerated(self):
        self.assertEqual(self.parse("approve 1 and 3")[0], [1, 3])

    def test_unknown_item_raises(self):
        with self.assertRaises(_common.ScriptError):
            self.parse("1, 9")

    def test_garbage_raises(self):
        with self.assertRaises(_common.ScriptError):
            self.parse("maybe the second one")


class PostGateTests(helpers.RepoCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.install(reply)
        self.install(state_cmd)

    def approved_state(self, **overrides):
        self.write_state(items=[helpers.make_item(1, **overrides)])
        run_state(self, "approve", "1")

    def test_force_flag_is_gone(self):
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                reply.build_parser().parse_args(["--item", "1", "--force"])
        self.assertNotIn("--force", reply.build_parser().format_help())

    def test_proposed_item_is_refused_even_with_body_and_threads(self):
        self.write_state(items=[helpers.make_item(1, status="proposed")])
        before = self.state_path.read_bytes()
        cap = run_post(self, "--item", "1", "--thread", "gl:d1", "--body", "Thanks", "--post")
        self.assertEqual(cap.code, 1)
        self.assertIn("approve", cap.stderr.lower())
        self.assertEqual(self.fake.glab_calls, [])
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_proposed_item_preview_is_refused_too(self):
        self.write_state(items=[helpers.make_item(1, status="proposed")])
        cap = run_post(self, "--item", "1", "--body", "Thanks")
        self.assertEqual(cap.code, 1)
        self.assertIn("approve", cap.stderr.lower())

    def test_approved_item_can_be_posted(self):
        self.write_state(
            items=[helpers.make_item(1, threadIds=["gl:d1", "gl:d2"])]
        )
        run_state(self, "approve", "1")
        self.fake.add_glab('{"url": "https://gitlab.example.com/note/1"}')
        cap = run_post(self, "--item", "1", "--body", "Thanks, fixed.", "--post")
        self.assertEqual(cap.code, 0, cap.stderr)

        item = self.read_state()["items"][0]
        self.assertEqual(item["status"], "posted")
        self.assertNotIn("postedAt", item)
        self.assertNotIn("postedReplies", item)
        self.assertEqual(len(item["posts"]), 2)
        post = item["posts"][0]
        self.assertEqual(post["threadId"], "gl:d1")
        self.assertEqual(post["body"], "Thanks, fixed.")
        self.assertEqual(post["source"], "override")
        self.assertIsNotNone(post["postedAt"])
        self.assertIsNone(post["resolvedAt"])
        self.assertEqual(post["url"], "https://gitlab.example.com/note/1")

    def test_applied_and_verified_items_are_postable(self):
        for status in ("applied", "verified"):
            with self.subTest(status=status):
                self.approved_state()
                run_state(self, "set", "--item", "1", "--status", status)
                self.fake.add_glab("{}")
                cap = run_post(self, "--item", "1", "--body", "Done", "--post")
                self.assertEqual(cap.code, 0, cap.stderr)

    def test_resolve_records_resolution_per_thread(self):
        self.approved_state()
        self.fake.add_glab("{}")
        self.fake.add_glab("{}")
        self.fake.add_glab("{}")
        self.fake.add_glab("{}")
        cap = run_post(self, "--item", "1", "--body", "Done", "--post", "--resolve")
        self.assertEqual(cap.code, 0, cap.stderr)
        item = self.read_state()["items"][0]
        self.assertEqual(item["status"], "resolved")
        self.assertTrue(all(post["resolvedAt"] for post in item["posts"]))

    def test_preview_makes_no_remote_call_and_changes_nothing(self):
        self.approved_state()
        before = self.state_path.read_bytes()
        cap = run_post(self, "--item", "1", "--body", "Done")
        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertIn("Preview only", cap.stdout)
        self.assertEqual(self.fake.glab_calls, [])
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_already_posted_item_is_refused(self):
        self.write_state(
            items=[
                helpers.make_item(
                    1,
                    status="posted",
                    posts=[{"threadId": "gl:d1", "postedAt": "2026-11-02T10:00:00Z"}],
                )
            ]
        )
        cap = run_post(self, "--item", "1", "--body", "Again", "--post")
        self.assertEqual(cap.code, 1)
        self.assertEqual(self.fake.glab_calls, [])

    def test_post_event_is_recorded(self):
        self.approved_state()
        self.fake.add_glab("{}")
        run_post(self, "--item", "1", "--body", "Done", "--post")
        state = self.read_state()
        self.assertEqual(state["events"][-1]["type"], "posted")

    def test_material_edit_blocks_posting_until_reapproved(self):
        self.approved_state()
        run_state(self, "set", "--item", "1", "--action", "A different fix.")
        refused = run_post(self, "--item", "1", "--body", "Done", "--post")
        self.assertEqual(refused.code, 1)
        self.assertIn("approve", refused.stderr.lower())
        self.assertEqual(self.fake.glab_calls, [])

        run_state(self, "approve", "1")
        self.fake.add_glab("{}")
        posted = run_post(self, "--item", "1", "--body", "Done", "--post")
        self.assertEqual(posted.code, 0, posted.stderr)


class HelperUnitTests(unittest.TestCase):
    def test_invalidate_approval_resets_executed_states(self):
        for status in ("approved", "applied", "verified"):
            with self.subTest(status=status):
                item = helpers.make_item(1, status=status, approvedAt="x", approvalHash="y")
                _common.invalidate_approval(item, "test")
                self.assertEqual(item["status"], "proposed")
                self.assertIsNone(item["approvedAt"])
                self.assertIsNone(item["approvalHash"])

    def test_invalidate_approval_keeps_terminal_states(self):
        for status in ("posted", "resolved", "skipped", "proposed"):
            with self.subTest(status=status):
                item = helpers.make_item(1, status=status, approvedAt="x", approvalHash="y")
                _common.invalidate_approval(item, "test")
                self.assertEqual(item["status"], status)
                self.assertIsNone(item["approvalHash"])

    def test_refresh_item_status_waits_for_every_thread(self):
        item = helpers.make_item(
            1,
            threadIds=["gl:a", "gl:b"],
            status="approved",
            posts=[{"threadId": "gl:a", "postedAt": "x", "resolvedAt": None}],
        )
        self.assertEqual(_common.refresh_item_status(item), "approved")

    def test_refresh_item_status_posted(self):
        item = helpers.make_item(
            1,
            threadIds=["gl:a", "gl:b"],
            status="approved",
            posts=[
                {"threadId": "gl:a", "postedAt": "x", "resolvedAt": None},
                {"threadId": "gl:b", "postedAt": "x", "resolvedAt": None},
            ],
        )
        self.assertEqual(_common.refresh_item_status(item), "posted")

    def test_refresh_item_status_resolved(self):
        item = helpers.make_item(
            1,
            threadIds=["gl:a", "gl:b"],
            status="posted",
            posts=[
                {"threadId": "gl:a", "postedAt": "x", "resolvedAt": "y"},
                {"threadId": "gl:b", "postedAt": "x", "resolvedAt": "y"},
            ],
        )
        self.assertEqual(_common.refresh_item_status(item), "resolved")


class FetchStateTests(helpers.RepoCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.install(fetch)

    def fetch_ok(self, discussions="[]"):
        self.fake.add_glab(
            json.dumps(
                {
                    "title": "Test MR",
                    "web_url": "https://gitlab.example.com/group/api/-/merge_requests/123",
                    "diff_refs": {"head_sha": helpers.HEAD_SHA, "base_sha": helpers.BASE_SHA},
                }
            )
        )
        self.fake.add_glab('{"username": "me"}')
        self.fake.add_glab(discussions)
        cap = helpers.capture()
        cap.run(
            fetch.main,
            [
                "--host",
                helpers.HOST,
                "--repo",
                helpers.REPO,
                "--number",
                str(helpers.NUMBER),
            ],
        )
        return cap

    def test_fetch_writes_a_v2_gitlab_state(self):
        cap = self.fetch_ok()
        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertTrue(self.state_path.exists())
        state = self.read_state()
        self.assertEqual(state["schemaVersion"], 2)
        self.assertNotIn("provider", state)
        self.assertEqual(state["target"]["number"], helpers.NUMBER)
        self.assertEqual(state["threads"], [])

    def test_fetch_backfills_item_defaults_on_refetch(self):
        self.write_state(
            items=[
                {
                    "n": 1,
                    "threadIds": ["gl:d1"],
                    "verdict": "ACCEPT",
                    "severity": "blocking",
                    "claim": "c",
                    "evidence": [],
                    "action": "a",
                    "replyDraft": "",
                }
            ]
        )
        # The item's thread must still exist or the refetch rightly orphans it.
        self.fetch_ok(
            json.dumps(
                [
                    {
                        "id": "d1",
                        "notes": [
                            {
                                "system": False,
                                "resolvable": True,
                                "resolved": False,
                                "body": "Comment.",
                                "author": {"username": "sara"},
                                "position": None,
                            }
                        ],
                    }
                ]
            )
        )
        item = self.read_state()["items"][0]
        self.assertEqual(item["posts"], [])
        self.assertIsNone(item["approvedAt"])
        self.assertIsNone(item["approvalHash"])
        self.assertFalse(item["orphaned"])
        self.assertEqual(item["missingThreadIds"], [])

    def test_refetch_rejects_a_v1_state(self):
        self.state_path.write_text(
            json.dumps({"schemaVersion": 1, "items": []}), encoding="utf-8"
        )
        cap = self.fetch_ok()
        self.assertEqual(cap.code, 1)
        self.assertIn("schema", cap.stderr.lower())
        self.assertEqual(
            json.loads(self.state_path.read_text(encoding="utf-8"))["schemaVersion"], 1
        )


if __name__ == "__main__":
    unittest.main()
