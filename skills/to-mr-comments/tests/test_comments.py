#!/usr/bin/env python3
"""Tests for the comments state CLI (stdlib, no network)."""

from __future__ import annotations

import contextlib
import io
import itertools
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
import comments  # noqa: E402
import helpers  # noqa: E402


class StateDirTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        helpers.git(self.root, "init", "-q")
        self._old = os.environ.pop("MR_COMMENTS_DIR", None)

    def tearDown(self):
        self.tmp.cleanup()
        if self._old is not None:
            os.environ["MR_COMMENTS_DIR"] = self._old
        else:
            os.environ.pop("MR_COMMENTS_DIR", None)

    def test_env_override_wins(self):
        target = self.root / "elsewhere"
        os.environ["MR_COMMENTS_DIR"] = str(target)
        try:
            directory, source = _common.resolve_state_dir(self.root)
        finally:
            os.environ.pop("MR_COMMENTS_DIR", None)
        self.assertEqual(directory, target)
        self.assertEqual(source, "MR_COMMENTS_DIR")

    def test_existing_gitignored_dir_is_used(self):
        (self.root / ".gitignore").write_text("scratch/\n", encoding="utf-8")
        (self.root / "scratch").mkdir()
        directory, source = _common.resolve_state_dir(self.root)
        self.assertEqual(directory, self.root / "scratch" / "to-mr-comments")
        self.assertIn("scratch", source)

    def test_tmp_has_highest_priority(self):
        (self.root / ".gitignore").write_text(
            "tmp/\n.tmp/\nscratch/\n.scratch/\n", encoding="utf-8"
        )
        for name in ("tmp", ".tmp", "scratch", ".scratch"):
            (self.root / name).mkdir()
        directory, source = _common.resolve_state_dir(self.root)
        self.assertEqual(directory, self.root / "tmp" / "to-mr-comments")
        self.assertEqual(source, "repo:tmp")

    def test_unignored_tmp_is_skipped(self):
        (self.root / ".gitignore").write_text(".tmp/\n", encoding="utf-8")
        (self.root / "tmp").mkdir()
        directory, _ = _common.resolve_state_dir(self.root)
        self.assertEqual(directory, self.root / ".tmp" / "to-mr-comments")
        self.assertNotEqual(directory.parent, self.root / "tmp")

    def test_creatable_tmp_is_used_only_when_ignored(self):
        (self.root / ".gitignore").write_text(".tmp/\n", encoding="utf-8")
        directory, _ = _common.resolve_state_dir(self.root)
        self.assertEqual(directory, self.root / ".tmp" / "to-mr-comments")
        self.assertTrue(directory.is_dir())

    def test_unignored_tmp_is_not_used(self):
        (self.root / ".gitignore").write_text("# nothing\n", encoding="utf-8")
        with tempfile.TemporaryDirectory() as fake_temp:
            original = _common.tempfile.gettempdir
            _common.tempfile.gettempdir = lambda: fake_temp
            try:
                directory, source = _common.resolve_state_dir(self.root)
            finally:
                _common.tempfile.gettempdir = original
            self.assertEqual(source, "system-temp")

    def test_system_temp_fallback(self):
        (self.root / ".gitignore").write_text("# nothing\n", encoding="utf-8")
        with tempfile.TemporaryDirectory() as fake_temp:
            original = _common.tempfile.gettempdir
            _common.tempfile.gettempdir = lambda: fake_temp
            try:
                directory, source = _common.resolve_state_dir(self.root)
            finally:
                _common.tempfile.gettempdir = original
            self.assertEqual(directory, Path(fake_temp) / "to-mr-comments")
            self.assertEqual(source, "system-temp")

    def test_never_returns_a_tracked_path(self):
        (self.root / ".gitignore").write_text("# nothing\n", encoding="utf-8")
        with tempfile.TemporaryDirectory() as fake_temp:
            original = _common.tempfile.gettempdir
            _common.tempfile.gettempdir = lambda: fake_temp
            try:
                directory, _ = _common.resolve_state_dir(self.root)
            finally:
                _common.tempfile.gettempdir = original
        path = directory / "mr-comments-team-api-1.json"
        _common.save_state(path, {"schemaVersion": 1, "comments": []})
        tracked = helpers.git(self.root, "ls-files").stdout
        self.assertNotIn(path.name, tracked)
        if self.root in path.parents:
            self.assertNotIn(str(path.relative_to(self.root)), tracked)


