#!/usr/bin/env python3
"""Tests for the deterministic renderer and its golden fixtures."""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

import comments  # noqa: E402

FIXTURES = HERE / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name / "input.json").read_text(encoding="utf-8"))


def base_comment(**overrides) -> dict:
    comment = {
        "id": "C1",
        "status": "pending",
        "type": "question",
        "severity": "nit",
        "anchor": {
            "kind": "inline",
            "path": "src/a.ts",
            "line": 4,
            "endLine": None,
            "inDiff": True,
            "verifiedAt": "abc1234",
            "verifiedHash": None,
            "verifiedText": "x",
        },
        "evidence": "src/a.ts:4",
        "source": {
            "kind": "diff",
            "decision": "open",
            "confidence": "medium",
            "quote": "SECRET QUOTE",
        },
        "title": "A question",
        "body": "A body line.",
        "suggestion": None,
        "long": False,
        "posted": {"noteId": None, "discussionId": None, "postedAt": None},
    }
    comment.update(overrides)
    return comment


def make_state(comments, dropped=None, lang="en", head="abc1234") -> dict:
    return {
        "schemaVersion": 1,
        "lang": lang,
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
            "diffRefs": {"base_sha": "1", "start_sha": "2", "head_sha": head},
        },
        "budget": {"target": 5, "max": 10, "forced": False},
        "comments": comments,
        "dropped": dropped or [],
        "events": [],
    }


class GoldenTests(unittest.TestCase):
    def test_golden_fixtures(self):
        for name in ("basic", "suggestion", "empty", "metadata", "fa"):
            with self.subTest(name=name):
                state = load_fixture(name)
                expected = (FIXTURES / name / "expected.md").read_text(encoding="utf-8")
                self.assertEqual(comments.render_markdown(state, "inline"), expected)


class ModeTests(unittest.TestCase):
    def test_inline_mode_omits_target_line(self):
        output = comments.render_markdown(load_fixture("basic"), "inline")
        boxes = re.findall(r"````markdown\n(.*?)\n````", output, re.DOTALL)
        self.assertTrue(boxes)
        for box in boxes:
            self.assertNotIn("**Target:**", box)
            self.assertNotIn("###", box)

    def test_summary_mode_includes_heading_and_target(self):
        output = comments.render_markdown(load_fixture("basic"), "summary")
        self.assertIn("### Throttle UI-to-JS dispatch in `panGesture.onChange`", output)
        self.assertIn(
            "**Target:** `src/components/VSlider/VSlider.tsx:118-124`", output
        )

    def test_summary_mode_omits_target_for_mr_anchor(self):
        output = comments.render_markdown(load_fixture("basic"), "summary")
        mr_box = output.split("#### C2")[1]
        self.assertNotIn("**Target:**", mr_box.split("####")[0])


class FenceTests(unittest.TestCase):
    def test_fence_collision_grows_outer_fence(self):
        state = make_state([base_comment(body="Example:\n\n````\ncode\n````")])
        output = comments.render_markdown(state, "inline")
        self.assertIn("`````markdown", output)
        self.assertIn("\n`````\n", output)

    def test_default_outer_fence_is_four(self):
        state = make_state([base_comment(body="Use `code` here.")])
        output = comments.render_markdown(state, "inline")
        self.assertIn("````markdown", output)

    def test_suggestion_block_exact_syntax(self):
        output = comments.render_markdown(load_fixture("suggestion"), "inline")
        self.assertIn("```suggestion:-0+0\nif (max > min) {\n  apply(value);\n}\n```", output)


class OrderingTests(unittest.TestCase):
    def test_severity_ordering(self):
        state = make_state(
            [
                base_comment(id="C1", severity="nit"),
                base_comment(id="C2", severity="blocking", body="b"),
                base_comment(id="C3", severity="correctness", body="c"),
                base_comment(
                    id="C4",
                    severity="nit",
                    anchor={"kind": "mr", "path": None, "line": None, "verifiedAt": "abc1234"},
                ),
            ]
        )
        output = comments.render_markdown(state, "inline")
        positions = [output.index(f"#### C{number}") for number in (2, 3, 1, 4)]
        self.assertEqual(positions, sorted(positions))

    def test_mr_anchor_sorts_last_within_severity(self):
        state = make_state(
            [
                base_comment(
                    id="C1",
                    severity="nit",
                    anchor={"kind": "mr", "path": None, "line": None, "verifiedAt": "abc1234"},
                ),
                base_comment(
                    id="C2",
                    severity="nit",
                    body="file anchor",
                    anchor={
                        "kind": "file",
                        "path": "src/b.ts",
                        "line": None,
                        "verifiedAt": "abc1234",
                    },
                ),
            ]
        )
        ordered = comments.order_comments(state)
        self.assertEqual([comment["id"] for comment in ordered], ["C2", "C1"])


class FooterTests(unittest.TestCase):
    def test_footer_counts(self):
        state = make_state(
            [base_comment(id="C1"), base_comment(id="C2", body="other")],
            dropped=[{"claim": "x", "reason": "y"}],
        )
        # Only C1 is verified at head; C2 is stale.
        state["comments"][1]["anchor"]["verifiedAt"] = "oldsha"
        self.assertEqual(
            comments.footer(state),
            "2 comments · 1/2 anchors verified at abc1234 · 1 dropped · lang=en",
        )

    def test_empty_state_has_explicit_message(self):
        output = comments.render_markdown(load_fixture("empty"), "inline")
        self.assertTrue(output.startswith("No actionable comments. 2 candidates were dropped:"))
        self.assertIn("0 comments · 0/0 anchors verified", output)

    def test_empty_state_without_dropped(self):
        output = comments.render_markdown(make_state([]), "inline")
        self.assertTrue(output.startswith("No actionable comments.\n\n0 comments"))


