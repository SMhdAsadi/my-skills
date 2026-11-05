#!/usr/bin/env python3
"""Anchor correctness from collection through listing and rendering.

A range-only GitLab note must derive its side from ``line_range`` instead of
producing a null side, renamed files must keep their pre-rename path, and a
deleted file must anchor at its old path. No network, no credentials.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import helpers  # noqa: E402
import fetch_threads as fetch  # noqa: E402
import triage_state as state_cmd  # noqa: E402

DISCUSSION_ID = "a" * 40


def position(**overrides) -> dict:
    base = {
        "new_path": "src/app.py",
        "old_path": "src/app.py",
        "new_line": 12,
        "old_line": None,
        "head_sha": "abc123",
        "line_range": None,
    }
    base.update(overrides)
    return base


def discussion(**overrides) -> dict:
    return {
        "id": DISCUSSION_ID,
        "notes": [
            {
                "id": 1,
                "type": "DiffNote",
                "system": False,
                "resolvable": True,
                "resolved": False,
                "body": "This guard is missing.",
                "created_at": "2026-11-01T10:00:00Z",
                "author": {"username": "sara"},
                "position": position(**overrides),
            }
        ],
    }


def anchor(**overrides) -> dict:
    thread = fetch.normalize_gitlab_discussion(discussion(**overrides), "abc123")
    return thread["anchor"]


class RangeSideTests(unittest.TestCase):
    def test_new_line_is_new_side(self):
        result = anchor()
        self.assertEqual(result["kind"], "inline")
        self.assertEqual(result["side"], "new")
        self.assertEqual(result["line"], 12)
        self.assertIsNone(result["endLine"])

    def test_old_line_is_old_side(self):
        result = anchor(new_line=None, old_line=8)
        self.assertEqual(result["side"], "old")
        self.assertEqual(result["line"], 8)

    def test_range_only_new_side(self):
        result = anchor(
            new_line=None,
            line_range={"start": {"new_line": 20}, "end": {"new_line": 24}},
        )
        self.assertEqual(result["side"], "new")
        self.assertEqual(result["line"], 20)
        self.assertEqual(result["endLine"], 24)

    def test_range_only_old_side(self):
        result = anchor(
            new_line=None,
            line_range={"start": {"old_line": 10}, "end": {"old_line": 14}},
        )
        self.assertEqual(result["side"], "old")
        self.assertEqual(result["line"], 10)
        self.assertEqual(result["endLine"], 14)

    def test_one_sided_range_with_start_only(self):
        result = anchor(
            new_line=None,
            line_range={"start": {"new_line": 20}, "end": {}},
        )
        self.assertEqual(result["kind"], "inline")
        self.assertEqual(result["side"], "new")
        self.assertEqual(result["line"], 20)
        self.assertIsNone(result["endLine"])

    def test_one_sided_range_with_end_only(self):
        result = anchor(
            new_line=None,
            line_range={"start": {}, "end": {"old_line": 9}},
        )
        self.assertEqual(result["side"], "old")
        self.assertEqual(result["line"], 9)
        self.assertIsNone(result["endLine"])

    def test_mixed_range_prefers_new_side(self):
        result = anchor(
            new_line=None,
            line_range={
                "start": {"new_line": 20, "old_line": 10},
                "end": {"new_line": 24, "old_line": 14},
            },
        )
        self.assertEqual(result["side"], "new")
        self.assertEqual(result["line"], 20)
        self.assertEqual(result["endLine"], 24)

    def test_mixed_range_uses_the_new_side_values_only(self):
        result = anchor(
            new_line=None,
            line_range={"start": {"old_line": 10}, "end": {"new_line": 24}},
        )
        self.assertEqual(result["side"], "new")
        self.assertEqual(result["line"], 24)
        self.assertIsNone(result["endLine"])

    def test_range_anchors_never_have_a_null_side(self):
        ranges = [
            {"start": {"new_line": 20}, "end": {"new_line": 24}},
            {"start": {"old_line": 10}, "end": {"old_line": 14}},
            {"start": {"new_line": 20}, "end": {}},
            {"start": {}, "end": {"old_line": 9}},
            {"start": {"new_line": 20, "old_line": 10}, "end": {"old_line": 14}},
        ]
        for line_range in ranges:
            with self.subTest(line_range=line_range):
                result = anchor(new_line=None, line_range=line_range)
                self.assertEqual(result["kind"], "inline")
                self.assertIsNotNone(result["side"])


class AnchorPathTests(unittest.TestCase):
    def test_renamed_file_keeps_the_old_path(self):
        result = anchor(new_path="src/new.py", old_path="src/old.py")
        self.assertEqual(result["path"], "src/new.py")
        self.assertEqual(result["oldPath"], "src/old.py")

    def test_unchanged_path_has_no_old_path(self):
        result = anchor(new_path="src/app.py", old_path="src/app.py")
        self.assertIsNone(result["oldPath"])

    def test_deleted_file_uses_the_old_path(self):
        result = anchor(
            new_path=None, old_path="src/gone.py", new_line=None, old_line=8
        )
        self.assertEqual(result["kind"], "inline")
        self.assertEqual(result["path"], "src/gone.py")
        self.assertIsNone(result["oldPath"])
        self.assertEqual(result["side"], "old")

    def test_file_level_anchor_keeps_the_renamed_paths(self):
        result = anchor(
            new_path="src/new.py",
            old_path="src/old.py",
            new_line=None,
            old_line=None,
        )
        self.assertEqual(result["kind"], "file")
        self.assertEqual(result["path"], "src/new.py")
        self.assertEqual(result["oldPath"], "src/old.py")
        self.assertIsNone(result["side"])

    def test_mr_level_anchor_has_an_old_path_key(self):
        thread = fetch.normalize_gitlab_discussion(
            {
                "id": DISCUSSION_ID,
                "notes": [
                    {
                        "id": 1,
                        "type": "DiscussionNote",
                        "system": False,
                        "resolvable": True,
                        "resolved": False,
                        "body": "Whole-MR concern.",
                        "created_at": "2026-11-01T10:00:00Z",
                        "author": {"username": "sara"},
                        "position": None,
                    }
                ],
            },
            "abc123",
        )
        result = thread["anchor"]
        self.assertEqual(result["kind"], "mr")
        self.assertIsNone(result["path"])
        self.assertIsNone(result["oldPath"])
        self.assertIsNone(result["side"])


class AnchorDisplayTests(helpers.RepoCase, unittest.TestCase):
    def run_threads(self, *argv):
        cap = helpers.capture()
        cap.run(state_cmd.main, ["--state", str(self.state_path), *argv])
        return cap

    def old_side_thread(self) -> dict:
        return helpers.make_thread(
            "gl:old",
            anchor={
                "kind": "inline",
                "path": "src/new.py",
                "oldPath": "src/old.py",
                "line": 8,
                "endLine": None,
                "side": "old",
            },
        )

    def test_thread_listing_shows_the_old_side(self):
        self.write_state(threads=[self.old_side_thread()])
        cap = self.run_threads("threads")
        self.assertEqual(cap.code, 0)
        self.assertIn("src/new.py:8 (old)", cap.stdout)

    def test_thread_listing_shows_the_new_side(self):
        self.write_state(threads=[helpers.make_thread("gl:new")])
        cap = self.run_threads("threads")
        self.assertEqual(cap.code, 0)
        self.assertIn(f"{helpers.SOURCE_PATH}:3 (new)", cap.stdout)

    def test_render_shows_the_anchor_side(self):
        self.write_state(
            threads=[self.old_side_thread()],
            items=[helpers.make_item(1, threadIds=["gl:old"])],
        )
        cap = self.run_threads("render")
        self.assertEqual(cap.code, 0)
        self.assertIn("src/new.py:8 (old)", cap.stdout)

    def test_render_shows_the_new_side(self):
        self.write_state(items=[helpers.make_item(1, threadIds=["gl:d1"])])
        cap = self.run_threads("render")
        self.assertEqual(cap.code, 0)
        self.assertIn(f"{helpers.SOURCE_PATH}:3 (new)", cap.stdout)


if __name__ == "__main__":
    unittest.main()
