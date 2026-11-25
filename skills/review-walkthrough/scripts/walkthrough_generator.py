"""Deterministic generator for review walkthrough deliverables.

Renders both review-walkthrough.md and review-walkthrough.html from a single
validated Schema v3 review-walkthrough.json file in milliseconds.
"""

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from walkthrough_schema import ValidationError, validate_walkthrough

HERE = Path(__file__).resolve().parent
DEFAULT_TEMPLATE_PATH = HERE.parent / "assets" / "walkthrough-template.html"


class CompileError(Exception):
    """Raised when walkthrough compilation cannot proceed."""

    pass


@dataclass
class CompileResult:
    """Outcome of compiling a review walkthrough."""

    markdown: str
    html: str
    data: Dict[str, Any]
    stats: Dict[str, Any]
    md_path: Optional[Path] = None
    html_path: Optional[Path] = None
    elapsed_ms: float = 0.0


DATA_BLOCK_RE = re.compile(
    r'(<script\s+type="application/json"\s+id="walkthrough-data">)(.*?)(</script>)',
    re.DOTALL,
)

LOCALIZED_LABELS = {
    "en": {
        "title_prefix": "Review Walkthrough:",
        "branch": "Branch:",
        "affects": "Affects:",
        "split": "Split Recommendation",
        "overview": "Overview",
        "heads_up": "Heads Up",
        "files_section": "Files",
        "skim": "Skim",
        "test": "What to Test",
        "files": "files",
        "file_singular": "file",
        "check": "Check:",
        "cross_cutting": "Cross-Cutting",
    },
    "fa": {
        "title_prefix": "راهنمای بررسی:",
        "branch": "برنچ:",
        "affects": "بخش‌های تحت‌تأثیر:",
        "split": "پیشنهاد تفکیک برنچ",
        "overview": "خلاصه تغییرات",
        "heads_up": "نکات حساس و ریسک‌ها",
        "files_section": "فایل‌ها",
        "skim": "بررسی گذرا",
        "test": "مواردی که باید تست شوند",
        "files": "فایل",
        "file_singular": "فایل",
        "check": "بررسی کنید:",
        "cross_cutting": "نکات مشترک بین بخش‌ها",
    },
    "de": {
        "title_prefix": "Review-Überblick:",
        "branch": "Branch:",
        "affects": "Betrifft:",
        "split": "Aufteilungsempfehlung",
        "overview": "Überblick",
        "heads_up": "Achtung: Risiken & Fallstricke",
        "files_section": "Dateien",
        "skim": "Überfliegen",
        "test": "Was getestet werden sollte",
        "files": "Dateien",
        "file_singular": "Datei",
        "check": "Prüfen:",
        "cross_cutting": "Übergreifend",
    },
    "es": {
        "title_prefix": "Guía de Revisión:",
        "branch": "Rama:",
        "affects": "Afecta:",
        "split": "Sugerencia de División",
        "overview": "Resumen",
        "heads_up": "Puntos Críticos y Riesgos",
        "files_section": "Archivos",
        "skim": "Vistazo rápido",
        "test": "Qué Probar",
        "files": "archivos",
        "file_singular": "archivo",
        "check": "Verificar:",
        "cross_cutting": "Aspectos Transversales",
    },
}

PERSIAN_DIGITS_TRANS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def to_persian_digits(n: int) -> str:
    return str(n).translate(PERSIAN_DIGITS_TRANS)


def get_labels(lang: str) -> Dict[str, str]:
    base = (lang or "en").split("-")[0].lower()
    return LOCALIZED_LABELS.get(base, LOCALIZED_LABELS["en"])


def format_ref_anchor(ref: Dict[str, Any]) -> str:
    path = ref["path"]
    start = ref["startLine"]
    end = ref.get("endLine")
    loc = f"{path}:{start}-{end}" if (end and end != start) else f"{path}:{start}"
    return f"([{loc}](#))"


def _resolve_heads_up_refs(hu_list: Any, resolve: Any) -> None:
    for hu in hu_list or []:
        if isinstance(hu, dict):
            for ref in hu.get("refs") or []:
                if isinstance(ref, dict) and isinstance(ref.get("path"), str):
                    ref["path"] = resolve(ref["path"])


