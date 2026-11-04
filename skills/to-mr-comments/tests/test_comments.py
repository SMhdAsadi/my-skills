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
        self.assertEqual(directory, self.root / "scratch")
        self.assertIn("scratch", source)

    def test_creatable_tmp_is_used_only_when_ignored(self):
        (self.root / ".gitignore").write_text(".tmp/\n", encoding="utf-8")
        directory, _ = _common.resolve_state_dir(self.root)
        self.assertEqual(directory, self.root / ".tmp")
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
            comments.main(["update", "C1", "--reanchor"])
        with self.assertRaises(_common.ScriptError):
            comments.main(["update", "C1", "--path", "a.txt", "--line", "3"])

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


if __name__ == "__main__":
    unittest.main()
