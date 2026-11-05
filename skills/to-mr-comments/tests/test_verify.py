#!/usr/bin/env python3
"""Tests for diff parsing and anchor verification (stdlib, no network)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

import helpers  # noqa: E402
import verify_anchors as va  # noqa: E402


class HunkParsingTests(unittest.TestCase):
    def test_single_hunk(self):
        diff = (
            "diff --git a/a.py b/a.py\n"
            "index 1111111..2222222 100644\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1,3 +1,4 @@\n"
            " alpha\n"
            "+beta\n"
            " gamma\n"
            " delta\n"
        )
        self.assertEqual(va.hunk_ranges(diff), {"a.py": [(1, 4)]})

    def test_omitted_count_means_one_line(self):
        diff = (
            "diff --git a/a.py b/a.py\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -7 +7 @@\n"
            "-old\n"
            "+new\n"
        )
        self.assertEqual(va.hunk_ranges(diff), {"a.py": [(7, 7)]})

    def test_multi_hunk_ranges(self):
        diff = (
            "diff --git a/a.py b/a.py\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1,2 +1,3 @@\n"
            " a\n"
            "+b\n"
            " c\n"
            "@@ -10,2 +11,2 @@\n"
            "-x\n"
            "+y\n"
            " z\n"
        )
        self.assertEqual(va.hunk_ranges(diff), {"a.py": [(1, 3), (11, 12)]})

    def test_new_file_is_fully_anchorable(self):
        diff = (
            "diff --git a/new.py b/new.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/new.py\n"
            "@@ -0,0 +1,3 @@\n"
            "+a\n"
            "+b\n"
            "+c\n"
        )
        self.assertEqual(va.hunk_ranges(diff), {"new.py": [(1, 3)]})

    def test_deleted_file_has_no_new_lines(self):
        diff = (
            "diff --git a/old.py b/old.py\n"
            "deleted file mode 100644\n"
            "--- a/old.py\n"
            "+++ /dev/null\n"
            "@@ -1,2 +0,0 @@\n"
            "-a\n"
            "-b\n"
        )
        self.assertEqual(va.hunk_ranges(diff), {"old.py": []})

    def test_rename_uses_destination_path(self):
        diff = (
            "diff --git a/old.py b/new.py\n"
            "similarity index 90%\n"
            "rename from old.py\n"
            "rename to new.py\n"
            "--- a/old.py\n"
            "+++ b/new.py\n"
            "@@ -1 +1 @@\n"
            "-a\n"
            "+b\n"
        )
        ranges = va.hunk_ranges(diff)
        self.assertIn("new.py", ranges)
        self.assertNotIn("old.py", ranges)

    def test_pure_rename_is_a_changed_file(self):
        diff = (
            "diff --git a/old.py b/new.py\n"
            "similarity index 100%\n"
            "rename from old.py\n"
            "rename to new.py\n"
        )
        self.assertEqual(va.hunk_ranges(diff), {"new.py": []})

    def test_binary_diff_has_no_anchorable_lines(self):
        diff = (
            "diff --git a/logo.png b/logo.png\n"
            "index 1111111..2222222 100644\n"
            "Binary files a/logo.png and b/logo.png differ\n"
        )
        self.assertEqual(va.hunk_ranges(diff), {"logo.png": []})

    def test_parse_changes_tracks_rename_source(self):
        diff = (
            "diff --git a/old.py b/new.py\n"
            "similarity index 90%\n"
            "rename from old.py\n"
            "rename to new.py\n"
            "--- a/old.py\n"
            "+++ b/new.py\n"
            "@@ -1 +1 @@\n"
            "-a\n"
            "+b\n"
        )
        ranges, renames = va.parse_changes(diff)
        self.assertIn("new.py", ranges)
        self.assertEqual(renames, {"new.py": "old.py"})

    def test_parse_changes_tracks_copy_source(self):
        diff = (
            "diff --git a/source.py b/twin.py\n"
            "similarity index 100%\n"
            "copy from source.py\n"
            "copy to twin.py\n"
        )
        ranges, renames = va.parse_changes(diff)
        self.assertEqual(ranges, {"twin.py": []})
        self.assertEqual(renames, {"twin.py": "source.py"})

    def test_parse_changes_without_rename_has_empty_map(self):
        diff = (
            "diff --git a/a.py b/a.py\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1,3 +1,4 @@\n"
            " alpha\n"
            "+beta\n"
            " gamma\n"
            " delta\n"
        )
        self.assertEqual(va.parse_changes(diff)[1], {})


class RealDiffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        self.base, self.head = helpers.build_repo(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_diff_on_a_real_branch(self):
        ranges = va.parse_diff(self.base, self.head, self.root)
        self.assertIn("a.txt", ranges)
        self.assertIn("new.txt", ranges)
        self.assertIn("gone.txt", ranges)
        self.assertIn("renamed.txt", ranges)
        self.assertEqual(ranges["gone.txt"], [])
        self.assertEqual(ranges["new.txt"], [(1, 4)])
        self.assertEqual(ranges["renamed.txt"], [])

    def test_parse_diff_changes_tracks_a_real_rename(self):
        ranges, renames = va.parse_diff_changes(self.base, self.head, self.root)
        self.assertEqual(ranges["renamed.txt"], [])
        self.assertEqual(renames, {"renamed.txt": "old.txt"})
        self.assertNotIn("gone.txt", renames)

    def test_file_anchor_on_a_really_deleted_file_is_ok(self):
        status, detail = va.verify_anchor(
            {"kind": "file", "path": "gone.txt"},
            {"gone.txt": []},
            self.root,
            self.head,
        )
        self.assertEqual(status, "ok")
        self.assertEqual(detail, "gone.txt")


class AnchorVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.lines = [f"line{i}" for i in range(1, 21)]
        (self.root / "a.py").write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        self.ranges = {"a.py": [(5, 8)]}
        self.head = "a" * 40

    def tearDown(self):
        self.tmp.cleanup()

    def anchor(self, **overrides):
        anchor = {"kind": "inline", "path": "a.py", "line": 5}
        anchor.update(overrides)
        return anchor

    def test_range_start_and_end_boundaries(self):
        for line in (5, 8):
            status, _ = va.verify_anchor(
                self.anchor(line=line), self.ranges, self.root, self.head
            )
            self.assertEqual(status, "ok", line)

    def test_line_just_outside_range(self):
        for line in (4, 9):
            status, _ = va.verify_anchor(
                self.anchor(line=line), self.ranges, self.root, self.head
            )
            self.assertEqual(status, "out-of-diff", line)

    def test_end_line_is_display_only(self):
        anchor = self.anchor(line=5, endLine=8)
        status, _ = va.verify_anchor(anchor, self.ranges, self.root, self.head)
        self.assertEqual(status, "ok")

    def test_end_line_past_file_length_is_missing(self):
        anchor = self.anchor(line=5, endLine=40)
        status, detail = va.verify_anchor(anchor, self.ranges, self.root, self.head)
        self.assertEqual(status, "missing")
        self.assertIn("outside the file", detail)

    def test_end_line_past_the_hunk_is_out_of_diff(self):
        anchor = self.anchor(line=5, endLine=9)
        status, _ = va.verify_anchor(anchor, self.ranges, self.root, self.head)
        self.assertEqual(status, "out-of-diff")

    def test_span_across_two_hunks_is_out_of_diff(self):
        anchor = self.anchor(line=5, endLine=11)
        status, _ = va.verify_anchor(
            anchor, {"a.py": [(5, 6), (10, 12)]}, self.root, self.head
        )
        self.assertEqual(status, "out-of-diff")

    def test_inline_line_past_file_length_is_missing(self):
        anchor = self.anchor(line=21)
        status, detail = va.verify_anchor(anchor, {"a.py": [(21, 25)]}, self.root, self.head)
        self.assertEqual(status, "missing")
        self.assertIn("outside the file", detail)

    def test_file_anchor_outside_diff_is_out_of_diff(self):
        (self.root / "b.py").write_text("x\n", encoding="utf-8")
        status, _ = va.verify_anchor(
            {"kind": "file", "path": "b.py"}, {"a.py": [(1, 3)]}, self.root, self.head
        )
        self.assertEqual(status, "out-of-diff")

    def test_head_moved_short_circuits_content_checks(self):
        anchor = self.anchor(path="does-not-exist.py", line=999)
        status, detail = va.verify_anchor(
            anchor, self.ranges, self.root, self.head, state_head="b" * 40
        )
        self.assertEqual(status, "head-moved")
        self.assertIn("state is at", detail)

    def test_hash_mismatch_is_moved(self):
        anchor = self.anchor(verifiedHash="sha256:deadbeef")
        status, _ = va.verify_anchor(anchor, self.ranges, self.root, self.head)
        self.assertEqual(status, "moved")

    def test_matching_hash_is_ok(self):
        anchor = self.anchor(verifiedHash=va.range_hash("a.py", 5, 5, self.root))
        status, _ = va.verify_anchor(anchor, self.ranges, self.root, self.head)
        self.assertEqual(status, "ok")

    def test_missing_file(self):
        anchor = self.anchor(path="nope.py", line=5)
        status, _ = va.verify_anchor(anchor, {"nope.py": [(1, 9)]}, self.root, self.head)
        self.assertEqual(status, "missing")

    def test_file_outside_diff(self):
        (self.root / "b.py").write_text("x\n", encoding="utf-8")
        status, _ = va.verify_anchor(
            self.anchor(path="b.py", line=1),
            {"a.py": [(1, 3)]},
            self.root,
            self.head,
        )
        self.assertEqual(status, "out-of-diff")

    def test_deleted_file_inline_is_out_of_diff(self):
        (self.root / "gone.py").write_text("x\n", encoding="utf-8")
        anchor = {"kind": "inline", "path": "gone.py", "line": 1}
        status, _ = va.verify_anchor(anchor, {"gone.py": []}, self.root, self.head)
        self.assertEqual(status, "out-of-diff")

    def test_file_anchor_on_binary_is_ok(self):
        (self.root / "logo.png").write_bytes(b"\x89PNG")
        status, _ = va.verify_anchor(
            {"kind": "file", "path": "logo.png"}, {"logo.png": []}, self.root, self.head
        )
        self.assertEqual(status, "ok")

    def test_mr_anchor_is_always_ok(self):
        status, _ = va.verify_anchor({"kind": "mr"}, {}, self.root, self.head)
        self.assertEqual(status, "ok")

    def test_mr_anchor_still_respects_head_moved(self):
        status, _ = va.verify_anchor(
            {"kind": "mr"}, {}, self.root, self.head, state_head="b" * 40
        )
        self.assertEqual(status, "head-moved")

    def test_range_hash_changes_with_text(self):
        before = va.range_hash("a.py", 5, 5, self.root)
        text = (self.root / "a.py").read_text(encoding="utf-8").replace(
            "line5", "line5-changed"
        )
        (self.root / "a.py").write_text(text, encoding="utf-8")
        after = va.range_hash("a.py", 5, 5, self.root)
        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
