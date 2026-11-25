"""Schema definitions and validation engine for review walkthrough data.

Schema Version: 3 (Vertical Slice Architecture)
Enforces structured integrity, clean human prose, and multi-IDE compatibility
without markdown reverse-engineering or arbitrary numeric caps/floors.
"""

import re
from typing import Any, Dict, List

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

VALID_STATUSES = {"modified", "added", "deleted"}

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# Detects parenthesized path prefix like "(Bar.tsx:35):" or "(src/a.ts:1-2):"
LEADING_PATH_PREFIX_RE = re.compile(
    r"^\(\s*[A-Za-z0-9_@.\-/+]+\s*:\s*\d+(?:-\d+)?\s*\)\s*:?"
)


class ValidationError(ValueError):
    """Raised when walkthrough data violates the Schema v3 contract."""

    pass


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def is_safe_path(p: Any) -> bool:
    """Validate that path is repo-relative, non-empty, and free of traversal/control characters.

    Supports extensionless files (Dockerfile, Makefile, LICENSE) and dotfiles (.env).
    """
    if not isinstance(p, str) or not p.strip():
        return False
    if p.startswith("/") or p.startswith("./") or p.startswith("../"):
        return False
    if "\\" in p or any(ord(c) < 32 for c in p):
        return False
    segments = p.split("/")
    if any(s == "" or s == ".." or s == "." for s in segments):
        return False
    return True


def _check_non_empty_str(val: Any, context: str) -> None:
    if not isinstance(val, str) or not val.strip():
        raise ValidationError(f"{context} must be a non-empty string")


def _check_str_list(val: Any, context: str, min_len: int = 0) -> None:
    if not isinstance(val, list) or len(val) < min_len:
        noun = "at least 1 item" if min_len == 1 else f"at least {min_len} items"
        msg = f"{context} must be a list with {noun}" if min_len > 0 else f"{context} must be a list"
        raise ValidationError(msg)
    for idx, item in enumerate(val):
        _check_non_empty_str(item, f"{context}[{idx}]")


def _check_pure_prose(text: str, context: str) -> None:
    """Ensure body or summary does not start with a parenthesized file:line prefix."""
    if LEADING_PATH_PREFIX_RE.search(text.strip()):
        raise ValidationError(
            f"{context} must be pure prose without leading parenthesized path prefixes. "
            f"Found: {text[:60]!r}"
        )


def _check_ref(ref: Any, context: str) -> None:
    if not isinstance(ref, dict):
        raise ValidationError(f"{context} must be a dictionary")
    path = ref.get("path")
    if not is_safe_path(path):
        raise ValidationError(
            f"{context}.path must be a safe, repo-relative path, got: {path!r}"
        )
    start_line = ref.get("startLine")
    if not _is_int(start_line) or start_line < 1:
        raise ValidationError(
            f"{context}.startLine must be an integer >= 1, got: {start_line!r}"
        )
    end_line = ref.get("endLine")
    if end_line is not None:
        if not _is_int(end_line) or end_line < start_line:
            raise ValidationError(
                f"{context}.endLine must be an integer >= startLine ({start_line}), got: {end_line!r}"
            )
    status = ref.get("status")
    if status is not None and status not in VALID_STATUSES:
        raise ValidationError(
            f"{context}.status must be one of {sorted(VALID_STATUSES)}, got: {status!r}"
        )


def _check_heads_up(hu: Any, context: str, *, require_refs: bool) -> None:
    if not isinstance(hu, dict):
        raise ValidationError(f"{context} must be a dictionary")

    _check_non_empty_str(hu.get("title"), f"{context}.title")
    body = hu.get("body")
    _check_non_empty_str(body, f"{context}.body")
    _check_pure_prose(body, f"{context}.body")

    refs = hu.get("refs")
    if require_refs:
        if not isinstance(refs, list) or len(refs) < 1:
            raise ValidationError(f"{context}.refs must be a list of at least 1 file reference")
    elif refs is not None and not isinstance(refs, list):
        raise ValidationError(f"{context}.refs must be a list if provided")

    if isinstance(refs, list):
        for j, r in enumerate(refs):
            _check_ref(r, f"{context}.refs[{j}]")

    extra = hu.get("extra")
    if extra is not None:
        _check_str_list(extra, f"{context}.extra", min_len=0)

    look_for = hu.get("lookFor")
    if look_for is not None:
        _check_non_empty_str(look_for, f"{context}.lookFor")


