"""Deterministic generator for review walkthrough deliverables.

Renders both review-walkthrough.md and review-walkthrough.html from a single
validated review-walkthrough.json file in milliseconds.
"""

import json
import re
from typing import Any, Dict, List, Optional

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


def render_markdown(data: Dict[str, Any]) -> str:
    """Deterministically render a clean, anti-fatigue Markdown review walkthrough."""
    lang = data.get("lang", "en")
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
    lines.append(f"# {labels['title_prefix']} {meta['title']}")
    lines.append("")
    lines.append(
        f"**{labels['branch']}** `{meta['branch']}` → `{meta['base']}` • "
        f"**{files_str} (+{stats['added']} / -{stats['removed']})**"
    )
    lines.append(f"**{labels['affects']}** {scope.get('affects', '')}")
    lines.append("")

    # Split Recommendation (if any)
    if split:
        lines.append(f"### {labels['split']}")
        lines.append(split.get("recommendation", ""))
        boundaries = split.get("boundaries")
        if boundaries:
            lines.append("")
            for b in boundaries:
                lines.append(f"- {b}")
        lines.append("")

    # The Gist
    lines.append(f"### {labels['gist']}")
    for g in scope.get("gist", []):
        lines.append(g)
    lines.append("")

    # Heads Up (Gotchas)
    lines.append(f"### {labels['heads_up']}")
    for gotcha in gotchas:
        refs = gotcha.get("refs", [])
        anchor = format_ref_anchor(refs[0]) if refs else ""
        anchor_part = f" {anchor}" if anchor else ""
        lines.append(f"- **{gotcha['title']}**{anchor_part}: {gotcha['body']}")
        if gotcha.get("lookFor"):
            lines.append(f"  - *{labels['check']} {gotcha['lookFor']}*")
    lines.append("")

    # Suggested Reading Order
    lines.append(f"### {labels['reading']}")
    for item in reading.get("items", []):
        anchor = format_ref_anchor(item)
        lines.append(f"- [ ] **{item['role']}** {anchor}: {item['summary']}")

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
        lines.append(f"- {t}")
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
