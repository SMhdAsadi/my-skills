#!/usr/bin/env python3
"""Tests for the mr-comment-triage helper scripts (stdlib unittest, no network)."""

from __future__ import annotations

import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import _common  # noqa: E402
import fetch_threads as fetch  # noqa: E402
import post_reply as reply  # noqa: E402
import triage_state as state_cmd  # noqa: E402


class ParseRemoteTests(unittest.TestCase):
    def test_scp_style(self):
        self.assertEqual(
            fetch.parse_remote("git@gitlab.com:group/api.git"), ("gitlab.com", "group/api")
        )

    def test_https_with_git_suffix(self):
        self.assertEqual(
            fetch.parse_remote("https://gitlab.com/group/api.git"), ("gitlab.com", "group/api")
        )

    def test_self_hosted_with_port(self):
        self.assertEqual(
            fetch.parse_remote("ssh://git@code.example.com:2222/team/api.git"),
            ("code.example.com", "team/api"),
        )

    def test_https_with_credentials(self):
        self.assertEqual(
            fetch.parse_remote("https://user:token@gitlab.example.com/group/sub/repo.git"),
            ("gitlab.example.com", "group/sub/repo"),
        )

    def test_garbage(self):
        self.assertIsNone(fetch.parse_remote("/local/path/repo"))