def validate_walkthrough(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a walkthrough dictionary against the Schema v3 contract.

    This is the build-time mirror of ``check(d)`` in
    ``assets/walkthrough-template.html``. When a rule changes,
    update both this function and the runtime ``check(d)`` together.

    Returns the validated data dictionary or raises ValidationError.
    """
    if not isinstance(data, dict):
        raise ValidationError("Walkthrough root must be a dictionary")

    version = data.get("schemaVersion")
    if not _is_int(version) or version != 3:
        raise ValidationError(
            f"Unsupported schemaVersion: {version!r}. Expected 3"
        )

    lang = data.get("lang")
    _check_non_empty_str(lang, "lang")

    # Meta validation
    meta = data.get("meta")
    if not isinstance(meta, dict):
        raise ValidationError("meta must be a dictionary")
    for key in ("title", "branch", "base", "headSha"):
        _check_non_empty_str(meta.get(key), f"meta.{key}")

    md_path = meta.get("markdownPath")
    if md_path is not None:
        _check_non_empty_str(md_path, "meta.markdownPath")

    stats = meta.get("stats")
    if not isinstance(stats, dict):
        raise ValidationError("meta.stats must be a dictionary")
    for k in ("files", "added", "removed"):
        val = stats.get(k)
        if not _is_int(val) or val < 0:
            raise ValidationError(
                f"meta.stats.{k} must be an integer >= 0, got: {val!r}"
            )

    # Repo validation
    repo = data.get("repo")
    if repo is not None:
        if not isinstance(repo, dict):
            raise ValidationError("repo must be a dictionary if present")
        if "defaultEditor" in repo and repo["defaultEditor"] is not None:
            editor = repo["defaultEditor"]
        else:
            editor = repo.get("editor")
        if editor is not None and editor not in VALID_EDITORS:
            raise ValidationError(
                f"repo.defaultEditor must be one of {sorted(VALID_EDITORS)}, got: {editor!r}"
            )

    # Overview validation
    overview = data.get("overview")
    if not isinstance(overview, dict):
        raise ValidationError("overview must be a dictionary")
    _check_non_empty_str(overview.get("title"), "overview.title")
    _check_non_empty_str(overview.get("affects"), "overview.affects")

    ov_summary = overview.get("summary")
    if ov_summary is not None:
        _check_str_list(ov_summary, "overview.summary", min_len=0)

    split = overview.get("split")
    if split is not None:
        if not isinstance(split, dict):
            raise ValidationError("overview.split must be a dictionary if present")
        _check_non_empty_str(split.get("recommendation"), "overview.split.recommendation")
        boundaries = split.get("boundaries")
        if boundaries is not None:
            _check_str_list(boundaries, "overview.split.boundaries", min_len=0)

    skim = overview.get("skim")
    if skim is not None:
        if not isinstance(skim, list) or any(not is_safe_path(p) for p in skim):
            raise ValidationError(
                "overview.skim must be a list of safe repo-relative paths"
            )

    # Slices validation
    slices = data.get("slices")
    if not isinstance(slices, list) or len(slices) < 1:
        raise ValidationError("slices must be a list with at least 1 slice")

    seen_ids = set()
    for i, sl in enumerate(slices):
        ctx = f"slices[{i}]"
        if not isinstance(sl, dict):
            raise ValidationError(f"{ctx} must be a dictionary")

        slice_id = sl.get("id")
        if (
            not isinstance(slice_id, str)
            or not SLUG_RE.match(slice_id)
            or slice_id in seen_ids
        ):
            raise ValidationError(
                f"{ctx}.id must be a unique kebab-case slug, got: {slice_id!r}"
            )
        seen_ids.add(slice_id)

        _check_non_empty_str(sl.get("title"), f"{ctx}.title")
        _check_str_list(sl.get("summary"), f"{ctx}.summary", min_len=1)

        files = sl.get("files")
        if not isinstance(files, list) or len(files) < 1:
            raise ValidationError(
                f"{ctx}.files must be a list with at least 1 reading item"
            )
        for j, item in enumerate(files):
            fctx = f"{ctx}.files[{j}]"
            if not isinstance(item, dict):
                raise ValidationError(f"{fctx} must be a dictionary")
            _check_non_empty_str(item.get("role"), f"{fctx}.role")
            summary = item.get("summary")
            _check_non_empty_str(summary, f"{fctx}.summary")
            _check_pure_prose(summary, f"{fctx}.summary")
            _check_ref(item, fctx)

        heads_up = sl.get("headsUp")
        if heads_up is not None:
            if not isinstance(heads_up, list):
                raise ValidationError(f"{ctx}.headsUp must be a list if provided")
            for j, hu in enumerate(heads_up):
                _check_heads_up(hu, f"{ctx}.headsUp[{j}]", require_refs=True)

        qa = sl.get("qa")
        if qa is not None:
            _check_str_list(qa, f"{ctx}.qa", min_len=0)

    # Optional Cross-Cutting validation
    cc = data.get("crossCutting")
    if cc is not None:
        if not isinstance(cc, dict):
            raise ValidationError("crossCutting must be a dictionary if present")
        cc_title = cc.get("title")
        if cc_title is not None:
            _check_non_empty_str(cc_title, "crossCutting.title")

        cc_hu = cc.get("headsUp")
        if cc_hu is not None:
            if not isinstance(cc_hu, list):
                raise ValidationError("crossCutting.headsUp must be a list if provided")
            for j, hu in enumerate(cc_hu):
                _check_heads_up(
                    hu, f"crossCutting.headsUp[{j}]", require_refs=False
                )

        cc_qa = cc.get("qa")
        if cc_qa is not None:
            _check_str_list(cc_qa, "crossCutting.qa", min_len=0)

        total_cc_items = len(cc_hu or []) + len(cc_qa or [])
        if total_cc_items < 1:
            raise ValidationError(
                "crossCutting must contain at least one item in headsUp or qa"
            )

    return data
