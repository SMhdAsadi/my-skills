"""Schema definitions and validation engine for review walkthrough data.

Schema Version: 2
Enforces structured integrity, clean human prose, and multi-IDE compatibility
without markdown reverse-engineering.
"""

import re
from typing import Any, Dict, List

TITLE_MAX = 160
ROLE_MAX = 80

VALID_EDITORS = {
    "vscode",
    "vscode-insiders",
    "cursor",
    "windsurf",
    "vscodium",
    "zed",
    "idea",
    "goland",
    "android-studio",
    "studio",
    "webstorm",
    "pycharm",
    "copy",
}

VALID_CATEGORIES = {
    "edge-case",
    "state",
    "layout",
    "concurrency",
    "persistence",
    "other",
}

VALID_STATUSES = {"modified", "added", "deleted"}

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# Detects parenthesized path prefix like "(Bar.tsx:35):" or "(src/a.ts:1-2):"
LEADING_PATH_PREFIX_RE = re.compile(
    r"^\(\s*[A-Za-z0-9_@.\-/+]+\s*:\s*\d+(?:-\d+)?\s*\)\s*:?"
)


class ValidationError(ValueError):
    """Raised when walkthrough data violates the Schema v2 contract."""

    pass


def is_safe_path(p: Any) -> bool:
    """Validate that path is repo-relative, non-empty, and free of traversal/control characters.

    Supports extensionless files (Dockerfile, Makefile, LICENSE) and dotfiles (.env).
    """
    if not isinstance(p, str) or not p.strip():
        return False
    # No absolute paths or explicit ./ prefixes
    if p.startswith("/") or p.startswith("./") or p.startswith("../"):
        return False
    # No backslashes or control characters
    if "\\" in p or any(ord(c) < 32 for c in p):
        return False
    # No empty segments, root relative traversal, or ..
    segments = p.split("/")
    if any(s == "" or s == ".." or s == "." for s in segments):
        return False
    return True


def _check_pure_prose(text: str, context: str) -> None:
    """Ensure body or summary does not start with a parenthesized file:line prefix."""
    if LEADING_PATH_PREFIX_RE.search(text.strip()):
        raise ValidationError(
            f"{context} must be pure prose without leading parenthesized path prefixes. "
            f"Found: {text[:60]!r}"
        )


def _check_ref(ref: Dict[str, Any], context: str) -> None:
    if not isinstance(ref, dict):
        raise ValidationError(f"{context} must be a dictionary")
    path = ref.get("path")
    if not is_safe_path(path):
        raise ValidationError(
            f"{context}.path must be a safe, repo-relative path, got: {path!r}"
        )
    start_line = ref.get("startLine")
    if not isinstance(start_line, int) or start_line < 1:
        raise ValidationError(
            f"{context}.startLine must be an integer >= 1, got: {start_line!r}"
        )
    end_line = ref.get("endLine")
    if end_line is not None:
        if not isinstance(end_line, int) or end_line < start_line:
            raise ValidationError(
                f"{context}.endLine must be an integer >= startLine ({start_line}), got: {end_line!r}"
            )
    status = ref.get("status")
    if status is not None and status not in VALID_STATUSES:
        raise ValidationError(
            f"{context}.status must be one of {sorted(VALID_STATUSES)}, got: {status!r}"
        )