def resolve_paths_against_diff(
    data: Dict[str, Any], diff_files: List[str]
) -> Dict[str, Any]:
    """Resolve bare basenames in Schema v3 data to full repo-relative paths found in diff_files."""
    if not diff_files:
        return data

    by_basename: Dict[str, List[str]] = {}
    for f in diff_files:
        f = f.strip()
        if f:
            base = f.rsplit("/", 1)[-1]
            by_basename.setdefault(base, []).append(f)

    def resolve(path: str) -> str:
        if "/" in path:
            return path
        matches = by_basename.get(path, [])
        return matches[0] if len(matches) == 1 else path

    data = json.loads(json.dumps(data))

    overview = data.get("overview")
    if isinstance(overview, dict) and isinstance(overview.get("skim"), list):
        overview["skim"] = [
            resolve(p) if isinstance(p, str) else p for p in overview["skim"]
        ]

    slices = data.get("slices")
    if isinstance(slices, list):
        for sl in slices:
            if not isinstance(sl, dict):
                continue
            for item in sl.get("files") or []:
                if isinstance(item, dict) and isinstance(item.get("path"), str):
                    item["path"] = resolve(item["path"])
            _resolve_heads_up_refs(sl.get("headsUp"), resolve)

    cc = data.get("crossCutting")
    if isinstance(cc, dict):
        _resolve_heads_up_refs(cc.get("headsUp"), resolve)

    return data


def fix_rtl_arrows(text: str, is_rtl: bool) -> str:
    """Normalize progression arrows in RTL text from rightwards to leftwards outside code spans."""
    if not is_rtl or not text:
        return text
    parts = re.split(r"(`[^`]+`)", text)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"[→➔➜]|->", "←", parts[i])
    return "".join(parts)


def _render_heads_up_items(
    lines: List[str], heads_up: List[Dict[str, Any]], labels: Dict[str, str], is_rtl: bool
) -> None:
    for hu in heads_up:
        refs = hu.get("refs") or []
        anchor_part = (
            " " + " ".join(format_ref_anchor(r) for r in refs) if refs else ""
        )
        h_title = fix_rtl_arrows(hu["title"], is_rtl)
        h_body = fix_rtl_arrows(hu["body"], is_rtl)
        lines.append(f"- **{h_title}**{anchor_part}: {h_body}")
        for extra_p in hu.get("extra") or []:
            lines.append(f"  - {fix_rtl_arrows(extra_p, is_rtl)}")
        if hu.get("lookFor"):
            look_for = fix_rtl_arrows(hu["lookFor"], is_rtl)
            lines.append(f"  - *{labels['check']} {look_for}*")


def _render_heads_up_and_qa(
    lines: List[str], section: Dict[str, Any], labels: Dict[str, str], is_rtl: bool
) -> None:
    heads_up = section.get("headsUp") or []
    if heads_up:
        lines.append(f"### {labels['heads_up']}")
        _render_heads_up_items(lines, heads_up, labels, is_rtl)
        lines.append("")

    qa = section.get("qa") or []
    if qa:
        lines.append(f"### {labels['test']}")
        for t in qa:
            lines.append(f"- [ ] {fix_rtl_arrows(t, is_rtl)}")
        lines.append("")


