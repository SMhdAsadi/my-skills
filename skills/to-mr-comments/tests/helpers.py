# Shared fixtures for the to-mr-comments tests. Not collected by unittest.

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
for entry in (HERE, SCRIPTS):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

A_TXT = "\n".join(f"line{i}" for i in range(1, 13)) + "\n"


def git(root: Path, *args: str, check: bool = True):
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=check,
    )


def build_repo(root: Path) -> tuple[str, str]:
    """Create a base commit and a feature branch with a mixed diff.

    Feature changes: modified line, inserted line, new file, deleted file, and
    a pure rename. Returns (base_sha, head_sha).
    """
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "a.txt").write_text(A_TXT, encoding="utf-8")
    (root / "gone.txt").write_text("bye\n", encoding="utf-8")
    (root / "old.txt").write_text("old\nname\n", encoding="utf-8")
    (root / ".gitignore").write_text(".state/\n.tmp/\nscratch/\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "base")
    base = git(root, "rev-parse", "HEAD").stdout.strip()

    git(root, "checkout", "-q", "-b", "feat")
    lines = A_TXT.splitlines()
    lines[2] = "L3-changed"
    lines.insert(6, "inserted-line")
    (root / "a.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (root / "new.txt").write_text("n1\nn2\nn3\nn4\n", encoding="utf-8")
    (root / "gone.txt").unlink()
    git(root, "mv", "old.txt", "renamed.txt")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "feat")
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    return base, head


class RepoCase:
    """Mixin for tests that need a throwaway repo, a state dir, and a cwd."""

    def prepare_repo(self, tmp: Path):
        self.root = tmp / "repo"
        self.base, self.head = build_repo(self.root)
        self.state_dir = self.root / ".state"
        self.files = tmp / "files"
        self.files.mkdir()
        self._old_cwd = Path.cwd()
        self._old_dir = os.environ.get("MR_COMMENTS_DIR")
        os.environ["MR_COMMENTS_DIR"] = str(self.state_dir)
        os.chdir(self.root)

    def cleanup_repo(self):
        os.chdir(self._old_cwd)
        if self._old_dir is None:
            os.environ.pop("MR_COMMENTS_DIR", None)
        else:
            os.environ["MR_COMMENTS_DIR"] = self._old_dir

    def init_state(self, iid: int = 7, host: str = "gitlab.example.com") -> Path:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        import comments  # noqa: WPS433

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            comments.main(
                [
                    "init",
                    "--project",
                    "team/api",
                    "--iid",
                    str(iid),
                    "--base",
                    self.base,
                    "--host",
                    host,
                    "--offline",
                ]
            )
        return self.state_dir / f"mr-comments-team-api-{iid}.json"
