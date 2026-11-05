#!/usr/bin/env python3
"""Gate 2 batch reply tests: one preview, one --post, resumable journal.

Every test drives ``post_reply.main`` once with the subprocess boundary faked,
so the invocation count is part of the assertion: a ten-item batch must not
turn into ten CLI calls.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import helpers  # noqa: E402
import post_reply as reply  # noqa: E402
import triage_state as state_cmd  # noqa: E402

DRAFT_ONE = "First reply body."
DRAFT_TWO = "Second reply body."


class BatchTests(helpers.RepoCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.install(reply)
        self.install(state_cmd)

    # -- helpers ---------------------------------------------------------

    def run_post(self, *argv):
        cap = helpers.capture()
        cap.run(reply.main, ["--state", str(self.state_path), *argv])
        return cap

    def run_state(self, *argv):
        cap = helpers.capture()
        cap.run(state_cmd.main, ["--state", str(self.state_path), *argv])
        return cap

    def approve_all(self):
        cap = self.run_state("approve", "all")
        self.assertEqual(cap.code, 0, cap.stderr)
        return cap

    def item(self, number: int) -> dict:
        for entry in self.read_state()["items"]:
            if entry["n"] == number:
                return entry
        raise AssertionError(f"item #{number} missing")

    # -- batch preview ---------------------------------------------------

    def test_all_approved_previews_every_item_and_thread_in_one_output(self):
        threads = [
            helpers.make_thread("gl:d1"),
            helpers.make_thread("gl:d2", author="omar", anchor={
                "kind": "inline",
                "path": helpers.SOURCE_PATH,
                "oldPath": None,
                "line": 7,
                "endLine": None,
                "side": "new",
            }),
        ]
        items = [
            helpers.make_item(1, threadIds=["gl:d1"], replyDraft=DRAFT_ONE),
            helpers.make_item(
                2,
                threadIds=["gl:d2"],
                verdict="PUSH_BACK",
                replyDraft=DRAFT_TWO,
            ),
        ]
        self.write_state(self.base_state(threads=threads, items=items))
        self.approve_all()
        before = self.state_path.read_bytes()

        cap = self.run_post("--all-approved", "--resolve")

        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertIn("#1", cap.stdout)
        self.assertIn("ACCEPT", cap.stdout)
        self.assertIn("#2", cap.stdout)
        self.assertIn("PUSH_BACK", cap.stdout)
        self.assertIn("gl:d1", cap.stdout)
        self.assertIn("gl:d2", cap.stdout)
        self.assertIn("@sara", cap.stdout)
        self.assertIn("@omar", cap.stdout)
        self.assertIn("src/app.py:3 (new)", cap.stdout)
        self.assertIn("src/app.py:7 (new)", cap.stdout)
        self.assertIn(DRAFT_ONE, cap.stdout)
        self.assertIn(DRAFT_TWO, cap.stdout)
        self.assertIn("resolve  yes", cap.stdout)
        self.assertIn("Preview only", cap.stdout)
        self.assertEqual(self.fake.glab_calls, [], "preview never posts")
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_item_and_all_approved_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            reply.build_parser().parse_args(
                ["--item", "1", "--all-approved", "--post"]
            )

    def test_thread_cannot_be_combined_with_all_approved(self):
        self.write_state(
            self.base_state(
                items=[helpers.make_item(1, verdict="PUSH_BACK", status="proposed")]
            )
        )
        cap = self.run_post("--all-approved", "--thread", "gl:d1", "--post")
        self.assertEqual(cap.code, 1)
        self.assertIn("--thread requires --item", cap.stderr)
        self.assertEqual(self.fake.glab_calls, [])

    # -- batch posting ---------------------------------------------------

    def test_all_approved_posts_every_thread_and_journals_each_item(self):
        threads = [helpers.make_thread("gl:d1"), helpers.make_thread("gl:d2")]
        items = [
            helpers.make_item(1, threadIds=["gl:d1"], replyDraft=DRAFT_ONE),
            helpers.make_item(2, threadIds=["gl:d2"], replyDraft=DRAFT_TWO),
        ]
        self.write_state(self.base_state(threads=threads, items=items))
        self.approve_all()
        self.fake.add_glab(json.dumps({"url": "https://gitlab.example.com/note/1"}))
        self.fake.add_glab(json.dumps({"url": "https://gitlab.example.com/note/2"}))

        cap = self.run_post("--all-approved", "--post")

        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual(len(self.fake.glab_calls), 2, "one reply per thread")
        self.assertIn("discussions/d1", " ".join(self.fake.glab_calls[0]))
        self.assertIn("discussions/d2", " ".join(self.fake.glab_calls[1]))
        self.assertIn("body=" + DRAFT_ONE, " ".join(self.fake.glab_calls[0]))
        self.assertIn("body=" + DRAFT_TWO, " ".join(self.fake.glab_calls[1]))
        self.assertEqual(self.item(1)["posts"][0]["body"], DRAFT_ONE)
        self.assertEqual(self.item(2)["posts"][0]["body"], DRAFT_TWO)
        self.assertEqual(self.item(1)["status"], "posted")
        self.assertEqual(self.item(2)["status"], "posted")
        self.assertEqual(
            len([event for event in self.read_state()["events"] if event["type"] == "posted"]),
            2,
        )

    def test_mixed_batch_posts_approved_and_reply_only_proposed_items(self):
        threads = [helpers.make_thread("gl:d1"), helpers.make_thread("gl:d2")]
        items = [
            helpers.make_item(1, threadIds=["gl:d1"], replyDraft=DRAFT_ONE),
            helpers.make_item(
                2, threadIds=["gl:d2"], verdict="PUSH_BACK", replyDraft=DRAFT_TWO
            ),
        ]
        self.write_state(self.base_state(threads=threads, items=items))
        cap = self.run_state("approve", "1")
        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual(self.item(1)["status"], "approved")
        self.assertEqual(self.item(2)["status"], "proposed")
        self.fake.add_glab("{}")
        self.fake.add_glab("{}")

        posted = self.run_post("--all-approved", "--post")

        self.assertEqual(posted.code, 0, posted.stderr)
        self.assertEqual(len(self.fake.glab_calls), 2)
        self.assertEqual(self.item(1)["status"], "posted")
        self.assertEqual(self.item(2)["status"], "posted")

    def test_ten_item_batch_is_one_main_call_and_one_glab_call_per_thread(self):
        threads = [helpers.make_thread(f"gl:d{n}") for n in range(1, 11)]
        items = [
            helpers.make_item(
                n,
                threadIds=[f"gl:d{n}"],
                verdict="PUSH_BACK",
                replyDraft=f"Reply number {n}.",
            )
            for n in range(1, 11)
        ]
        self.write_state(self.base_state(threads=threads, items=items))
        for _ in range(10):
            self.fake.add_glab("{}")

        calls = []
        real_main = reply.main

        def counting_main(argv=None):
            calls.append(list(argv or []))
            return real_main(argv)

        reply.main = counting_main
        try:
            cap = helpers.capture()
            cap.run(reply.main, ["--state", str(self.state_path), "--all-approved", "--post"])
        finally:
            reply.main = real_main

        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual(len(calls), 1, "the whole batch is one CLI invocation")
        self.assertEqual(len(self.fake.glab_calls), 10, "one glab call per thread")
        for n in range(1, 11):
            item = self.item(n)
            self.assertEqual(item["posts"][0]["body"], f"Reply number {n}.")
            self.assertEqual(item["status"], "posted")

    def test_batch_resolve_reports_and_records_each_resolution(self):
        threads = [helpers.make_thread("gl:d1"), helpers.make_thread("gl:d2")]
        items = [
            helpers.make_item(1, threadIds=["gl:d1"], verdict="PUSH_BACK", replyDraft=DRAFT_ONE),
            helpers.make_item(2, threadIds=["gl:d2"], verdict="ALREADY_FIXED", replyDraft=DRAFT_TWO),
        ]
        self.write_state(self.base_state(threads=threads, items=items))
        for _ in range(4):
            self.fake.add_glab("{}")

        cap = self.run_post("--all-approved", "--resolve", "--post")

        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual(len(self.fake.glab_calls), 4, "reply then resolve per thread")
        self.assertTrue(all(post["resolvedAt"] for post in self.item(1)["posts"]))
        self.assertTrue(all(post["resolvedAt"] for post in self.item(2)["posts"]))
        self.assertEqual(self.item(1)["status"], "resolved")
        self.assertEqual(self.item(2)["status"], "resolved")

    # -- partial failure and resume --------------------------------------

    def test_partial_batch_failure_reports_ids_and_stays_resumable(self):
        threads = [helpers.make_thread(f"gl:d{n}") for n in (1, 2, 3)]
        items = [
            helpers.make_item(n, threadIds=[f"gl:d{n}"], replyDraft=f"Reply {n}.")
            for n in (1, 2, 3)
        ]
        self.write_state(self.base_state(threads=threads, items=items))
        self.approve_all()
        self.fake.add_glab("{}")
        self.fake.fail_glab("glab: 500 server error")

        cap = self.run_post("--all-approved", "--post")

        self.assertEqual(cap.code, 1)
        self.assertEqual([post["threadId"] for post in self.item(1)["posts"]], ["gl:d1"])
        self.assertEqual(self.item(2)["posts"], [])
        self.assertEqual(self.item(3)["posts"], [])
        self.assertEqual(self.item(1)["status"], "posted")
        self.assertEqual(self.item(2)["status"], "approved")
        output = cap.stdout + cap.stderr
        self.assertIn("Succeeded:", output)
        self.assertIn("gl:d1", output)
        self.assertIn("Failed:", output)
        self.assertIn("gl:d2", output)
        self.assertIn("Not attempted: gl:d3", output)

        calls_before = len(self.fake.glab_calls)
        self.fake.add_glab("{}")
        self.fake.add_glab("{}")
        resumed = self.run_post("--all-approved", "--post")

        self.assertEqual(resumed.code, 0, resumed.stderr)
        resumed_calls = self.fake.glab_calls[calls_before:]
        self.assertEqual(len(resumed_calls), 2, "the posted thread is never repeated")
        self.assertIn("discussions/d2", " ".join(resumed_calls[0]))
        self.assertIn("discussions/d3", " ".join(resumed_calls[1]))
        for n in (1, 2, 3):
            self.assertEqual(self.item(n)["status"], "posted")

    def test_partial_reply_only_batch_resumes_without_reapproval(self):
        threads = [helpers.make_thread("gl:d1"), helpers.make_thread("gl:d2")]
        items = [
            helpers.make_item(1, threadIds=["gl:d1"], verdict="PUSH_BACK", replyDraft=DRAFT_ONE),
            helpers.make_item(2, threadIds=["gl:d2"], verdict="CLARIFY", replyDraft=DRAFT_TWO),
        ]
        self.write_state(self.base_state(threads=threads, items=items))
        self.fake.add_glab("{}")
        self.fake.fail_glab("glab: 500 server error")

        self.assertEqual(self.run_post("--all-approved", "--post").code, 1)
        self.assertEqual(self.item(1)["status"], "posted")
        self.assertEqual(self.item(2)["status"], "proposed")

        self.fake.add_glab("{}")
        resumed = self.run_post("--all-approved", "--post")

        self.assertEqual(resumed.code, 0, resumed.stderr)
        self.assertEqual(len(self.fake.glab_calls), 3)
        self.assertEqual(self.item(2)["status"], "posted")

    # -- reply-only fast path --------------------------------------------

    def test_reply_only_fast_path_previews_without_gate_one(self):
        threads = [helpers.make_thread(f"gl:d{n}") for n in (1, 2, 3)]
        items = [
            helpers.make_item(1, threadIds=["gl:d1"], verdict="PUSH_BACK", replyDraft=DRAFT_ONE),
            helpers.make_item(2, threadIds=["gl:d2"], verdict="CLARIFY", replyDraft=DRAFT_TWO),
            helpers.make_item(3, threadIds=["gl:d3"], verdict="ALREADY_FIXED", replyDraft="Third."),
        ]
        self.write_state(self.base_state(threads=threads, items=items))
        before = self.state_path.read_bytes()

        preview = self.run_post("--all-approved")

        self.assertEqual(preview.code, 0, preview.stderr)
        self.assertIn(DRAFT_ONE, preview.stdout)
        self.assertIn(DRAFT_TWO, preview.stdout)
        self.assertIn("Third.", preview.stdout)
        self.assertEqual(self.fake.glab_calls, [])
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertTrue(all(item["status"] == "proposed" for item in self.read_state()["items"]))

    def test_reply_only_fast_path_still_requires_explicit_post(self):
        self.write_state(
            self.base_state(
                items=[helpers.make_item(1, verdict="PUSH_BACK", replyDraft=DRAFT_ONE)]
            )
        )

        preview = self.run_post("--all-approved")

        self.assertEqual(preview.code, 0, preview.stderr)
        self.assertIn("Preview only", preview.stdout)
        self.assertEqual(self.fake.glab_calls, [])

        self.fake.add_glab("{}")
        posted = self.run_post("--all-approved", "--post")

        self.assertEqual(posted.code, 0, posted.stderr)
        self.assertEqual(len(self.fake.glab_calls), 1)
        self.assertEqual(self.item(1)["status"], "posted")

    def test_reply_only_fast_path_refuses_a_plan_with_an_unapproved_code_item(self):
        threads = [helpers.make_thread("gl:d1"), helpers.make_thread("gl:d2")]
        items = [
            helpers.make_item(1, threadIds=["gl:d1"], verdict="ACCEPT", replyDraft=DRAFT_ONE),
            helpers.make_item(2, threadIds=["gl:d2"], verdict="PUSH_BACK", replyDraft=DRAFT_TWO),
        ]
        self.write_state(self.base_state(threads=threads, items=items))
        before = self.state_path.read_bytes()

        cap = self.run_post("--all-approved", "--post")

        self.assertEqual(cap.code, 1)
        self.assertIn("Gate 1", cap.stderr)
        self.assertIn("#1", cap.stderr)
        self.assertEqual(self.fake.glab_calls, [])
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_all_approved_refuses_a_plan_of_only_unapproved_code_items(self):
        self.write_state(
            self.base_state(
                items=[helpers.make_item(1, verdict="ALTERNATIVE", replyDraft=DRAFT_ONE)]
            )
        )

        cap = self.run_post("--all-approved", "--post")

        self.assertEqual(cap.code, 1)
        self.assertIn("Gate 1", cap.stderr)
        self.assertEqual(self.fake.glab_calls, [])

    def test_a_skipped_code_item_does_not_block_the_fast_path(self):
        threads = [helpers.make_thread("gl:d1"), helpers.make_thread("gl:d2")]
        items = [
            helpers.make_item(1, threadIds=["gl:d1"], verdict="ACCEPT", status="skipped"),
            helpers.make_item(2, threadIds=["gl:d2"], verdict="PUSH_BACK", replyDraft=DRAFT_TWO),
        ]
        self.write_state(self.base_state(threads=threads, items=items))
        self.fake.add_glab("{}")

        cap = self.run_post("--all-approved", "--post")

        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual(len(self.fake.glab_calls), 1, "only the reply-only item posts")
        self.assertIn("discussions/d2", " ".join(self.fake.glab_calls[0]))
        self.assertEqual(self.item(1)["status"], "skipped")
        self.assertEqual(self.item(2)["status"], "posted")

    # -- batch refuses unsafe overrides ----------------------------------

    def test_batch_refuses_a_single_body_override(self):
        self.write_state(
            self.base_state(
                items=[helpers.make_item(1, verdict="PUSH_BACK", replyDraft=DRAFT_ONE)]
            )
        )

        cap = self.run_post("--all-approved", "--body", "one text for all", "--post")

        self.assertEqual(cap.code, 1)
        self.assertIn("single-item overrides", cap.stderr)
        self.assertEqual(self.fake.glab_calls, [])

    def test_batch_refuses_an_empty_draft_before_any_call(self):
        threads = [helpers.make_thread("gl:d1"), helpers.make_thread("gl:d2")]
        items = [
            helpers.make_item(1, threadIds=["gl:d1"], verdict="PUSH_BACK", replyDraft=DRAFT_ONE),
            helpers.make_item(2, threadIds=["gl:d2"], verdict="PUSH_BACK", replyDraft=""),
        ]
        self.write_state(self.base_state(threads=threads, items=items))
        before = self.state_path.read_bytes()

        cap = self.run_post("--all-approved", "--post")

        self.assertEqual(cap.code, 1)
        self.assertIn("empty", cap.stderr.lower())
        self.assertEqual(self.fake.glab_calls, [], "a bad draft stops the whole batch")
        self.assertEqual(self.state_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