class AtomicSaveTests(unittest.TestCase):
    def test_save_leaves_no_tmp_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = {"schemaVersion": 1, "comments": [{"id": "C1"}]}
            _common.save_state(path, state)
            self.assertEqual(_common.load_state(path), state)
            self.assertFalse((Path(tmp) / "state.json.tmp").exists())
            self.assertEqual(
                [entry.name for entry in Path(tmp).iterdir()], ["state.json"]
            )

    def test_state_filename_is_stable(self):
        self.assertEqual(
            _common.state_filename("team/api", 2340),
            "mr-comments-team-api-2340.json",
        )
        self.assertEqual(
            _common.state_filename("Group/Sub/Project", "7"),
            "mr-comments-Group-Sub-Project-7.json",
        )

    def test_legacy_draft_status_is_read_as_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "comments": [{"id": "C1", "status": "draft"}],
                    }
                ),
                encoding="utf-8",
            )
            state = _common.load_state(path)
        self.assertEqual(state["comments"][0]["status"], "pending")


class CliCase(helpers.RepoCase, unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.prepare_repo(Path(self._tmp.name))
        self.counter = itertools.count(1)

    def tearDown(self):
        self.cleanup_repo()
        self._tmp.cleanup()

    def body(self, text: str) -> str:
        path = self.files / f"body-{next(self.counter)}.md"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def suggestion(self, text: str) -> str:
        path = self.files / f"suggestion-{next(self.counter)}.txt"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def add(self, *, body_text="Does this guard handle zero?", extra=(), **overrides):
        values = {
            "type": "question",
            "severity": "nit",
            "title": "Question about the guard",
            "evidence": "a.txt:3",
            "source": "diff",
            "decision": "open",
            "confidence": "medium",
            "path": "a.txt",
            "line": 3,
        }
        values.update(overrides)
        argv = ["add", "--body-file", self.body(body_text)]
        mapping = {
            "type": "--type",
            "severity": "--severity",
            "title": "--title",
            "evidence": "--evidence",
            "source": "--source",
            "decision": "--decision",
            "confidence": "--confidence",
            "quote": "--quote",
            "path": "--path",
            "line": "--line",
            "end_line": "--end-line",
            "suggestion_file": "--suggestion-file",
        }
        for key, flag in mapping.items():
            value = values.get(key)
            if value is None:
                continue
            argv += [flag, str(value)]
        if values.get("long"):
            argv.append("--long")
        if values.get("force"):
            argv.append("--force")
        argv += list(extra)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return comments.main(argv)

    def cli(self, *argv):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return comments.main(list(argv))

    def blocked_add(self, **overrides):
        with self.assertRaises(_common.ScriptError):
            self.add(**overrides)

    def state(self, path: Path) -> dict:
        return _common.load_state(path)

    def capture(self, fn):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
            result = fn()
        return result, buffer.getvalue()


class AddValidationTests(CliCase):
    def test_valid_inline_add(self):
        path = self.init_state()
        self.add()
        state = self.state(path)
        self.assertEqual(len(state["comments"]), 1)
        comment = state["comments"][0]
        self.assertEqual(comment["id"], "C1")
        self.assertEqual(comment["status"], "pending")
        self.assertEqual(comment["anchor"]["kind"], "inline")
        self.assertTrue(comment["anchor"]["inDiff"])
        self.assertEqual(comment["anchor"]["verifiedAt"], self.head)
        self.assertIsNotNone(comment["anchor"]["verifiedHash"])

    def test_inline_without_line_is_rejected(self):
        self.init_state()
        self.blocked_add(path="a.txt", line=None, end_line=5)

    def test_path_only_is_a_file_anchor(self):
        path = self.init_state()
        self.add(path="a.txt", line=None)
        anchor = self.state(path)["comments"][0]["anchor"]
        self.assertEqual(anchor["kind"], "file")

    def test_line_without_path_is_rejected(self):
        self.init_state()
        self.blocked_add(path=None, line=3)

    def test_inline_not_in_diff_is_rejected(self):
        self.init_state()
        self.blocked_add(line=12)

    def test_blocker_with_open_decision_is_rejected(self):
        self.init_state()
        self.blocked_add(
            type="blocker", severity="correctness", decision="open", confidence="high"
        )

    def test_blocker_with_low_confidence_is_rejected(self):
        self.init_state()
        self.blocked_add(
            type="blocker", severity="correctness", decision="agreed", confidence="low"
        )

    def test_missing_evidence_is_rejected(self):
        self.init_state()
        self.blocked_add(evidence="")

    def test_weak_evidence_is_rejected(self):
        self.init_state()
        self.blocked_add(evidence="this looks slow to me")

    def test_duplicate_anchor_and_body_is_rejected(self):
        self.init_state()
        self.add(body_text="Same body.")
        self.blocked_add(body_text="Same body.")

    def test_title_over_60_chars_is_rejected(self):
        self.init_state()
        self.blocked_add(title="x" * 61)

    def test_body_word_budget(self):
        self.init_state()
        self.blocked_add(body_text="word " * 121)

    def test_long_allows_up_to_250_words(self):
        path = self.init_state()
        self.add(body_text="word " * 200, long=True)
        state = self.state(path)
        self.assertTrue(state["comments"][0]["long"])

    def test_long_still_rejects_over_250(self):
        self.init_state()
        self.blocked_add(body_text="word " * 251, long=True)

    def test_suggestion_requires_replacement(self):
        self.init_state()
        self.blocked_add(
            type="suggestion",
            severity="maintainability",
            decision="agreed",
            confidence="high",
        )

    def test_suggestion_longer_than_five_lines_is_rejected(self):
        self.init_state()
        self.blocked_add(
            type="suggestion",
            severity="maintainability",
            decision="agreed",
            confidence="high",
            suggestion_file=self.suggestion("a\nb\nc\nd\ne\nf\n"),
        )

    def test_budget_rejects_eleventh_and_force_records_it(self):
        path = self.init_state()
        for index in range(1, 11):
            self.add(body_text=f"Body number {index}.", title=f"Title number {index}")
        self.blocked_add(body_text="Body number 11.", title="Title number 11")
        self.add(body_text="Body number 11.", title="Title number 11", force=True)
        state = self.state(path)
        self.assertEqual(len(state["comments"]), 11)
        self.assertTrue(state["budget"]["forced"])

    def test_file_anchor_on_a_deleted_file(self):
        path = self.init_state()
        self.add(path="gone.txt", line=None, body_text="Why delete this?")
        anchor = self.state(path)["comments"][0]["anchor"]
        self.assertEqual(anchor["kind"], "file")
        self.assertEqual(anchor["path"], "gone.txt")
        self.assertEqual(anchor["verifiedAt"], self.head)

    def test_renamed_file_anchor_records_old_path(self):
        path = self.init_state()
        self.add(path="renamed.txt", line=None, body_text="Rename note.")
        anchor = self.state(path)["comments"][0]["anchor"]
        self.assertEqual(anchor["oldPath"], "old.txt")

    def test_add_rejects_end_line_past_the_file(self):
        self.init_state()
        self.blocked_add(line=3, end_line=99)

    def test_add_rejects_end_line_outside_the_hunk(self):
        self.init_state()
        self.blocked_add(line=3, end_line=12)

    def test_add_rejects_rejected_and_hypothesis_decisions(self):
        self.init_state()
        for decision in ("rejected", "hypothesis"):
            with self.subTest(decision=decision):
                self.blocked_add(decision=decision, confidence="high")

    def test_add_rejects_low_confidence_for_every_type(self):
        self.init_state()
        for ctype in ("question", "follow-up", "test-gap"):
            with self.subTest(ctype=ctype):
                self.blocked_add(
                    type=ctype, decision="agreed", confidence="low"
                )

    def test_add_rejects_open_on_a_non_question(self):
        self.init_state()
        for ctype in ("blocker", "suggestion", "follow-up", "test-gap"):
            with self.subTest(ctype=ctype):
                self.blocked_add(
                    type=ctype, decision="open", confidence="high"
                )

    def test_add_accepts_agreed_question(self):
        path = self.init_state()
        self.add(decision="agreed", confidence="high")
        source = self.state(path)["comments"][0]["source"]
        self.assertEqual(source["decision"], "agreed")


class LifecycleTests(CliCase):
    def comments_for_approval(self):
        return [{"id": f"C{number}"} for number in range(1, 5)]

    def test_approval_grammar_all(self):
        approved, skipped, overrides = comments.parse_approval(
            "all", self.comments_for_approval()
        )
        self.assertEqual(approved, [1, 2, 3, 4])
        self.assertEqual(skipped, [])
        self.assertEqual(overrides, {})

    def test_approval_grammar_numbers(self):
        approved, skipped, _ = comments.parse_approval(
            "1, 3", self.comments_for_approval()
        )
        self.assertEqual(approved, [1, 3])
        self.assertEqual(skipped, [])

    def test_approval_grammar_skip(self):
        approved, skipped, _ = comments.parse_approval(
            "all, skip 2", self.comments_for_approval()
        )
        self.assertEqual(approved, [1, 3, 4])
        self.assertEqual(skipped, [2])

    def test_approval_grammar_override(self):
        approved, _, overrides = comments.parse_approval(
            "2=APPROVE", self.comments_for_approval()
        )
        self.assertEqual(approved, [2])
        self.assertEqual(overrides, {2: "APPROVE"})

    def test_approval_accepts_comment_ids(self):
        approved, skipped, overrides = comments.parse_approval(
            "all, skip C2", self.comments_for_approval()
        )
        self.assertEqual(approved, [1, 3, 4])
        self.assertEqual(skipped, [2])
        approved, _, overrides = comments.parse_approval(
            "C3=DROP", self.comments_for_approval()
        )
        self.assertEqual(approved, [3])
        self.assertEqual(overrides, {3: "DROP"})

    def test_invalid_approval_expression_is_rejected(self):
        with self.assertRaises(_common.ScriptError):
            comments.parse_approval("maybe the second one", self.comments_for_approval())

    def test_unknown_comment_number_is_rejected(self):
        with self.assertRaises(_common.ScriptError):
            comments.parse_approval("1, 9", self.comments_for_approval())

    def test_drop_preserves_history(self):
        path = self.init_state()
        self.add()
        self.cli("drop", "C1", "--reason", "not actionable")
        state = self.state(path)
        self.assertEqual(len(state["comments"]), 1)
        self.assertEqual(state["comments"][0]["status"], "dropped")
        self.assertEqual(state["comments"][0]["dropReason"], "not actionable")
        self.assertTrue(any(event["kind"] == "dropped" for event in state["events"]))

    def test_ids_are_never_reused(self):
        path = self.init_state()
        self.add(body_text="First body.")
        self.cli("drop", "C1", "--reason", "no")
        self.add(body_text="Second body.")
        state = self.state(path)
        self.assertEqual([comment["id"] for comment in state["comments"]], ["C1", "C2"])

    def test_editing_approved_resets_to_pending(self):
        path = self.init_state()
        self.add()
        self.cli("approve", "all")
        self.assertEqual(self.state(path)["comments"][0]["status"], "approved")
        self.cli("update", "C1", "--title", "A better title")
        comment = self.state(path)["comments"][0]
        self.assertEqual(comment["status"], "pending")
        self.assertEqual(comment["title"], "A better title")

    def test_reanchor_requires_verification(self):
        self.init_state()
        self.add()
        with self.assertRaises(_common.ScriptError):
            comments.main(["update", "C1", "--path", "a.txt", "--line", "3"])

    def test_reanchor_without_path_demotes_to_mr(self):
        path = self.init_state()
        self.add()
        self.cli("update", "C1", "--reanchor")
        anchor = self.state(path)["comments"][0]["anchor"]
        self.assertEqual(anchor["kind"], "mr")
        self.assertIsNone(anchor["path"])
        self.assertEqual(anchor["verifiedAt"], self.head)

    def test_reanchor_kind_mr_with_path_is_rejected(self):
        self.init_state()
        self.add()
        with self.assertRaises(_common.ScriptError):
            comments.main(
                ["update", "C1", "--reanchor", "--kind", "mr", "--path", "a.txt"]
            )

    def test_reanchor_kind_file_on_a_renamed_file(self):
        path = self.init_state()
        self.add(path="a.txt", line=None, body_text="Renamed body.")
        self.cli(
            "update", "C1", "--reanchor", "--kind", "file", "--path", "renamed.txt"
        )
        anchor = self.state(path)["comments"][0]["anchor"]
        self.assertEqual(anchor["kind"], "file")
        self.assertEqual(anchor["path"], "renamed.txt")
        self.assertEqual(anchor["oldPath"], "old.txt")

    def test_reanchor_kind_and_line_must_agree(self):
        self.init_state()
        self.add()
        with self.assertRaises(_common.ScriptError):
            self.cli(
                "update",
                "C1",
                "--reanchor",
                "--kind",
                "file",
                "--path",
                "a.txt",
                "--line",
                "3",
            )
        with self.assertRaises(_common.ScriptError):
            self.cli("update", "C1", "--kind", "mr")

    def test_reanchor_to_outside_diff_is_rejected(self):
        self.init_state()
        self.add()
        with self.assertRaises(_common.ScriptError):
            comments.main(
                ["update", "C1", "--reanchor", "--path", "a.txt", "--line", "12"]
            )

    def test_list_orders_by_severity_and_json_shape(self):
        self.init_state()
        self.add(
            body_text="Nit body.", title="Nit", severity="nit", decision="open"
        )
        self.add(
            body_text="Blocker body.",
            title="Blocker",
            type="blocker",
            severity="blocking",
            decision="agreed",
            confidence="high",
        )
        self.add(
            body_text="Maintainability body.",
            title="Maintainability",
            severity="maintainability",
            decision="open",
        )
        _, output = self.capture(lambda: comments.main(["list"]))
        lines = [line for line in output.splitlines() if line.strip()]
        self.assertIn("Blocker", lines[0])
        self.assertIn("Maintainability", lines[1])

        result, json_output = self.capture(lambda: comments.main(["list", "--json"]))
        self.assertEqual(result, 0)
        payload = json.loads(json_output)
        self.assertEqual(set(payload), {"comments", "dropped", "budget"})
        self.assertEqual(payload["comments"][0]["id"], "C2")

    def test_init_rejects_non_gitlab_host(self):
        with self.assertRaises(_common.ScriptError) as caught:
            comments.main(
                [
                    "init",
                    "--project",
                    "team/api",
                    "--iid",
                    "7",
                    "--base",
                    self.base,
                    "--host",
                    "github.com",
                    "--offline",
                ]
            )
        self.assertIn("GitLab-only", str(caught.exception))

    def test_init_accepts_gitlab_and_stores_diff_refs(self):
        path = self.init_state()
        state = self.state(path)
        refs = state["mr"]["diffRefs"]
        self.assertEqual(refs["head_sha"], self.head)
        self.assertTrue(refs["base_sha"])
        self.assertTrue(refs["start_sha"])
        self.assertEqual(state["mr"]["provider"], "gitlab")

    def test_init_accepts_explicit_host_when_glab_is_unavailable(self):
        with mock.patch.object(
            comments, "is_gitlab_host", return_value=False
        ), mock.patch.object(comments, "glab_available", return_value=False):
            self.cli(
                "init",
                "--project",
                "team/api",
                "--iid",
                "8",
                "--base",
                self.base,
                "--host",
                "code.example.com",
                "--offline",
            )
        self.assertTrue((self.state_dir / "mr-comments-team-api-8.json").exists())

    def test_init_from_mr_failure_reports_the_exact_command(self):
        error = _common.ScriptError("`glab` failed:\nboom")
        real_run = comments.run

        def fake_run(cmd, **kwargs):
            if cmd and cmd[0] == "glab":
                raise error
            return real_run(cmd, **kwargs)

        with mock.patch.object(comments, "run", side_effect=fake_run):
            with self.assertRaises(_common.ScriptError) as caught:
                comments.main(
                    [
                        "init",
                        "--project",
                        "team/api",
                        "--iid",
                        "7",
                        "--base",
                        self.base,
                        "--host",
                        "gitlab.example.com",
                        "--from-mr",
                    ]
                )
        message = str(caught.exception)
        self.assertIn("glab api --hostname gitlab.example.com", message)
        self.assertIn("projects/team%2Fapi/merge_requests/7", message)


class DropCandidateTests(CliCase):
    def test_drop_claim_records_a_rejected_candidate(self):
        path = self.init_state()
        self.cli(
            "drop",
            "--claim",
            "Uniform LTR enforcement",
            "--reason",
            "unbounded audit; no anchor",
        )
        state = self.state(path)
        self.assertEqual(
            state["dropped"],
            [
                {
                    "claim": "Uniform LTR enforcement",
                    "reason": "unbounded audit; no anchor",
                    "source": "conversation",
                }
            ],
        )
        self.assertTrue(any(event["kind"] == "dropped" for event in state["events"]))
        self.assertEqual(state["comments"], [])

    def test_drop_claim_source_is_recorded(self):
        path = self.init_state()
        self.cli("drop", "--claim", "c1", "--reason", "no evidence", "--source", "diff")
        self.assertEqual(self.state(path)["dropped"][0]["source"], "diff")

    def test_dropped_candidate_renders_in_the_table_and_footer(self):
        path = self.init_state()
        self.cli("drop", "--claim", "Style preference", "--reason", "no consequence")
        self.cli("render")
        markdown = (path.parent / "mr-comments.md").read_text(encoding="utf-8")
        self.assertIn("| Style preference | no consequence |", markdown)
        self.assertIn("0 comments · 0/0 anchors verified", markdown)
        self.assertIn("1 dropped", markdown)

    def test_drop_requires_exactly_one_target(self):
        self.init_state()
        with self.assertRaises(_common.ScriptError):
            self.cli("drop", "C1", "--claim", "both", "--reason", "no")
        with self.assertRaises(_common.ScriptError):
            self.cli("drop", "--reason", "neither")
        with self.assertRaises(_common.ScriptError):
            self.cli("drop", "--claim", "   ", "--reason", "blank")

    def test_drop_source_only_applies_to_a_claim(self):
        path = self.init_state()
        self.add()
        with self.assertRaises(_common.ScriptError):
            self.cli("drop", "C1", "--reason", "no", "--source", "diff")
        self.assertEqual(self.state(path)["comments"][0]["status"], "pending")


class StateLifecycleTests(CliCase):
    def test_valid_update_flags_change_decision_and_type_together(self):
        path = self.init_state()
        self.add(body_text="Is this guard safe?")
        self.cli(
            "update",
            "C1",
            "--type",
            "blocker",
            "--severity",
            "correctness",
            "--decision",
            "agreed",
            "--confidence",
            "high",
        )
        comment = self.state(path)["comments"][0]
        self.assertEqual(comment["type"], "blocker")
        self.assertEqual(comment["source"]["decision"], "agreed")
        self.assertEqual(comment["source"]["confidence"], "high")

    def test_update_rejects_rejected_hypothesis_low_and_open_on_non_question(self):
        self.init_state()
        self.add()
        for argv in (
            ("--decision", "rejected"),
            ("--decision", "hypothesis"),
            ("--confidence", "low"),
            ("--type", "blocker", "--decision", "open"),
        ):
            with self.subTest(argv=argv):
                with self.assertRaises(_common.ScriptError):
                    self.cli("update", "C1", *argv)

    def test_update_no_long_applies_the_strict_budget(self):
        path = self.init_state()
        self.add(body_text="word " * 200, long=True)
        with self.assertRaises(_common.ScriptError):
            self.cli("update", "C1", "--no-long")
        self.cli(
            "update",
            "C1",
            "--no-long",
            "--body-file",
            self.body("A much shorter body."),
        )
        self.assertFalse(self.state(path)["comments"][0]["long"])

    def test_duplicate_check_runs_on_update(self):
        self.init_state()
        self.add(body_text="First body.")
        self.add(body_text="Second body.", title="Second")
        with self.assertRaises(_common.ScriptError):
            self.cli(
                "update", "C2", "--body-file", self.body("First body.")
            )

    def test_dropped_comment_does_not_block_a_replacement(self):
        path = self.init_state()
        self.add(body_text="Same body.")
        self.cli("drop", "C1", "--reason", "flawed")
        self.add(body_text="Same body.")
        state = self.state(path)
        self.assertEqual(state["comments"][0]["status"], "dropped")
        self.assertEqual(state["comments"][1]["status"], "pending")

    def test_duplicate_check_ignores_dropped_comments_on_update(self):
        path = self.init_state()
        self.add(body_text="First body.")
        self.add(body_text="Second body.", title="Second")
        self.cli("drop", "C1", "--reason", "flawed")
        self.cli("update", "C2", "--body-file", self.body("First body."))
        comment = self.state(path)["comments"][1]
        self.assertEqual(comment["body"], "First body.")

    def test_add_and_update_refuse_when_head_has_drifted(self):
        self.init_state()
        self.add()
        helpers.git(self.root, "commit", "-q", "--allow-empty", "-m", "drift")
        with self.assertRaises(_common.ScriptError) as caught:
            self.add(body_text="New body.")
        self.assertIn("The state is at", str(caught.exception))
        with self.assertRaises(_common.ScriptError):
            self.cli("update", "C1", "--title", "New title")

    def test_add_refuses_a_state_without_a_head_sha(self):
        path = self.init_state()
        state = self.state(path)
        del state["mr"]["headSha"]
        _common.save_state(path, state)
        with self.assertRaises(_common.ScriptError) as caught:
            self.add()
        self.assertIn("no HEAD SHA", str(caught.exception))

    def test_verify_syncs_head_and_diff_refs(self):
        path = self.init_state()
        self.add()
        helpers.git(self.root, "commit", "-q", "--allow-empty", "-m", "drift")
        new_head = helpers.git(self.root, "rev-parse", "HEAD").stdout.strip()
        self.assertNotEqual(new_head, self.head)
        self.cli("verify")
        state = self.state(path)
        self.assertEqual(state["mr"]["headSha"], new_head)
        self.assertEqual(state["mr"]["diffRefs"]["head_sha"], new_head)
        self.assertEqual(
            state["comments"][0]["anchor"]["verifiedAt"], new_head
        )

    def test_verify_does_not_partially_refresh_when_one_anchor_fails(self):
        path = self.init_state()
        self.add()
        self.add(body_text="Second body.", title="Second", path="new.txt", line=1)
        helpers.git(self.root, "commit", "-q", "--allow-empty", "-m", "drift")
        state = self.state(path)
        state["comments"][1]["anchor"]["path"] = "old.txt"
        state["comments"][1]["anchor"]["line"] = 1
        _common.save_state(path, state)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = comments.main(["verify"])
        self.assertEqual(result, 1)
        saved = self.state(path)
        self.assertEqual(saved["mr"]["headSha"], self.head)
        self.assertEqual(saved["comments"][0]["anchor"]["verifiedAt"], self.head)


if __name__ == "__main__":
    unittest.main()
