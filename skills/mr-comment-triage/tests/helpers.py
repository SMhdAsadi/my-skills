# Shared fixtures for the mr-comment-triage tests. Not collected by unittest.
"""Real temporary git repositories, real state files, mocked subprocess boundary.

The scripts import ``run`` by name, so ``install(module)`` swaps that module's
transport with a fake that delegates ``git`` to the real binary and answers
``glab`` from a script. Nothing here touches the network or needs credentials.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
for entry in (HERE, SCRIPTS):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import _common  # noqa: E402

HOST = "gitlab.example.com"
REPO = "group/api"
NUMBER = 123
HEAD_SHA = "a" * 40
BASE_SHA = "b" * 40

# 12 lines, so evidence citations can be checked at HEAD.
SOURCE = "\n".join(f"value_{line} = {line}" for line in range(1, 13)) + "\n"
SOURCE_PATH = "src/app.py"
SOURCE_LINES = 12


def git(root: Path, *args: str, check: bool = True):
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=check,
    )


def make_item(number: int = 1, **overrides) -> dict:
    """A complete v2 item; tests override only the field under test."""
    item = {
        "n": number,
        "threadIds": [f"gl:d{number}"],
        "verdict": "ACCEPT",
        "severity": "blocking",
        "claim": "The guard is missing.",
        "evidence": [{"path": SOURCE_PATH, "line": 3, "note": "no guard"}],
        "action": "Add the guard.",
        "replyDraft": "Added the guard.",
        "status": "proposed",
        "approvedAt": None,
        "approvalHash": None,
        "commitSha": None,
        "posts": [],
        "orphaned": False,
        "missingThreadIds": [],
        "updatedAt": None,
    }
    item.update(overrides)
    return item


def make_thread(thread_id: str = "gl:d1", **overrides) -> dict:
    thread = {
        "id": thread_id,
        "remoteId": thread_id.removeprefix("gl:"),
        "anchor": {
            "kind": "inline",
            "path": SOURCE_PATH,
            "oldPath": None,
            "line": 3,
            "endLine": None,
            "side": "new",
        },
        "author": "sara",
        "authorKind": "human",
        "body": "This guard is missing.",
        "createdAt": "2026-11-01T10:00:00Z",
        "resolvable": True,
        "resolved": False,
        "stale": False,
        "replies": [],
    }
    thread.update(overrides)
    return thread


class FakeRun:
    """A ``run`` replacement: real git, scripted glab."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self._glab_queue: list[dict] = []
        self._glab_failure: tuple[str, str, int] | None = None

    def add_glab(self, stdout="{}", *, code: int = 0, stderr: str = "") -> None:
        """Queue one scripted glab response."""
        self._glab_queue.append({"stdout": stdout, "code": code, "stderr": stderr})

    def fail_glab(self, stderr: str = "glab: boom", *, code: int = 1) -> None:
        self.add_glab("", code=code, stderr=stderr)

    def fail_on(self, needle: str, stderr: str = "glab: boom", *, code: int = 1) -> None:
        """Fail any glab call whose joined command contains ``needle``."""
        self._glab_failure = (needle, stderr, code)

    @property
    def glab_calls(self) -> list[list[str]]:
        return [call for call in self.calls if call and call[0] == "glab"]

    def __call__(self, cmd, *, cwd=None, check=True, env=None):
        command = list(cmd)
        self.calls.append(command)

        merged_env = None
        if env:
            merged_env = {**os.environ, **env}

        if command and command[0] == "git":
            return subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
                env=merged_env,
            )

        if command and command[0] == "glab":
            joined = " ".join(command)
            if self._glab_failure and self._glab_failure[0] in joined:
                _, stderr, code = self._glab_failure
                scripted = {"stdout": "", "code": code, "stderr": stderr}
            else:
                scripted = (
                    self._glab_queue.pop(0)
                    if self._glab_queue
                    else {"stdout": "{}", "code": 0, "stderr": ""}
                )
            proc = subprocess.CompletedProcess(
                command,
                scripted["code"],
                stdout=scripted["stdout"],
                stderr=scripted["stderr"],
            )
            if check and proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or "").strip().splitlines()[:6]
                raise _common.ScriptError(
                    f"`{' '.join(command[:2])}` failed:\n" + "\n".join(detail)
                )
            return proc

        return subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            env=merged_env,
        )


