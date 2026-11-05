#!/usr/bin/env python3
"""Write-phase guards: clean-tree preflight and the resolve-author guard.

Every test drives a real CLI entry point against a throwaway git repository and
a real state file, with the subprocess boundary faked. No network, no
credentials, and no write ever reaches the example merge request.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import helpers  # noqa: E402
import _common  # noqa: E402
import post_reply as reply  # noqa: E402
import triage_state as state_cmd  # noqa: E402

ME = "me"


def self_thread(thread_id: str = "gl:d1", **overrides) -> dict:
    return helpers.make_thread(thread_id, author=ME, authorKind="self", **overrides)


class WritePhaseGuardTests(helpers.RepoCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.install(state_cmd)
        self.install(reply)

    # -- helpers ---------------------------------------------------------

    def run_state(self, *argv):
        cap = helpers.capture()
        cap.run(state_cmd.main, ["--state", str(self.state_path), *argv])
        return cap

    def run_post(self, *argv):
        cap = helpers.capture()
        cap.run(reply.main, ["--state", str(self.state_path), *argv])
        return cap

    def item(self, number: int = 1) -> dict:
        for entry in self.read_state()["items"]:
            if entry["n"] == number:
                return entry
        raise AssertionError(f"item #{number} missing")

    def approve(self, number: int = 1) -> None:
        cap = self.run_state("approve", str(number))
        self.assertEqual(cap.code, 0, cap.stderr)

    # -- preflight -------------------------------------------------------

    def test_clean_preflight_records_the_check(self):
        self.write_state(self.base_state())
        before = self.read_state()
        self.assertEqual(before["events"], [])

        cap = self.run_state("preflight")

        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertIn("preflight", cap.stdout.lower())
        events = self.read_state()["events"]
        self.assertEqual([event["type"] for event in events], ["preflight-clean"])

    def test_dirty_preflight_lists_the_paths_and_writes_nothing(self):
        self.write_state(self.base_state())
        before = self.state_path.read_bytes()
        (self.root / helpers.SOURCE_PATH).write_text("changed = 1\n", encoding="utf-8")
        (self.root / "notes.txt").write_text("local note\n", encoding="utf-8")

        cap = self.run_state("preflight")

        self.assertEqual(cap.code, 1)
        self.assertIn(helpers.SOURCE_PATH, cap.stderr)
        self.assertIn("notes.txt", cap.stderr)
        self.assertEqual(self.state_path.read_bytes(), before, "a refusal applies nothing")
        self.assertEqual(self.fake.glab_calls, [])

    def test_dirty_preflight_caps_a_long_path_list(self):
        self.write_state(self.base_state())
        for number in range(1, 26):
            (self.root / f"f{number:02d}.txt").write_text("x\n", encoding="utf-8")

        cap = self.run_state("preflight")

        self.assertEqual(cap.code, 1)
        self.assertIn("and 5 more", cap.stderr)
        self.assertNotIn("f25.txt", cap.stderr)

    def test_preflight_uses_the_shared_resolver_for_an_ignored_state_dir(self):
        os.environ.pop("MR_TRIAGE_DIR", None)
        directory = self.root / ".tmp" / _common.STATE_DIRNAME
        directory.mkdir(parents=True)
        path = _common.state_path(directory, helpers.REPO, helpers.NUMBER)
        _common.save_state(path, self.base_state())

        cap = helpers.capture()
        cap.run(state_cmd.main, ["preflight"])

        self.assertEqual(cap.code, 0, cap.stderr)
        events = _common.load_state(path)["events"]
        self.assertEqual([event["type"] for event in events], ["preflight-clean"])
        self.assertEqual(helpers.git(self.root, "status", "--porcelain").stdout, "")

    # -- resolve guard ---------------------------------------------------

    def test_resolve_closes_self_authored_threads(self):
        threads = [self_thread("gl:d1"), self_thread("gl:d2")]
        self.write_state(
            self.base_state(
                threads=threads,
                items=[helpers.make_item(1, threadIds=["gl:d1", "gl:d2"])],
            )
        )
        self.approve()
        for _ in range(4):
            self.fake.add_glab("{}")

        cap = self.run_post("--item", "1", "--post", "--resolve")

        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual(len(self.fake.glab_calls), 4, "reply then resolve per thread")
        item = self.item()
        self.assertEqual(item["status"], "resolved")
        self.assertTrue(all(post["resolvedAt"] for post in item["posts"]))
        event_types = [event["type"] for event in self.read_state()["events"]]
        self.assertNotIn("resolve-override", event_types)

    def test_non_self_resolve_is_refused_before_any_call(self):
        threads = [
            self_thread("gl:d1"),
            helpers.make_thread("gl:d2", author="sara", authorKind="human"),
        ]
        self.write_state(
            self.base_state(
                threads=threads,
                items=[helpers.make_item(1, threadIds=["gl:d1", "gl:d2"])],
            )
        )
        self.approve()
        before = self.state_path.read_bytes()

        cap = self.run_post("--item", "1", "--post", "--resolve")

        self.assertEqual(cap.code, 1)
        self.assertIn("gl:d2", cap.stderr)
        self.assertIn("sara", cap.stderr)
        self.assertIn("--resolve-other", cap.stderr)
        self.assertEqual(self.fake.glab_calls, [], "no reply is published either")
        self.assertEqual(self.state_path.read_bytes(), before, "the state is untouched")

    def test_resolve_other_records_one_audit_event_per_non_self_thread(self):
        threads = [
            self_thread("gl:d1"),
            helpers.make_thread("gl:d2", author="sara", authorKind="human"),
            helpers.make_thread("gl:d3", author="review-bot", authorKind="bot"),
        ]
        self.write_state(
            self.base_state(
                threads=threads,
                items=[helpers.make_item(1, threadIds=["gl:d1", "gl:d2", "gl:d3"])],
            )
        )
        self.approve()
        for _ in range(6):
            self.fake.add_glab("{}")

        cap = self.run_post("--item", "1", "--post", "--resolve", "--resolve-other")

        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual(len(self.fake.glab_calls), 6, "reply and resolve for three threads")
        self.assertEqual(self.item()["status"], "resolved")
        audit = [
            event
            for event in self.read_state()["events"]
            if event["type"] == "resolve-override"
        ]
        self.assertEqual(len(audit), 2)
        self.assertIn("gl:d2", audit[0]["detail"])
        self.assertIn("sara", audit[0]["detail"])
        self.assertIn("gl:d3", audit[1]["detail"])
        self.assertIn("review-bot", audit[1]["detail"])

    def test_resolve_other_without_resolve_is_refused(self):
        self.write_state(
            self.base_state(items=[helpers.make_item(1, threadIds=["gl:d1"])])
        )
        self.approve()
        before = self.state_path.read_bytes()

        cap = self.run_post("--item", "1", "--post", "--resolve-other")

        self.assertEqual(cap.code, 1)
        self.assertIn("--resolve", cap.stderr)
        self.assertEqual(self.fake.glab_calls, [])
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_resolve_other_without_resolve_is_refused_on_a_preview_too(self):
        self.write_state(
            self.base_state(items=[helpers.make_item(1, threadIds=["gl:d1"])])
        )

        cap = self.run_post("--item", "1", "--resolve-other")

        self.assertEqual(cap.code, 1)
        self.assertIn("--resolve", cap.stderr)

    # -- batch path uses the same guard ----------------------------------

    def test_batch_resolve_refuses_non_self_threads_before_posting(self):
        threads = [
            self_thread("gl:d1"),
            helpers.make_thread("gl:d2", author="omar", authorKind="human"),
        ]
        items = [
            helpers.make_item(
                1, threadIds=["gl:d1"], verdict="PUSH_BACK", replyDraft="First."
            ),
            helpers.make_item(
                2, threadIds=["gl:d2"], verdict="PUSH_BACK", replyDraft="Second."
            ),
        ]
        self.write_state(self.base_state(threads=threads, items=items))
        before = self.state_path.read_bytes()

        cap = self.run_post("--all-approved", "--post", "--resolve")

        self.assertEqual(cap.code, 1)
        self.assertIn("gl:d2", cap.stderr)
        self.assertIn("omar", cap.stderr)
        self.assertEqual(self.fake.glab_calls, [])
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_batch_resolve_other_audits_every_non_self_thread(self):
        threads = [
            self_thread("gl:d1"),
            helpers.make_thread("gl:d2", author="omar", authorKind="human"),
        ]
        items = [
            helpers.make_item(
                1, threadIds=["gl:d1"], verdict="PUSH_BACK", replyDraft="First."
            ),
            helpers.make_item(
                2, threadIds=["gl:d2"], verdict="PUSH_BACK", replyDraft="Second."
            ),
        ]
        self.write_state(self.base_state(threads=threads, items=items))
        for _ in range(4):
            self.fake.add_glab("{}")

        cap = self.run_post("--all-approved", "--post", "--resolve", "--resolve-other")

        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual(len(self.fake.glab_calls), 4)
        self.assertEqual(self.item(1)["status"], "resolved")
        self.assertEqual(self.item(2)["status"], "resolved")
        audit = [
            event
            for event in self.read_state()["events"]
            if event["type"] == "resolve-override"
        ]
        self.assertEqual(len(audit), 1)
        self.assertIn("gl:d2", audit[0]["detail"])
        self.assertIn("omar", audit[0]["detail"])


if __name__ == "__main__":
    unittest.main()