class GitLabOnlyTests(unittest.TestCase):
    """The Skill ships a single GitLab transport and no provider switch."""

    def test_collector_has_no_provider_flag(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                fetch.build_parser().parse_args(["--provider", "gitlab"])

    def test_collector_has_no_github_symbols(self):
        for name in (
            "GITHUB_QUERY",
            "detect_provider",
            "github_api",
            "fetch_github",
            "normalize_github_thread",
        ):
            self.assertFalse(hasattr(fetch, name), name)

    def test_reply_transport_has_no_github_symbols(self):
        for name in ("REPLY_MUTATION", "RESOLVE_MUTATION", "github_reply", "github_resolve"):
            self.assertFalse(hasattr(reply, name), name)

    def test_documents_never_claim_github(self):
        docs = [
            SKILL_ROOT / "SKILL.md",
            SKILL_ROOT / "README.md",
            *sorted((SKILL_ROOT / "references").glob("*.md")),
        ]
        banned = (
            re.compile(r"\bgh\b"),
            re.compile(r"github", re.IGNORECASE),
            re.compile(r"graphql", re.IGNORECASE),
            re.compile(r"gh_host", re.IGNORECASE),
            re.compile(r"--provider"),
        )
        for path in docs:
            text = path.read_text(encoding="utf-8")
            for pattern in banned:
                self.assertIsNone(
                    pattern.search(text), f"{path.name} still matches {pattern.pattern!r}"
                )


class AuthorTests(unittest.TestCase):
    def test_self_wins(self):
        self.assertEqual(fetch.classify_author("me", "me"), "self")

    def test_suffix_and_known(self):
        self.assertEqual(fetch.classify_author("dependabot[bot]"), "bot")
        self.assertEqual(fetch.classify_author("copilot-pull-request-reviewer"), "bot")
        self.assertEqual(fetch.classify_author("alice"), "human")

    def test_unknown(self):
        self.assertEqual(fetch.classify_author(None), "unknown")


def gitlab_discussion(**overrides):
    discussion = {
        "id": "a" * 40,
        "notes": [
            {
                "id": 1,
                "type": "DiffNote",
                "system": False,
                "resolvable": True,
                "resolved": False,
                "body": "Missing null check",
                "created_at": "2026-10-01T10:00:00Z",
                "author": {"username": "sara"},
                "position": {
                    "new_path": "lib/job.rb",
                    "new_line": 12,
                    "old_path": "lib/job.rb",
                    "old_line": None,
                    "head_sha": "abc123",
                    "line_range": None,
                },
            }
        ],
    }
    discussion.update(overrides)
    return discussion


class GitlabNormalizeTests(unittest.TestCase):
    def test_inline_anchor(self):
        thread = fetch.normalize_gitlab_discussion(gitlab_discussion(), "abc123", "me")
        self.assertEqual(thread["id"], "gl:" + "a" * 40)
        self.assertEqual(thread["anchor"]["kind"], "inline")
        self.assertFalse(thread["stale"])

    def test_system_note_is_skipped(self):
        discussion = gitlab_discussion()
        discussion["notes"][0].update({"system": True, "resolvable": False, "resolved": None})
        self.assertIsNone(fetch.normalize_gitlab_discussion(discussion, "abc123"))

    def test_non_resolvable_is_skipped(self):
        discussion = gitlab_discussion()
        discussion["notes"][0].update({"resolvable": False, "resolved": None})
        self.assertIsNone(fetch.normalize_gitlab_discussion(discussion, "abc123"))

    def test_mr_level_thread_has_no_position(self):
        discussion = gitlab_discussion()
        discussion["notes"][0].update({"type": "DiscussionNote", "position": None})
        thread = fetch.normalize_gitlab_discussion(discussion, "abc123")
        self.assertEqual(thread["anchor"]["kind"], "mr")

    def test_thread_with_leading_system_note_is_kept(self):
        discussion = gitlab_discussion()
        discussion["notes"].insert(
            0,
            {
                "id": 0,
                "system": True,
                "resolvable": False,
                "resolved": None,
                "body": "added 1 commit",
                "author": {"username": "sara"},
            },
        )
        thread = fetch.normalize_gitlab_discussion(discussion, "abc123")
        self.assertIsNotNone(thread)
        self.assertEqual(thread["anchor"]["line"], 12)
        self.assertEqual(thread["replies"], [])

    def test_stale_when_head_moved(self):
        thread = fetch.normalize_gitlab_discussion(gitlab_discussion(), "different")
        self.assertTrue(thread["stale"])

    def test_line_range_uses_start_and_end(self):
        discussion = gitlab_discussion()
        discussion["notes"][0]["position"].update(
            {
                "new_line": None,
                "line_range": {
                    "start": {"new_line": 20},
                    "end": {"new_line": 24},
                },
            }
        )
        thread = fetch.normalize_gitlab_discussion(discussion, "abc123")
        self.assertEqual(thread["anchor"]["line"], 20)
        self.assertEqual(thread["anchor"]["endLine"], 24)

    def test_deleted_line_uses_old_side(self):
        discussion = gitlab_discussion()
        discussion["notes"][0]["position"].update(
            {"new_line": None, "old_line": 8, "line_range": None}
        )
        thread = fetch.normalize_gitlab_discussion(discussion, "abc123")
        self.assertEqual(thread["anchor"]["side"], "old")
        self.assertEqual(thread["anchor"]["line"], 8)


class ApprovalParseTests(unittest.TestCase):
    def setUp(self):
        self.items = [
            {"n": 1, "verdict": "ACCEPT"},
            {"n": 2, "verdict": "CLARIFY"},
            {"n": 3, "verdict": "PUSH_BACK"},
            {"n": 4, "verdict": "DEFER"},
        ]

    def test_all(self):
        approved, skipped, overrides = state_cmd.parse_approval("all", self.items)
        self.assertEqual(approved, [1, 2, 3, 4])
        self.assertEqual(skipped, [])
        self.assertEqual(overrides, {})

    def test_explicit_numbers(self):
        approved, skipped, _ = state_cmd.parse_approval("1, 3", self.items)
        self.assertEqual(approved, [1, 3])
        self.assertEqual(skipped, [])

    def test_skip(self):
        approved, skipped, _ = state_cmd.parse_approval("all, skip 2", self.items)
        self.assertEqual(approved, [1, 3, 4])
        self.assertEqual(skipped, [2])

    def test_override(self):
        approved, _, overrides = state_cmd.parse_approval("2=ACCEPT", self.items)
        self.assertEqual(approved, [2])
        self.assertEqual(overrides, {2: "ACCEPT"})

    def test_approve_prefix_is_tolerated(self):
        approved, _, _ = state_cmd.parse_approval("Approve 1 and 3".replace(" and ", ", "), self.items)
        self.assertEqual(approved, [1, 3])

    def test_unknown_item_raises(self):
        with self.assertRaises(_common.ScriptError):
            state_cmd.parse_approval("1, 9", self.items)

    def test_garbage_raises(self):
        with self.assertRaises(_common.ScriptError):
            state_cmd.parse_approval("maybe the second one", self.items)


class EvidenceParseTests(unittest.TestCase):
    def test_path_and_line(self):
        self.assertEqual(
            state_cmd.parse_evidence(["src/app.ts:42"]),
            [{"path": "src/app.ts", "line": 42, "note": ""}],
        )

    def test_path_line_and_note(self):
        self.assertEqual(
            state_cmd.parse_evidence(["pkg/x.go:600:early return removed"]),
            [{"path": "pkg/x.go", "line": 600, "note": "early return removed"}],
        )

    def test_multiple_entries(self):
        parsed = state_cmd.parse_evidence(["a.ts:1", "b.ts:2:why"])
        self.assertEqual([entry["path"] for entry in parsed], ["a.ts", "b.ts"])

    def test_missing_line_raises(self):
        with self.assertRaises(_common.ScriptError):
            state_cmd.parse_evidence(["src/app.ts"])


class StateDirTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        (self.root / ".gitignore").write_text("*.tmp\nscratch/\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_ignored_tmp_dir(self):
        directory, source = _common.resolve_state_dir(self.root)
        self.assertEqual(directory, self.root / ".tmp" / "mr-comment-triage")
        self.assertIn("repo:", source)
        self.assertTrue(directory.is_dir())

    def test_tmp_has_highest_priority(self):
        (self.root / ".gitignore").write_text(
            "tmp/\n.tmp/\nscratch/\n.scratch/\n", encoding="utf-8"
        )
        for name in ("tmp", ".tmp", "scratch", ".scratch"):
            (self.root / name).mkdir()
        directory, source = _common.resolve_state_dir(self.root)
        self.assertEqual(directory, self.root / "tmp" / "mr-comment-triage")
        self.assertEqual(source, "repo:tmp")

    def test_unignored_tmp_is_skipped(self):
        (self.root / ".gitignore").write_text("*.tmp\n", encoding="utf-8")
        (self.root / "tmp").mkdir()
        directory, _ = _common.resolve_state_dir(self.root)
        self.assertEqual(directory, self.root / ".tmp" / "mr-comment-triage")

    def test_prefers_existing_ignored_scratch(self):
        (self.root / "scratch").mkdir()
        directory, source = _common.resolve_state_dir(self.root)
        self.assertEqual(directory, self.root / "scratch" / "mr-comment-triage")
        self.assertIn("scratch", source)

    def test_skips_existing_but_unignored_directory(self):
        (self.root / ".gitignore").write_text("*.tmp\n", encoding="utf-8")
        (self.root / "scratch").mkdir()
        directory, _ = _common.resolve_state_dir(self.root)
        self.assertNotEqual(directory.parent, self.root / "scratch")

    def test_falls_back_to_system_temp_when_nothing_is_ignored(self):
        (self.root / ".gitignore").write_text("# nothing\n", encoding="utf-8")
        with tempfile.TemporaryDirectory() as fake_temp:
            original = _common.tempfile.gettempdir
            _common.tempfile.gettempdir = lambda: fake_temp
            try:
                directory, source = _common.resolve_state_dir(self.root)
            finally:
                _common.tempfile.gettempdir = original
            self.assertEqual(source, "system-temp")
            self.assertEqual(directory, Path(fake_temp) / "mr-comment-triage")

    def test_state_file_is_invisible_to_git(self):
        directory, _ = _common.resolve_state_dir(self.root)
        path = _common.state_path(directory, "gitlab", "group/api", 2340)
        _common.save_state(path, {"schemaVersion": 1, "items": []})
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        self.assertNotIn(path.name, untracked.stdout)
        self.assertTrue(path.exists())

    def test_env_override_wins(self):
        target = self.root / "elsewhere"
        original = _common.os.environ.get("MR_TRIAGE_DIR")
        _common.os.environ["MR_TRIAGE_DIR"] = str(target)
        try:
            directory, source = _common.resolve_state_dir(self.root)
        finally:
            if original is None:
                _common.os.environ.pop("MR_TRIAGE_DIR", None)
            else:
                _common.os.environ["MR_TRIAGE_DIR"] = original
        self.assertEqual(directory, target)
        self.assertEqual(source, "MR_TRIAGE_DIR")


class StateFileTests(unittest.TestCase):
    def test_roundtrip_and_atomic_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = {"schemaVersion": 1, "items": [{"n": 1, "verdict": "ACCEPT"}]}
            _common.save_state(path, state)
            self.assertEqual(_common.load_state(path), state)
            self.assertFalse((Path(tmp) / "state.json.tmp").exists())

    def test_state_path_is_stable_and_slugged(self):
        path = _common.state_path(Path("/tmp"), "gitlab", "Team/Api", 2340)
        self.assertEqual(path.name, "gitlab-team-api-2340.json")

    def test_missing_state_raises(self):
        with self.assertRaises(_common.ScriptError):
            _common.load_state(Path("/nonexistent/state.json"))


if __name__ == "__main__":
    unittest.main()
