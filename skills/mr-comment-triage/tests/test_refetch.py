#!/usr/bin/env python3
"""Re-fetch reconciliation: history survives, vanished threads are caught.

Every test drives the real CLI entry points with the subprocess boundary faked
and a real state file on disk, so a re-fetch is observed exactly the way the
next session would see it. No network, no credentials.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import helpers  # noqa: E402
import _common  # noqa: E402
import fetch_threads as fetch  # noqa: E402
import post_reply as reply  # noqa: E402
import triage_state as state_cmd  # noqa: E402

MR_PAYLOAD = {
    "iid": helpers.NUMBER,
    "title": "Test MR",
    "web_url": f"https://{helpers.HOST}/{helpers.REPO}/-/merge_requests/{helpers.NUMBER}",
    "sha": helpers.HEAD_SHA,
    "diff_refs": {"head_sha": helpers.HEAD_SHA, "base_sha": helpers.BASE_SHA},
}


def discussion(remote_id: str, *, resolved: bool = False, line: int = 3) -> dict:
    """One GitLab discussion carrying a single resolvable review note."""
    return {
        "id": remote_id,
        "notes": [
            {
                "id": sum(ord(char) for char in remote_id),
                "system": False,
                "resolvable": True,
                "resolved": resolved,
                "body": f"Comment on {remote_id}.",
                "created_at": "2026-11-01T10:00:00Z",
                "author": {"username": "sara"},
                "position": {
                    "new_path": helpers.SOURCE_PATH,
                    "new_line": line,
                    "old_path": helpers.SOURCE_PATH,
                    "old_line": None,
                    "head_sha": helpers.HEAD_SHA,
                    "line_range": None,
                },
            }
        ],
    }


def approved_item(number: int, **overrides) -> dict:
    """An item whose approval is real, so invalidation is observable."""
    item = helpers.make_item(number, **overrides)
    item["status"] = "approved"
    item["approvedAt"] = "2026-11-02T10:00:00Z"
    item["approvalHash"] = _common.approval_hash(item)
    return item


class RefetchTests(helpers.RepoCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.install(fetch)
        self.install(state_cmd)
        self.install(reply)

    # -- harness ---------------------------------------------------------

    def queue_fetch(self, discussions: list[dict]) -> None:
        self.fake.add_glab(json.dumps(MR_PAYLOAD))
        self.fake.add_glab(json.dumps({"username": "me"}))
        self.fake.add_glab(json.dumps(discussions))

    def fetch_once(self, discussions: list[dict], *argv: str):
        self.queue_fetch(discussions)
        cap = helpers.capture()
        cap.run(
            fetch.main,
            [
                "--host", helpers.HOST,
                "--repo", helpers.REPO,
                "--number", str(helpers.NUMBER),
                *argv,
            ],
        )
        self.assertEqual(cap.code, 0, cap.stderr)
        return cap

    def run_state(self, *argv):
        cap = helpers.capture()
        cap.run(state_cmd.main, ["--state", str(self.state_path), *argv])
        return cap

    def run_post(self, *argv):
        cap = helpers.capture()
        cap.run(reply.main, ["--state", str(self.state_path), *argv])
        return cap

    def plan(self, items: list[dict]) -> None:
        plan_file = self.tmp_path / "plan.json"
        plan_file.write_text(json.dumps({"items": items}), encoding="utf-8")
        cap = self.run_state("plan", "--from", str(plan_file))
        self.assertEqual(cap.code, 0, cap.stderr)

    def seed(self, **overrides) -> None:
        state = self.read_state()
        state.update(overrides)
        _common.save_state(self.state_path, state)

    def events(self, kind: str) -> list[dict]:
        return [event for event in self.read_state()["events"] if event["type"] == kind]

    def thread_ids(self) -> list[str]:
        return [thread["id"] for thread in self.read_state()["threads"]]

    # -- history ---------------------------------------------------------

    def test_refetch_preserves_prior_events_and_appends_fetched_and_refetched(self):
        self.fetch_once([discussion("d1"), discussion("d2")])
        self.plan(
            [
                {
                    "n": 1,
                    "threadIds": ["gl:d1"],
                    "verdict": "ACCEPT",
                    "severity": "blocking",
                    "claim": "Guard is missing.",
                    "evidence": [f"{helpers.SOURCE_PATH}:3"],
                    "action": "Add the guard.",
                    "replyDraft": "Added.",
                }
            ]
        )
        self.assertEqual(self.run_state("approve", "1").code, 0)
        prior = self.read_state()["events"]
        self.assertEqual([event["type"] for event in prior], ["fetched", "planned", "approved"])

        self.fetch_once([discussion("d1"), discussion("d2")])

        events = self.read_state()["events"]
        self.assertEqual(events[:3], prior, "every prior event survives byte-for-byte")
        self.assertEqual(
            [event["type"] for event in events[3:]], ["fetched", "refetched"]
        )
        self.assertEqual(
            len(self.events("fetched")), 2, "one fetched event per fetch, never replayed"
        )

    def test_refetch_keeps_items_verdicts_statuses_approval_and_posts(self):
        self.fetch_once([discussion("d1"), discussion("d2")])
        item = approved_item(1, threadIds=["gl:d1", "gl:d2"])
        item["posts"] = [
            {
                "threadId": "gl:d1",
                "postedAt": "2026-11-02T11:00:00Z",
                "resolvedAt": None,
                "body": "Added the guard.",
                "url": "https://gitlab.example.com/note/7",
                "source": "draft",
            }
        ]
        self.seed(items=[item])
        before = self.read_state()["items"][0]

        self.fetch_once([discussion("d1"), discussion("d2")])

        self.assertEqual(self.read_state()["items"], [before])

    # -- orphan reconciliation -------------------------------------------

    def test_orphaned_item_is_invalidated_and_warned(self):
        self.fetch_once([discussion("d1"), discussion("d2")])
        self.seed(items=[approved_item(1, threadIds=["gl:d1"]), approved_item(2, threadIds=["gl:d2"])])

        cap = self.fetch_once([discussion("d1")])

        state = self.read_state()
        kept, gone = state["items"]
        self.assertFalse(kept["orphaned"])
        self.assertEqual(kept["status"], "approved")
        self.assertIsNotNone(kept["approvalHash"])

        self.assertTrue(gone["orphaned"])
        self.assertEqual(gone["missingThreadIds"], ["gl:d2"])
        self.assertEqual(gone["status"], "proposed")
        self.assertIsNone(gone["approvedAt"])
        self.assertIsNone(gone["approvalHash"])

        orphaned = self.events("orphaned")
        self.assertEqual(len(orphaned), 1)
        self.assertIn("#2", orphaned[0]["detail"])
        self.assertIn("gl:d2", orphaned[0]["detail"])
        self.assertTrue(
            any("gl:d2" in warning for warning in state["warnings"]),
            state["warnings"],
        )
        self.assertIn("gl:d2", cap.stdout, "the collector prints the orphan warning")
        self.assertEqual(self.thread_ids(), ["gl:d1"], "the fresh thread list wins")

    def test_posted_item_is_marked_orphaned_without_losing_its_status(self):
        self.fetch_once([discussion("d1"), discussion("d2")])
        posted = approved_item(1, threadIds=["gl:d2"])
        posted["status"] = "posted"
        posted["posts"] = [
            {
                "threadId": "gl:d2",
                "postedAt": "2026-11-02T11:00:00Z",
                "resolvedAt": None,
                "body": "Done.",
                "url": "https://gitlab.example.com/note/8",
                "source": "draft",
            }
        ]
        self.seed(items=[posted])

        self.fetch_once([discussion("d1")])

        item = self.read_state()["items"][0]
        self.assertTrue(item["orphaned"])
        self.assertEqual(item["missingThreadIds"], ["gl:d2"])
        self.assertEqual(item["status"], "posted", "a finished item is never rolled back")
        self.assertEqual(len(item["posts"]), 1)

    def test_orphan_flag_clears_when_the_thread_comes_back(self):
        self.fetch_once([discussion("d1"), discussion("d2")])
        self.seed(
            items=[
                helpers.make_item(
                    1,
                    threadIds=["gl:d2"],
                    orphaned=True,
                    missingThreadIds=["gl:d2"],
                )
            ]
        )

        self.fetch_once([discussion("d1"), discussion("d2")])

        item = self.read_state()["items"][0]
        self.assertFalse(item["orphaned"])
        self.assertEqual(item["missingThreadIds"], [])

    def test_render_and_show_display_the_orphan_warning(self):
        self.write_state(
            threads=[helpers.make_thread("gl:d1")],
            items=[
                helpers.make_item(
                    1,
                    threadIds=["gl:d1", "gl:gone"],
                    orphaned=True,
                    missingThreadIds=["gl:gone"],
                )
            ],
        )

        for command in ("render", "show"):
            with self.subTest(command=command):
                cap = self.run_state(command)
                self.assertEqual(cap.code, 0, cap.stderr)
                self.assertIn("orphaned", cap.stdout.lower())
                self.assertIn("gl:gone", cap.stdout)

    def test_posting_an_orphaned_item_is_refused(self):
        self.write_state(
            items=[
                approved_item(
                    1,
                    orphaned=True,
                    missingThreadIds=["gl:gone"],
                )
            ]
        )

        cap = self.run_post("--item", "1", "--post")

        self.assertEqual(cap.code, 1)
        self.assertIn("orphaned", cap.stderr.lower())
        self.assertIn("gl:gone", cap.stderr)
        self.assertEqual(self.fake.glab_calls, [], "refused before any network call")

    # -- fresh threads ---------------------------------------------------

    def test_new_threads_are_available_for_planning(self):
        self.fetch_once([discussion("d1")])
        self.plan(
            [
                {
                    "n": 1,
                    "threadIds": ["gl:d1"],
                    "verdict": "PUSH_BACK",
                    "evidence": [],
                    "replyDraft": "Not a defect.",
                }
            ]
        )

        self.fetch_once([discussion("d1"), discussion("d3")])

        self.assertEqual(self.thread_ids(), ["gl:d1", "gl:d3"])
        self.plan(
            [
                {
                    "n": 1,
                    "threadIds": ["gl:d1"],
                    "verdict": "PUSH_BACK",
                    "evidence": [],
                    "replyDraft": "Not a defect.",
                },
                {
                    "n": 2,
                    "threadIds": ["gl:d3"],
                    "verdict": "PUSH_BACK",
                    "evidence": [],
                    "replyDraft": "Already handled elsewhere.",
                },
            ]
        )
        items = self.read_state()["items"]
        self.assertEqual([item["threadIds"] for item in items], [["gl:d1"], ["gl:d3"]])

    # -- include-resolved ------------------------------------------------

    def test_include_resolved_reports_both_counts_accurately(self):
        cap = self.fetch_once(
            [discussion("d1"), discussion("d2", resolved=True)], "--include-resolved"
        )

        self.assertIn("1 unresolved", cap.stdout)
        self.assertIn("1 resolved kept", cap.stdout)
        self.assertEqual(self.thread_ids(), ["gl:d1", "gl:d2"], "resolved threads are kept")

    def test_default_fetch_reports_only_unresolved_threads(self):
        cap = self.fetch_once([discussion("d1"), discussion("d2", resolved=True)])

        self.assertIn("1 unresolved", cap.stdout)
        self.assertNotIn("resolved kept", cap.stdout)
        self.assertNotIn("of 2", cap.stdout)
        self.assertEqual(self.thread_ids(), ["gl:d1"])

    # -- reset and schema guard ------------------------------------------

    def test_reset_discards_items_and_starts_a_clean_log(self):
        self.fetch_once([discussion("d1")])
        self.plan(
            [
                {
                    "n": 1,
                    "threadIds": ["gl:d1"],
                    "verdict": "PUSH_BACK",
                    "evidence": [],
                    "replyDraft": "Not a defect.",
                }
            ]
        )

        self.fetch_once([discussion("d1")], "--reset")

        state = self.read_state()
        self.assertEqual(state["items"], [])
        self.assertEqual([event["type"] for event in state["events"]], ["fetched"])
        self.assertEqual(state["warnings"], [])

    def test_schema_v1_state_fails_cleanly_without_migration(self):
        _common.save_state(
            self.state_path, {"schemaVersion": 1, "items": [], "events": []}
        )
        before = self.state_path.read_bytes()
        self.queue_fetch([discussion("d1")])

        cap = helpers.capture().run(
            fetch.main,
            [
                "--host", helpers.HOST,
                "--repo", helpers.REPO,
                "--number", str(helpers.NUMBER),
            ],
        )

        self.assertEqual(cap[0], 1)
        self.assertIn("schema version", cap[2])
        self.assertEqual(self.state_path.read_bytes(), before, "the old state is untouched")


if __name__ == "__main__":
    unittest.main()
