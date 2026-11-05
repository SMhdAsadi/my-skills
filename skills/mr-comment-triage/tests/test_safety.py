#!/usr/bin/env python3
"""Scratch-directory and command safety regressions.

Every test uses a real temporary git repository and a fake subprocess
boundary, so the suite stays offline and credential-free.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import _common  # noqa: E402

HOST = "gitlab.example.com"


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


class StateDirSafetyTests(unittest.TestCase):
    """MR_TRIAGE_DIR may never land in a tracked path."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.repo = self.base / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "test@example.com")
        git(self.repo, "config", "user.name", "Test")
        (self.repo / ".gitignore").write_text(".tmp/\nscratch/\n", encoding="utf-8")
        # An ignored scratch dir must exist for git to accept the directory
        # pattern; the resolver then uses it instead of the system temp dir.
        (self.repo / ".tmp").mkdir()
        (self.repo / "src").mkdir()
        (self.repo / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "base")
        self._original = os.environ.get("MR_TRIAGE_DIR")

    def tearDown(self) -> None:
        if self._original is None:
            os.environ.pop("MR_TRIAGE_DIR", None)
        else:
            os.environ["MR_TRIAGE_DIR"] = self._original
        self.tmp.cleanup()

    def set_override(self, path: Path) -> None:
        os.environ["MR_TRIAGE_DIR"] = str(path)

    def test_tracked_override_inside_repo_is_refused_and_not_created(self) -> None:
        target = self.repo / "notes"
        self.set_override(target)
        with self.assertRaises(_common.ScriptError) as caught:
            _common.resolve_state_dir(self.repo)
        message = str(caught.exception)
        self.assertIn(str(target), message)
        self.assertIn(str(self.repo), message)
        self.assertFalse(target.exists())

    def test_existing_tracked_override_inside_repo_is_refused(self) -> None:
        target = self.repo / "src"
        self.set_override(target)
        with self.assertRaises(_common.ScriptError) as caught:
            _common.resolve_state_dir(self.repo)
        self.assertIn(str(target), str(caught.exception))

    def test_repo_root_override_is_refused(self) -> None:
        self.set_override(self.repo)
        with self.assertRaises(_common.ScriptError):
            _common.resolve_state_dir(self.repo)

    def test_override_outside_repo_is_accepted(self) -> None:
        target = self.base / "outside" / "state"
        self.set_override(target)
        directory, source = _common.resolve_state_dir(self.repo)
        self.assertEqual(directory, target)
        self.assertEqual(source, "MR_TRIAGE_DIR")
        self.assertTrue(directory.is_dir())

    def test_gitignored_override_inside_repo_is_accepted(self) -> None:
        target = self.repo / ".tmp" / "mr-comment-triage"
        self.set_override(target)
        directory, source = _common.resolve_state_dir(self.repo)
        self.assertEqual(directory, target)
        self.assertEqual(source, "MR_TRIAGE_DIR")
        self.assertTrue(directory.is_dir())

    def test_normal_resolver_state_never_appears_in_git(self) -> None:
        os.environ.pop("MR_TRIAGE_DIR", None)
        directory, source = _common.resolve_state_dir(self.repo)
        self.assertIn("repo:", source)
        path = _common.state_path(directory, "group/api", 123)
        _common.save_state(path, {"schemaVersion": 2, "items": []})
        self.assertEqual(git(self.repo, "status", "--porcelain").stdout, "")
        self.assertEqual(
            git(self.repo, "ls-files", "--others", "--exclude-standard").stdout, ""
        )
        self.assertTrue(path.exists())

    def test_valid_override_state_never_appears_in_git(self) -> None:
        target = self.repo / ".tmp" / "override"
        self.set_override(target)
        directory, _ = _common.resolve_state_dir(self.repo)
        path = _common.state_path(directory, "group/api", 123)
        _common.save_state(path, {"schemaVersion": 2, "items": []})
        self.assertEqual(git(self.repo, "status", "--porcelain").stdout, "")
        self.assertEqual(
            git(self.repo, "ls-files", "--others", "--exclude-standard").stdout, ""
        )


class RunFailureTests(unittest.TestCase):
    """A failing subprocess stays diagnosable without leaking content."""

    def fail(self, cmd: list[str], *, stderr: str = "boom", code: int = 1) -> str:
        proc = subprocess.CompletedProcess(cmd, code, stdout="", stderr=stderr)
        with mock.patch.object(_common.subprocess, "run", return_value=proc):
            with self.assertRaises(_common.ScriptError) as caught:
                _common.run(cmd)
        return str(caught.exception)

    def test_failing_command_is_reported_exactly_with_host_and_endpoint(self) -> None:
        cmd = ["glab", "api", "--hostname", HOST, "projects/x/merge_requests/1"]
        message = self.fail(cmd)
        self.assertIn(" ".join(cmd), message)
        self.assertIn("glab api", message)
        self.assertIn(HOST, message)
        self.assertIn("projects/x/merge_requests/1", message)

    def test_form_body_value_is_redacted(self) -> None:
        body = "Looks good, ship it & merge R&D."
        cmd = [
            "glab", "api", "--hostname", HOST, "--method", "POST",
            "projects/x/merge_requests/1/discussions/abc/notes",
            "-f", f"body={body}",
        ]
        message = self.fail(cmd)
        for word in body.split():
            self.assertNotIn(word, message)
        self.assertIn("-f body=***", message)
        self.assertIn(HOST, message)
        self.assertIn("projects/x/merge_requests/1/discussions/abc/notes", message)

    def test_body_option_value_is_redacted(self) -> None:
        body = "Please fix the guard."
        message = self.fail(["glab", "api", "--body", body])
        for word in body.split():
            self.assertNotIn(word, message)
        self.assertIn("--body ***", message)

    def test_token_query_and_bare_body_are_redacted(self) -> None:
        cmd = [
            "glab", "api",
            "projects/x/merge_requests/1?private_token=SECRET_TOKEN&query=SECRET_QUERY",
            "body=SECRET_BODY",
            "token=SECRET_TOKEN_2",
        ]
        message = self.fail(cmd)
        for secret in ("SECRET_TOKEN", "SECRET_QUERY", "SECRET_BODY", "SECRET_TOKEN_2"):
            self.assertNotIn(secret, message)
        self.assertIn("private_token=***", message)
        self.assertIn("query=***", message)
        self.assertIn("body=***", message)

    def test_stderr_body_is_redacted_too(self) -> None:
        body = "Looks good, ship it & merge R&D."
        message = self.fail(
            ["glab", "api", "-f", f"body={body}"],
            stderr=f"request failed: body={body}",
        )
        for word in body.split():
            self.assertNotIn(word, message)

    def test_missing_tool_names_it_and_never_suggests_a_pasted_dump(self) -> None:
        with mock.patch.object(
            _common.subprocess, "run", side_effect=FileNotFoundError("no glab")
        ):
            with self.assertRaises(_common.ScriptError) as caught:
                _common.run(["glab", "api", "projects/x/merge_requests/1"])
        message = str(caught.exception)
        self.assertIn("glab", message)
        self.assertNotIn("pasted", message.lower())
        self.assertNotIn("dump", message.lower())


if __name__ == "__main__":
    unittest.main()