def fake_run() -> FakeRun:
    return FakeRun()


def install(module, fake: FakeRun) -> FakeRun:
    """Patch ``module.run`` (modules import the shared helper by name)."""
    module.run = fake
    return fake


class Capture:
    """Run a CLI entry point and keep its exit code and streams."""

    def __init__(self) -> None:
        self.code = 0
        self.stdout = ""
        self.stderr = ""

    def __enter__(self) -> "Capture":
        return self

    def __exit__(self, *exc_info) -> None:
        return None

    def run(self, entry, argv=None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = entry(list(argv) if argv is not None else [])
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
            except _common.ScriptError as exc:
                print(f"error: {exc}", file=sys.stderr)
                code = 1
        self.code = code or 0
        self.stdout, self.stderr = out.getvalue(), err.getvalue()
        return self.result()

    def result(self) -> tuple[int, str, str]:
        return self.code, self.stdout, self.stderr


def capture() -> Capture:
    return Capture()


class RepoCase:
    """Mixin: throwaway repo, out-of-tree state dir, restored cwd/env."""

    def setUp(self) -> None:
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.root = self.tmp_path / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "test@example.com")
        git(self.root, "config", "user.name", "Test")
        (self.root / ".gitignore").write_text(".tmp/\nscratch/\n.state/\n", encoding="utf-8")
        source = self.root / SOURCE_PATH
        source.parent.mkdir(parents=True)
        source.write_text(SOURCE, encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-q", "-m", "base")

        self.state_dir = self.tmp_path / "state"
        self.state_dir.mkdir()
        self.state_path = _common.state_path(self.state_dir, REPO, NUMBER)

        self._old_cwd = Path.cwd()
        self._old_triage_dir = os.environ.get("MR_TRIAGE_DIR")
        os.environ["MR_TRIAGE_DIR"] = str(self.state_dir)
        os.chdir(self.root)

        self.fake = fake_run()

    def tearDown(self) -> None:
        os.chdir(self._old_cwd)
        if self._old_triage_dir is None:
            os.environ.pop("MR_TRIAGE_DIR", None)
        else:
            os.environ["MR_TRIAGE_DIR"] = self._old_triage_dir
        self._tmp.cleanup()
        super().tearDown()

    def install(self, module) -> FakeRun:
        return install(module, self.fake)

    def base_state(self, *, threads=None, items=None, **overrides) -> dict:
        state = {
            "schemaVersion": _common.SCHEMA_VERSION,
            "host": HOST,
            "repo": REPO,
            "target": {
                "kind": "mr",
                "number": NUMBER,
                "title": "Test MR",
                "url": f"https://{HOST}/{REPO}/-/merge_requests/{NUMBER}",
                "headSha": HEAD_SHA,
                "baseSha": BASE_SHA,
            },
            "fetchedAt": "2026-11-01T09:00:00Z",
            "warnings": [],
            "threads": threads
            if threads is not None
            else [make_thread("gl:d1"), make_thread("gl:d2")],
            "items": items or [],
            "events": [],
        }
        state.update(overrides)
        return state

    def write_state(self, state: dict | None = None, **overrides) -> Path:
        if state is None:
            state = self.base_state()
        state = json.loads(json.dumps(state))
        state.update(overrides)
        _common.save_state(self.state_path, state)
        return self.state_path

    def read_state(self) -> dict:
        return _common.load_state(self.state_path)


def safe_main(module, argv=None) -> tuple[int, str, str]:
    return capture().run(module.main, argv)