def render_markdown(data: Dict[str, Any]) -> str:
    """Deterministically render a vertical, anti-fatigue Markdown review walkthrough."""
    lang = data.get("lang", "en")
    base_lang = (lang or "en").split("-")[0].lower()
    is_fa = base_lang == "fa"
    is_rtl = base_lang in {"fa", "ar", "he", "ur", "ps", "ku", "yi", "dv"}
    labels = get_labels(lang)
    meta = data["meta"]
    stats = meta["stats"]
    overview = data["overview"]

    n_files = stats["files"]
    if is_fa:
        files_str = f"{to_persian_digits(n_files)} {labels['files']}"
    else:
        unit = labels["file_singular"] if n_files == 1 else labels["files"]
        files_str = f"{n_files} {unit}"

    lines: List[str] = []

    # Header
    branch_arrow = "←" if is_rtl else "→"
    lines.append(f"# {labels['title_prefix']} {fix_rtl_arrows(meta['title'], is_rtl)}")
    lines.append("")
    lines.append(
        f"**{labels['branch']}** `{meta['branch']}` {branch_arrow} `{meta['base']}` • "
        f"**{files_str} (+{stats['added']} / -{stats['removed']})**"
    )
    lines.append(
        f"**{labels['affects']}** {fix_rtl_arrows(overview.get('affects', ''), is_rtl)}"
    )
    lines.append("")

    # Overview optional Split Recommendation
    split = overview.get("split")
    if split:
        lines.append(f"### {labels['split']}")
        lines.append(fix_rtl_arrows(split.get("recommendation", ""), is_rtl))
        boundaries = split.get("boundaries") or []
        if boundaries:
            lines.append("")
            for b in boundaries:
                lines.append(f"- {fix_rtl_arrows(b, is_rtl)}")
        lines.append("")

    # Overview optional summary
    ov_summary = overview.get("summary") or []
    if ov_summary:
        lines.append(f"### {labels['overview']}")
        for idx_p, p in enumerate(ov_summary):
            if idx_p > 0:
                lines.append("")
            lines.append(fix_rtl_arrows(p, is_rtl))
        lines.append("")

    # Overview optional collapsed Skim List
    skim = overview.get("skim") or []
    if skim:
        skim_count = to_persian_digits(len(skim)) if is_fa else str(len(skim))
        skim_unit = labels["file_singular"] if len(skim) == 1 else labels["files"]
        lines.append("<details>")
        lines.append(f"<summary>{labels['skim']} ({skim_count} {skim_unit})</summary>")
        lines.append("")
        for s in skim:
            lines.append(f"- `{s}`")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    # Numbered Vertical Slices
    for slice_num, sl in enumerate(data["slices"], 1):
        lines.append(f"## {slice_num}. {fix_rtl_arrows(sl['title'], is_rtl)}")
        lines.append("")
        for idx_p, p in enumerate(sl["summary"]):
            if idx_p > 0:
                lines.append("")
            lines.append(fix_rtl_arrows(p, is_rtl))
        lines.append("")

        # Files checklist
        lines.append(f"### {labels['files_section']}")
        for item in sl["files"]:
            anchor = format_ref_anchor(item)
            role = fix_rtl_arrows(item["role"], is_rtl)
            summary = fix_rtl_arrows(item["summary"], is_rtl)
            lines.append(f"- [ ] **{role}** {anchor}: {summary}")
        lines.append("")

        _render_heads_up_and_qa(lines, sl, labels, is_rtl)

    # Optional Cross-Cutting section
    cc = data.get("crossCutting")
    if cc:
        cc_title = cc.get("title") or labels["cross_cutting"]
        lines.append(f"## {fix_rtl_arrows(cc_title, is_rtl)}")
        lines.append("")
        _render_heads_up_and_qa(lines, cc, labels, is_rtl)

    return "\n".join(lines).strip() + "\n"