def validate_walkthrough(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a walkthrough dictionary against the Schema v2 contract.

    Returns the validated data dictionary or raises ValidationError.
    """
    if not isinstance(data, dict):
        raise ValidationError("Walkthrough root must be a dictionary")

    version = data.get("schemaVersion")
    if version not in (1, 2):
        raise ValidationError(
            f"Unsupported schemaVersion: {version!r}. Expected 1 or 2"
        )

    lang = data.get("lang")
    if not isinstance(lang, str) or not lang.strip():
        raise ValidationError(f"lang must be a non-empty string, got: {lang!r}")

    # Meta validation
    meta = data.get("meta")
    if not isinstance(meta, dict):
        raise ValidationError("meta must be a dictionary")
    for key in ("title", "branch", "base", "headSha"):
        val = meta.get(key)
        if not isinstance(val, str) or not val.strip():
            raise ValidationError(f"meta.{key} must be a non-empty string")
    if len(meta["title"]) > TITLE_MAX:
        raise ValidationError(
            f"meta.title must be <= {TITLE_MAX} characters, got {len(meta['title'])}"
        )

    stats = meta.get("stats")
    if not isinstance(stats, dict):
        raise ValidationError("meta.stats must be a dictionary")
    for k in ("files", "added", "removed"):
        val = stats.get(k)
        if not isinstance(val, int) or val < 0:
            raise ValidationError(
                f"meta.stats.{k} must be an integer >= 0, got: {val!r}"
            )

    # Repo validation
    repo = data.get("repo")
    if repo is not None:
        if not isinstance(repo, dict):
            raise ValidationError("repo must be a dictionary if present")
        editor = repo.get("defaultEditor") or repo.get("editor")
        if editor is not None and editor not in VALID_EDITORS:
            raise ValidationError(
                f"repo.defaultEditor must be one of {sorted(VALID_EDITORS)}, got: {editor!r}"
            )

    # Steps validation
    steps = data.get("steps")
    if not isinstance(steps, list) or len(steps) < 3:
        raise ValidationError(
            f"steps must be a list of at least 3 items, got: {len(steps) if isinstance(steps, list) else type(steps)}"
        )

    seen_ids = set()
    kinds = []

    for i, step in enumerate(steps):
        ctx = f"steps[{i}]"
        if not isinstance(step, dict):
            raise ValidationError(f"{ctx} must be a dictionary")

        step_id = step.get("id")
        if (
            not isinstance(step_id, str)
            or not SLUG_RE.match(step_id)
            or step_id in seen_ids
        ):
            raise ValidationError(
                f"{ctx}.id must be a unique kebab-case slug, got: {step_id!r}"
            )
        seen_ids.add(step_id)

        kind = step.get("kind")
        if kind not in ("scope", "split", "gotcha", "reading", "test"):
            raise ValidationError(f"{ctx}.kind is invalid: {kind!r}")
        kinds.append(kind)

        section = step.get("section")
        if not isinstance(section, str) or not section.strip():
            raise ValidationError(f"{ctx}.section must be a non-empty string")

        title = step.get("title")
        if (
            not isinstance(title, str)
            or not title.strip()
            or len(title) > TITLE_MAX
        ):
            raise ValidationError(
                f"{ctx}.title must be a non-empty string <= {TITLE_MAX} characters"
            )

        if kind == "scope":
            if i != 0:
                raise ValidationError(f"{ctx}: scope step must always be first")
            gist = step.get("gist")
            if (
                not isinstance(gist, list)
                or not (1 <= len(gist) <= 3)
                or any(not isinstance(s, str) or not s.strip() for s in gist)
            ):
                raise ValidationError(
                    f"{ctx}.gist must be an array of 1 to 3 non-empty strings"
                )
            affects = step.get("affects")
            if not isinstance(affects, str) or not affects.strip():
                raise ValidationError(
                    f"{ctx}.affects must be a non-empty string"
                )

        elif kind == "split":
            if i != 1:
                raise ValidationError(
                    f"{ctx}: split step must directly follow scope (index 1)"
                )
            rec = step.get("recommendation")
            if not isinstance(rec, str) or not rec.strip():
                raise ValidationError(
                    f"{ctx}.recommendation must be a non-empty string"
                )
            boundaries = step.get("boundaries")
            if boundaries is not None:
                if not isinstance(boundaries, list) or any(
                    not isinstance(b, str) or not b.strip() for b in boundaries
                ):
                    raise ValidationError(
                        f"{ctx}.boundaries must be a list of non-empty strings"
                    )

        elif kind == "gotcha":
            cat = step.get("category")
            if cat not in VALID_CATEGORIES:
                raise ValidationError(
                    f"{ctx}.category must be one of {sorted(VALID_CATEGORIES)}, got: {cat!r}"
                )
            body = step.get("body")
            if not isinstance(body, str) or not body.strip():
                raise ValidationError(f"{ctx}.body must be a non-empty string")
            _check_pure_prose(body, f"{ctx}.body")

            refs = step.get("refs")
            if not isinstance(refs, list) or not (1 <= len(refs) <= 3):
                raise ValidationError(
                    f"{ctx}.refs must be a list of 1 to 3 file references"
                )
            for j, r in enumerate(refs):
                _check_ref(r, f"{ctx}.refs[{j}]")

            look_for = step.get("lookFor")
            if look_for is not None and (
                not isinstance(look_for, str) or not look_for.strip()
            ):
                raise ValidationError(
                    f"{ctx}.lookFor must be a non-empty string if provided"
                )

        elif kind == "reading":
            items = step.get("items")
            if not isinstance(items, list) or len(items) < 1:
                raise ValidationError(
                    f"{ctx}.items must be a list with at least 1 reading item"
                )
            for j, item in enumerate(items):
                ictx = f"{ctx}.items[{j}]"
                if not isinstance(item, dict):
                    raise ValidationError(f"{ictx} must be a dictionary")
                role = item.get("role")
                if (
                    not isinstance(role, str)
                    or not role.strip()
                    or len(role) > ROLE_MAX
                ):
                    raise ValidationError(
                        f"{ictx}.role must be a non-empty string <= {ROLE_MAX} chars"
                    )
                summary = item.get("summary")
                if not isinstance(summary, str) or not summary.strip():
                    raise ValidationError(
                        f"{ictx}.summary must be a non-empty string"
                    )
                _check_pure_prose(summary, f"{ictx}.summary")
                _check_ref(item, ictx)

            skim = step.get("skim")
            if skim is not None:
                if not isinstance(skim, list) or any(
                    not is_safe_path(p) for p in skim
                ):
                    raise ValidationError(
                        f"{ctx}.skim must be a list of safe repo-relative paths"
                    )

        elif kind == "test":
            if i != len(steps) - 1:
                raise ValidationError(f"{ctx}: test step must always be last")
            test_items = step.get("items")
            if (
                not isinstance(test_items, list)
                or not (2 <= len(test_items) <= 5)
                or any(
                    not isinstance(t, str) or not t.strip() for t in test_items
                )
            ):
                raise ValidationError(
                    f"{ctx}.items must be a list of 2 to 5 practical test verification strings"
                )

    # Invariant counts and relative positions
    if kinds.count("scope") != 1:
        raise ValidationError("Walkthrough must have exactly one scope step")
    if kinds.count("reading") != 1:
        raise ValidationError("Walkthrough must have exactly one reading step")
    if kinds.count("test") != 1:
        raise ValidationError("Walkthrough must have exactly one test step")
    if kinds.count("split") > 1:
        raise ValidationError("Walkthrough can have at most one split step")
    gotcha_count = kinds.count("gotcha")
    if not (1 <= gotcha_count <= 4):
        raise ValidationError(
            f"Walkthrough must have 1 to 4 gotchas, found {gotcha_count}"
        )

    reading_idx = kinds.index("reading")
    last_gotcha_idx = max(i for i, k in enumerate(kinds) if k == "gotcha")
    if reading_idx < last_gotcha_idx:
        raise ValidationError(
            "Reading order step must follow all gotcha steps"
        )

    return data
