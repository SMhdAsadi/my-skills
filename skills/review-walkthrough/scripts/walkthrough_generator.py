"""Deterministic generator for review walkthrough deliverables.

Renders both review-walkthrough.md and review-walkthrough.html from a single
validated review-walkthrough.json file in milliseconds.
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
        "gist": "The Gist",
        "heads_up": "Heads Up",
        "reading": "Suggested Reading Order",
        "skim": "Skim:",
        "test": "What to Test",
        "files": "files",
        "check": "Check:",
    },
    "fa": {
        "title_prefix": "راهنمای بررسی:",
        "branch": "برنچ:",
        "affects": "بخش‌های تحت‌تأثیر:",
        "split": "پیشنهاد تفکیک برنچ",
        "gist": "خلاصه تغییرات",
        "heads_up": "نکات حساس و ریسک‌ها",
        "reading": "ترتیب پیشنهادی بررسی",
        "skim": "بررسی گذرا:",
        "test": "مواردی که باید تست شوند",
        "files": "فایل",
        "check": "بررسی کنید:",
    },
    "de": {
        "title_prefix": "Review-Überblick:",
        "branch": "Branch:",
        "affects": "Betrifft:",
        "split": "Aufteilungsempfehlung",
        "gist": "Das Wichtigste",
        "heads_up": "Achtung: Risiken & Fallstricke",
        "reading": "Empfohlene Lesereihenfolge",
        "skim": "Überfliegen:",
        "test": "Was getestet werden sollte",
        "files": "Dateien",
        "check": "Prüfen:",
    },
    "es": {
        "title_prefix": "Guía de Revisión:",
        "branch": "Rama:",
        "affects": "Afecta:",
        "split": "Sugerencia de División",
        "gist": "En Resumen",
        "heads_up": "Puntos Críticos y Riesgos",
        "reading": "Orden de Lectura Sugerido",
        "skim": "Vistazo rápido:",
        "test": "Qué Probar",
        "files": "archivos",
        "check": "Verificar:",
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


def resolve_paths_against_diff(
    data: Dict[str, Any], diff_files: List[str]
) -> Dict[str, Any]:
    """Resolve bare basenames in data to full repo-relative paths found in diff_files."""
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

    # Deep copy or mutate
    data = json.loads(json.dumps(data))
    for step in data.get("steps", []):
        for ref in step.get("refs", []):
            if "path" in ref:
                ref["path"] = resolve(ref["path"])
        for item in step.get("items", []):
            if isinstance(item, dict) and "path" in item:
                item["path"] = resolve(item["path"])
        if "skim" in step and isinstance(step["skim"], list):
            step["skim"] = [resolve(p) for p in step["skim"]]
    return data


def fix_rtl_arrows(text: str, is_rtl: bool) -> str:
    """Normalize progression arrows in RTL text from rightwards to leftwards outside code spans."""
    if not is_rtl or not text:
        return text
    parts = re.split(r"(`[^`]+`)", text)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"[→➔➜]|->", "←", parts[i])
    return "".join(parts)


def render_markdown(data: Dict[str, Any]) -> str:
    """Deterministically render a clean, anti-fatigue Markdown review walkthrough."""
    lang = data.get("lang", "en")
    is_rtl = lang.lower().startswith(("fa", "ar", "he", "ur"))
    labels = get_labels(lang)
    meta = data["meta"]
    stats = meta["stats"]

    n_files = stats["files"]
    if lang.lower().startswith("fa"):
        files_str = f"{to_persian_digits(n_files)} {labels['files']}"
    else:
        files_str = f"{n_files} {labels['files']}"

    # Find step types
    steps_by_kind = {}
    gotchas = []
    for s in data["steps"]:
        k = s["kind"]
        if k == "gotcha":
            gotchas.append(s)
        else:
            steps_by_kind[k] = s

    scope = steps_by_kind.get("scope", {})
    split = steps_by_kind.get("split")
    reading = steps_by_kind.get("reading", {})
    test = steps_by_kind.get("test", {})

    lines: List[str] = []

    # Title & Header
    lines.append(f"# {labels['title_prefix']} {fix_rtl_arrows(meta['title'], is_rtl)}")
    lines.append("")
    lines.append(
        f"**{labels['branch']}** `{meta['branch']}` → `{meta['base']}` • "
        f"**{files_str} (+{stats['added']} / -{stats['removed']})**"
    )
    lines.append(f"**{labels['affects']}** {fix_rtl_arrows(scope.get('affects', ''), is_rtl)}")
    lines.append("")

    # Split Recommendation (if any)
    if split:
        lines.append(f"### {labels['split']}")
        lines.append(fix_rtl_arrows(split.get("recommendation", ""), is_rtl))
        boundaries = split.get("boundaries")
        if boundaries:
            lines.append("")
            for b in boundaries:
                lines.append(f"- {fix_rtl_arrows(b, is_rtl)}")
        lines.append("")

    # The Gist
    lines.append(f"### {labels['gist']}")
    for g in scope.get("gist", []):
        lines.append(fix_rtl_arrows(g, is_rtl))
    lines.append("")

    # Heads Up (Gotchas)
    lines.append(f"### {labels['heads_up']}")
    for gotcha in gotchas:
        refs = gotcha.get("refs", [])
        anchor = format_ref_anchor(refs[0]) if refs else ""
        anchor_part = f" {anchor}" if anchor else ""
        g_title = fix_rtl_arrows(gotcha['title'], is_rtl)
        g_body = fix_rtl_arrows(gotcha['body'], is_rtl)
        lines.append(f"- **{g_title}**{anchor_part}: {g_body}")
        if gotcha.get("lookFor"):
            look_for = fix_rtl_arrows(gotcha['lookFor'], is_rtl)
            lines.append(f"  - *{labels['check']} {look_for}*")
    lines.append("")

    # Suggested Reading Order
    lines.append(f"### {labels['reading']}")
    for item in reading.get("items", []):
        anchor = format_ref_anchor(item)
        role = fix_rtl_arrows(item['role'], is_rtl)
        summary = fix_rtl_arrows(item['summary'], is_rtl)
        lines.append(f"- [ ] **{role}** {anchor}: {summary}")

    skim = reading.get("skim", [])
    if skim:
        skim_str = ", ".join(f"`{s}`" for s in skim)
        # In Persian markdown, use Persian comma
        if lang.lower().startswith("fa"):
            skim_str = "، ".join(f"`{s}`" for s in skim)
        lines.append(f"*{labels['skim']} {skim_str}*")
    lines.append("")

    # What to Test
    lines.append(f"### {labels['test']}")
    for t in test.get("items", []):
        lines.append(f"- [ ] {fix_rtl_arrows(t, is_rtl)}")
    lines.append("")

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
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
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
    Schema v2 validation, Markdown generation, and companion HTML template injection.
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

    # 4. Schema validation
    data = validate_walkthrough(data)

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
        resolved_html_path = Path(html_path).resolve() if html_path else base_dir / f"{stem}.html"

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

    steps = data.get("steps", [])
    gotchas_count = sum(1 for s in steps if s.get("kind") == "gotcha")
    reading_count = sum(len(s.get("items", [])) for s in steps if s.get("kind") == "reading")
    stats_dict = {
        "steps": len(steps),
        "gotchas": gotchas_count,
        "reading_items": reading_count,
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