def render_html(data: Dict[str, Any], template_html: str) -> str:
    """Inject JSON payload into the HTML companion template safely."""
    payload = (
        json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    if not DATA_BLOCK_RE.search(template_html):
        raise ValueError("HTML template missing #walkthrough-data script block")

    return DATA_BLOCK_RE.sub(
        lambda m: m.group(1) + payload + m.group(3), template_html, count=1
    )


def _git(root: str, *args: str) -> str:
    """Internal Git execution helper behind the compiler seam."""
    try:
        cmd = ["git"]
        if root:
            cmd.extend(["-C", root])
        cmd.extend(args)
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def compile_walkthrough(
    spec: Union[Dict[str, Any], str, Path],
    *,
    out_dir: Optional[Union[str, Path]] = None,
    md_path: Optional[Union[str, Path]] = None,
    html_path: Optional[Union[str, Path]] = None,
    editor: Optional[str] = None,
    lang: Optional[str] = None,
    base_ref: Optional[str] = None,
    diff_files: Optional[List[str]] = None,
    template_path: Optional[Union[str, Path]] = None,
    write_files: Optional[bool] = None,
) -> CompileResult:
    """Compile a review walkthrough specification into Markdown and HTML deliverables.

    Encapsulates input ingestion, Git context enrichment, diff path resolution,
    Schema v3 validation, vertical Markdown generation, and companion HTML template injection.
    """
    start_time = time.perf_counter()

    # 1. Load data from dict, JSON file, or JSON string
    input_file_path: Optional[Path] = None
    if isinstance(spec, (str, Path)):
        p = Path(spec)
        if p.exists() and p.is_file():
            input_file_path = p.resolve()
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                raise CompileError(f"Invalid JSON in {p}: {e}") from e
        else:
            try:
                data = json.loads(str(spec))
            except json.JSONDecodeError:
                raise CompileError(f"Walkthrough file not found: {spec}")
    elif isinstance(spec, dict):
        data = json.loads(json.dumps(spec))
    else:
        raise CompileError(f"Unsupported spec type: {type(spec)}")

    if not isinstance(data, dict):
        raise CompileError("Walkthrough data must be a dictionary")

    if lang:
        data["lang"] = lang

    meta = data.setdefault("meta", {})
    repo = data.setdefault("repo", {})

    if editor:
        repo["defaultEditor"] = editor

    # 2. Git enrichment if missing and root exists
    repo_root = repo.get("root") or _git("", "rev-parse", "--show-toplevel")
    if repo_root:
        repo_root = os.path.abspath(os.path.expanduser(repo_root))
        repo["root"] = repo_root

    if not meta.get("headSha") or meta.get("headSha") == "HEAD":
        head = _git(repo_root, "rev-parse", "--short", "HEAD") if repo_root else ""
        if head:
            meta["headSha"] = head

    # 3. Diff-aware path resolution
    base = base_ref or meta.get("base")
    if diff_files is not None:
        data = resolve_paths_against_diff(data, diff_files)
    elif repo_root and base:
        diff_out = _git(repo_root, "diff", "--name-only", f"{base}...HEAD")
        if not diff_out:
            diff_out = _git(repo_root, "diff", "--name-only", base)
        if diff_out:
            resolved_diff_files = diff_out.splitlines()
            data = resolve_paths_against_diff(data, resolved_diff_files)

    # 4. Schema validation (fail fast before either deliverable is rendered)
    try:
        data = validate_walkthrough(data)
    except ValidationError as e:
        if input_file_path:
            raise ValidationError(f"{input_file_path}: {e}") from e
        raise

    # 5. Determine if files should be written and target paths
    should_write = write_files
    if should_write is None:
        should_write = bool(out_dir or md_path or html_path or input_file_path)

    resolved_md_path: Optional[Path] = None
    resolved_html_path: Optional[Path] = None

    if should_write:
        stem = "review-walkthrough"
        if input_file_path:
            base_dir = Path(out_dir).resolve() if out_dir else input_file_path.parent
            stem = input_file_path.stem
            if stem.endswith(".json"):
                stem = stem[:-5]
        else:
            base_dir = Path(out_dir).resolve() if out_dir else Path.cwd()

        resolved_md_path = Path(md_path).resolve() if md_path else base_dir / f"{stem}.md"
        resolved_html_path = (
            Path(html_path).resolve() if html_path else base_dir / f"{stem}.html"
        )

        data["meta"]["markdownPath"] = str(resolved_md_path)

    # 6. Render Markdown
    md_content = render_markdown(data)

    # 7. Render HTML
    tpl = Path(template_path) if template_path else DEFAULT_TEMPLATE_PATH
    if not tpl.exists():
        raise CompileError(f"HTML template not found: {tpl}")
    try:
        template_content = tpl.read_text(encoding="utf-8")
        html_content = render_html(data, template_content)
    except Exception as e:
        if isinstance(e, CompileError):
            raise
        raise CompileError(f"Error rendering HTML companion: {e}") from e

    # 8. Write files if requested
    if should_write and resolved_md_path and resolved_html_path:
        resolved_md_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_md_path.write_text(md_content, encoding="utf-8")
        resolved_html_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_html_path.write_text(html_content, encoding="utf-8")

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    slices = data.get("slices", [])
    cc = data.get("crossCutting") or {}
    heads_up_count = sum(len(s.get("headsUp") or []) for s in slices) + len(
        cc.get("headsUp") or []
    )
    files_count = sum(len(s.get("files", [])) for s in slices)
    qa_count = sum(len(s.get("qa") or []) for s in slices) + len(cc.get("qa") or [])

    stats_dict = {
        "slices": len(slices),
        "heads_up": heads_up_count,
        "files": files_count,
        "qa_items": qa_count,
        "elapsed_ms": elapsed_ms,
    }

    return CompileResult(
        markdown=md_content,
        html=html_content,
        data=data,
        stats=stats_dict,
        md_path=resolved_md_path,
        html_path=resolved_html_path,
        elapsed_ms=elapsed_ms,
    )