class PersianTests(unittest.TestCase):
    def test_persian_fixture_prose_starts_with_persian_words(self):
        output = comments.render_markdown(load_fixture("fa"), "inline")
        box = re.search(r"````markdown\n(.*?)\n````", output, re.DOTALL).group(1)
        prose = [
            line for line in box.splitlines()
            if line and not line.startswith(("**", "###", "```", "|"))
        ]
        self.assertTrue(prose)
        for line in prose:
            self.assertGreaterEqual(ord(line[0]), 0x0600, line)


class MetadataTests(unittest.TestCase):
    def test_metadata_line_and_repro_order(self):
        comment = base_comment(
            type="blocker",
            severity="correctness",
            kind="bug",
            affectsUsers=True,
            repro="1. Open the screen.\n\n**Expected:** It loads.\n**Actual:** It crashes.",
        )
        block = comments.body_for(comment, "inline")
        lines = block.split("\n\n")
        self.assertEqual(lines[0], "**A question**")
        self.assertEqual(
            lines[1],
            "**Type:** `blocker` · **Kind:** `bug` · "
            "**Severity:** `correctness` · **Affects users:** `yes`",
        )
        self.assertEqual(lines[2], "A body line.")
        self.assertEqual(lines[3], "**Steps to Reproduce**")
        self.assertIn("1. Open the screen.", lines[4])
        self.assertIn("**Expected:** It loads.", block)

    def test_repro_hidden_without_bug_or_visible_flag(self):
        comment = base_comment(
            kind="refactor",
            affectsUsers=False,
            repro="1. Press the button.",
        )
        self.assertNotIn("Steps to Reproduce", comments.body_for(comment, "inline"))

    def test_old_state_has_no_metadata_line(self):
        block = comments.body_for(base_comment(), "inline")
        self.assertNotIn("**Type:**", block)
        self.assertNotIn("**Severity:**", block)

    def test_affects_users_null_does_not_trigger(self):
        comment = base_comment(affectsUsers=None)
        self.assertNotIn("**Type:**", comments.body_for(comment, "inline"))

    def test_affects_users_false_renders_no(self):
        comment = base_comment(affectsUsers=False)
        self.assertIn("**Affects users:** `no`", comments.body_for(comment, "inline"))

    def test_preview_header_drops_type_when_line_renders(self):
        output = comments.render_markdown(load_fixture("metadata"), "inline")
        self.assertIn("#### C1 · src/components/VSlider/VSlider.tsx:118-124", output)
        self.assertNotIn("#### C1 · blocker", output)

    def test_preview_header_keeps_type_for_old_state(self):
        output = comments.render_markdown(load_fixture("basic"), "inline")
        self.assertIn(
            "#### C1 · blocker · src/components/VSlider/VSlider.tsx:118-124", output
        )

    def test_persian_metadata_is_localised(self):
        comment = base_comment(
            kind="spec-mismatch",
            severity="nit",
            affectsUsers=True,
        )
        block = comments.body_for(comment, "inline", "fa")
        self.assertIn("**دسته:** `پرسش`", block)
        self.assertIn("**ماهیت:** `عدم تطابق با spec`", block)
        self.assertIn("**اهمیت:** `جزئی`", block)
        self.assertIn("**تأثیر بر کاربر:** `بله`", block)

    def test_persian_labels_cover_every_enum_value(self):
        table = comments._META_LABELS["fa"]["values"]
        for group, codes in (
            ("type", comments.TYPES),
            ("kind", comments.FINDING_KINDS),
            ("severity", comments.SEVERITIES),
        ):
            for code in codes:
                with self.subTest(group=group, code=code):
                    self.assertIn(code, table[group])

    def test_unknown_language_falls_back_to_english(self):
        block = comments.body_for(
            base_comment(kind="bug", affectsUsers=True), "inline", "de"
        )
        self.assertIn("**Type:** `question`", block)
        self.assertIn("**Kind:** `bug`", block)

    def test_summary_uses_state_language(self):
        state = make_state(
            [base_comment(kind="bug", affectsUsers=True, severity="correctness")],
            lang="fa",
        )
        output = comments.render_markdown(state, "summary")
        self.assertIn("**ماهیت:** `باگ`", output)
        self.assertIn("**تأثیر بر کاربر:** `بله`", output)
        self.assertNotIn("**Kind:**", output)


class SafetyTests(unittest.TestCase):
    def test_source_quote_never_appears(self):
        state = make_state([base_comment()])
        self.assertIn("SECRET QUOTE", json.dumps(state))
        output = comments.render_markdown(state, "inline")
        self.assertNotIn("SECRET QUOTE", output)

    def test_rendering_is_byte_identical(self):
        state = load_fixture("basic")
        first = comments.render_markdown(state, "inline")
        second = comments.render_markdown(state, "inline")
        self.assertEqual(first.encode("utf-8"), second.encode("utf-8"))

    def test_render_does_not_mutate_state(self):
        state = load_fixture("basic")
        before = json.dumps(state, sort_keys=True)
        comments.render_markdown(state, "summary")
        self.assertEqual(json.dumps(state, sort_keys=True), before)


if __name__ == "__main__":
    unittest.main()
