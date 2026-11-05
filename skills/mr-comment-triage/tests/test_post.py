#!/usr/bin/env python3
"""Reply transport tests: draft default, per-thread journal, resume.

Every test drives ``post_reply.main`` with the subprocess boundary faked, so no
network or credentials are involved. The state file is a real file on disk and
each assertion reads it back the way the next invocation would.
"""

from __future__ import annotations

import json
import sys
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import helpers  # noqa: E402
import post_reply as reply  # noqa: E402
import triage_state as state_cmd  # noqa: E402

DRAFT = "Added the guard in src/app.py."
NOTE_URL = "https://gitlab.example.com/note/7"
# `--resolve` closes only your own threads; these fixtures are self-authored.
SELF_THREADS = [
    helpers.make_thread("gl:d1", author="me", authorKind="self"),
    helpers.make_thread("gl:d2", author="me", authorKind="self"),
]


class PostTests(helpers.RepoCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.install(reply)
        self.install(state_cmd)

    # -- per-thread journal ----------------------------------------------

    def test_each_thread_is_journaled_before_the_next_call(self):
        self.approve(threadIds=["gl:d1", "gl:d2"], replyDraft=DRAFT)
        self.fake.add_glab(json.dumps({"url": NOTE_URL}))
        before_calls = self.spy_states()

        cap = self.run_post("--item", "1", "--post")

        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual(len(before_calls), 2)
        self.assertEqual(before_calls[0]["items"][0]["posts"], [])
        second = before_calls[1]["items"][0]
        self.assertEqual([post["threadId"] for post in second["posts"]], ["gl:d1"])
        self.assertEqual(second["posts"][0]["body"], DRAFT)
        self.assertEqual(second["posts"][0]["url"], NOTE_URL)
        self.assertEqual(second["posts"][0]["source"], "draft")
        self.assertEqual(second["status"], "approved", "partial posting stays resumable")
        final = self.item()
        self.assertEqual(
            [post["threadId"] for post in final["posts"]], ["gl:d1", "gl:d2"]
        )
        self.assertEqual(final["status"], "posted")

    def test_status_is_derived_from_posts_not_item_level_fields(self):
        self.approve(threadIds=["gl:d1", "gl:d2"], replyDraft=DRAFT)
        self.fake.add_glab("{}")
        self.fake.add_glab("{}")

        cap = self.run_post("--item", "1", "--post")

        self.assertEqual(cap.code, 0, cap.stderr)
        item = self.item()
        self.assertEqual(len(item["posts"]), 2)
        self.assertNotIn("postedAt", item)
        self.assertNotIn("postedReplies", item)
        self.assertEqual(item["status"], "posted")

    def test_post_and_resolved_events_are_recorded_per_thread(self):
        self.approve(
            threads=SELF_THREADS,
            threadIds=["gl:d1", "gl:d2"],
            replyDraft=DRAFT,
        )
        for _ in range(4):
            self.fake.add_glab("{}")

        cap = self.run_post("--item", "1", "--post", "--resolve")

        self.assertEqual(cap.code, 0, cap.stderr)
        state = self.read_state()
        self.assertEqual(state["items"][0]["status"], "resolved")
        posted = [event for event in state["events"] if event["type"] == "posted"]
        resolved = [event for event in state["events"] if event["type"] == "resolved"]
        self.assertEqual(len(posted), 2)
        self.assertEqual(len(resolved), 2)
        self.assertIn("gl:d1", posted[0]["detail"])
        self.assertIn("gl:d2", resolved[1]["detail"])
        self.assertTrue(
            all(post["resolvedAt"] for post in state["items"][0]["posts"])
        )

    # -- partial failure and resume --------------------------------------

    def test_mid_batch_failure_keeps_success_and_reports_ids(self):
        self.approve(threadIds=["gl:d1", "gl:d2"], replyDraft=DRAFT)
        self.fake.add_glab(json.dumps({"url": NOTE_URL}))
        self.fake.fail_glab("glab: 500 server error")

        cap = self.run_post("--item", "1", "--post")

        self.assertEqual(cap.code, 1)
        state = self.read_state()
        item = state["items"][0]
        self.assertEqual([post["threadId"] for post in item["posts"]], ["gl:d1"])
        self.assertEqual(item["posts"][0]["body"], DRAFT)
        self.assertEqual(item["status"], "approved", "the batch stays resumable")
        self.assertEqual(
            len([event for event in state["events"] if event["type"] == "posted"]), 1
        )
        output = cap.stdout + cap.stderr
        self.assertIn("gl:d1", output)
        self.assertIn("gl:d2", output)
        self.assertIn("Succeeded", output)
        self.assertIn("Failed", output)

    def test_resume_posts_only_the_failed_thread(self):
        self.approve(threadIds=["gl:d1", "gl:d2"], replyDraft=DRAFT)
        self.fake.add_glab("{}")
        self.fake.fail_glab("glab: 500 server error")
        self.assertEqual(self.run_post("--item", "1", "--post").code, 1)
        calls_before = len(self.fake.glab_calls)

        self.fake.add_glab("{}")
        cap = self.run_post("--item", "1", "--post")

        self.assertEqual(cap.code, 0, cap.stderr)
        resumed = self.fake.glab_calls[calls_before:]
        self.assertEqual(len(resumed), 1)
        self.assertIn("discussions/d2", " ".join(resumed[0]))
        item = self.item()
        self.assertEqual([post["threadId"] for post in item["posts"]], ["gl:d1", "gl:d2"])
        self.assertEqual(item["status"], "posted")

    def test_a_fully_posted_item_is_never_posted_again(self):
        self.approve(replyDraft=DRAFT)
        self.fake.add_glab("{}")
        self.assertEqual(self.run_post("--item", "1", "--post").code, 0)
        calls_before = len(self.fake.glab_calls)

        cap = self.run_post("--item", "1", "--post")

        self.assertEqual(cap.code, 1)
        self.assertIn("posted", cap.stderr)
        self.assertEqual(len(self.fake.glab_calls), calls_before)
        self.assertEqual(len(self.item()["posts"]), 1)

    def test_failed_resolve_keeps_the_post_record_and_can_be_retried(self):
        self.approve(threads=[SELF_THREADS[0]], replyDraft=DRAFT)
        self.fake.add_glab(json.dumps({"url": NOTE_URL}))
        self.fake.fail_glab("glab: 500 server error")

        failed = self.run_post("--item", "1", "--post", "--resolve")

        self.assertEqual(failed.code, 1)
        post = self.item()["posts"][0]
        self.assertEqual(post["body"], DRAFT)
        self.assertIsNone(post["resolvedAt"])
        self.assertIn("resolve", (failed.stdout + failed.stderr).lower())

        self.fake.add_glab("{}")
        retried = self.run_post("--item", "1", "--post", "--resolve")

        self.assertEqual(retried.code, 0, retried.stderr)
        self.assertEqual(len(self.fake.glab_calls), 3, "no second reply note")
        post = self.item()["posts"][0]
        self.assertIsNotNone(post["resolvedAt"])
        self.assertEqual(self.item()["status"], "resolved")

    # -- duplicate ids and single-thread corrections ----------------------

    def test_duplicate_thread_ids_produce_one_post(self):
        self.approve(threadIds=["gl:d1", "gl:d1"], replyDraft=DRAFT)
        preview = self.run_post("--item", "1")
        self.assertEqual(preview.code, 0, preview.stderr)
        self.assertEqual(preview.stdout.count("gl:d1"), 1, "deduped before previewing")
        self.fake.add_glab("{}")

        cap = self.run_post("--item", "1", "--post")

        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual(len(self.fake.glab_calls), 1)
        self.assertEqual([post["threadId"] for post in self.item()["posts"]], ["gl:d1"])
        self.assertEqual(self.item()["status"], "posted")

    def test_single_thread_post_records_that_thread_only(self):
        self.approve(threadIds=["gl:d1", "gl:d2"], replyDraft=DRAFT)
        self.fake.add_glab(json.dumps({"url": NOTE_URL}))

        first = self.run_post("--item", "1", "--thread", "gl:d1", "--post")

        self.assertEqual(first.code, 0, first.stderr)
        self.assertEqual(len(self.fake.glab_calls), 1)
        self.assertIn("discussions/d1", " ".join(self.fake.glab_calls[0]))
        item = self.item()
        self.assertEqual([post["threadId"] for post in item["posts"]], ["gl:d1"])
        self.assertEqual(item["status"], "approved", "the other thread stays postable")

        self.fake.add_glab("{}")
        second = self.run_post("--item", "1", "--thread", "gl:d2", "--post")

        self.assertEqual(second.code, 0, second.stderr)
        item = self.item()
        self.assertEqual([post["threadId"] for post in item["posts"]], ["gl:d1", "gl:d2"])
        self.assertEqual(item["status"], "posted")

    def test_thread_requires_item(self):
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                reply.build_parser().parse_args(["--thread", "gl:d1", "--post"])

    # -- helpers ---------------------------------------------------------

    def spy_states(self) -> list[dict]:
        """Snapshot the state file before every faked glab call.

        The snapshot taken before call N shows exactly which thread records
        were journaled before the next external call started.
        """

        class Spy:
            def __init__(spy_self):
                spy_self.snapshots: list[dict] = []

            def __call__(spy_self, cmd, **kwargs):
                if cmd and cmd[0] == "glab":
                    spy_self.snapshots.append(
                        json.loads(self.state_path.read_text(encoding="utf-8"))
                    )
                return self.fake(cmd, **kwargs)

        spy = Spy()
        reply.run = spy
        return spy.snapshots

    def approve(self, *, threads=None, **overrides) -> None:
        state = self.base_state(items=[helpers.make_item(1, **overrides)])
        if threads is not None:
            state["threads"] = threads
        self.write_state(state)
        cap = self.run_state("approve", "1")
        self.assertEqual(cap.code, 0, cap.stderr)

    def run_state(self, *argv):
        cap = helpers.capture()
        cap.run(state_cmd.main, ["--state", str(self.state_path), *argv])
        return cap

    def run_post(self, *argv):
        cap = helpers.capture()
        cap.run(reply.main, ["--state", str(self.state_path), *argv])
        return cap

    def item(self) -> dict:
        return self.read_state()["items"][0]

    # -- draft default and overrides -------------------------------------

    def test_preview_uses_the_stored_reply_draft(self):
        self.approve(replyDraft=DRAFT)
        before = self.state_path.read_bytes()

        cap = self.run_post("--item", "1")

        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertIn(DRAFT, cap.stdout)
        self.assertIn("draft", cap.stdout)
        self.assertEqual(self.fake.glab_calls, [])
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_post_uses_the_reply_draft_by_default_and_records_it(self):
        self.approve(replyDraft=DRAFT)
        self.fake.add_glab(json.dumps({"url": NOTE_URL}))

        cap = self.run_post("--item", "1", "--post")

        self.assertEqual(cap.code, 0, cap.stderr)
        post = self.item()["posts"][0]
        self.assertEqual(post["body"], DRAFT)
        self.assertEqual(post["source"], "draft")
        self.assertEqual(post["url"], NOTE_URL)
        self.assertIsNotNone(post["postedAt"])
        self.assertIsNone(post["resolvedAt"])
        self.assertIn("body=" + DRAFT, " ".join(self.fake.glab_calls[0]))

    def test_body_override_is_posted_and_recorded(self):
        self.approve(replyDraft=DRAFT)
        self.fake.add_glab(json.dumps({"url": NOTE_URL}))

        cap = self.run_post("--item", "1", "--body", "Thanks, fixed.", "--post")

        self.assertEqual(cap.code, 0, cap.stderr)
        item = self.item()
        self.assertEqual(item["replyDraft"], DRAFT)
        self.assertEqual(item["posts"][0]["body"], "Thanks, fixed.")
        self.assertEqual(item["posts"][0]["source"], "override")

    def test_body_file_override_is_posted_and_recorded(self):
        self.approve(replyDraft=DRAFT)
        body_file = self.tmp_path / "reply.md"
        body_file.write_text("Body from a file.\n", encoding="utf-8")
        self.fake.add_glab("{}")

        cap = self.run_post("--item", "1", "--body-file", str(body_file), "--post")

        self.assertEqual(cap.code, 0, cap.stderr)
        post = self.item()["posts"][0]
        self.assertEqual(post["body"], "Body from a file.")
        self.assertEqual(post["source"], "override")

    def test_empty_draft_is_refused_before_any_call(self):
        self.approve(replyDraft="")
        before = self.state_path.read_bytes()

        cap = self.run_post("--item", "1", "--post")

        self.assertEqual(cap.code, 1)
        self.assertIn("empty", cap.stderr.lower())
        self.assertEqual(self.fake.glab_calls, [])
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_blank_override_is_refused_before_any_call(self):
        self.approve(replyDraft=DRAFT)
        before = self.state_path.read_bytes()

        cap = self.run_post("--item", "1", "--body", "   ", "--post")

        self.assertEqual(cap.code, 1)
        self.assertIn("empty", cap.stderr.lower())
        self.assertEqual(self.fake.glab_calls, [])
        self.assertEqual(self.state_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
