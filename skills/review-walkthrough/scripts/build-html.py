#!/usr/bin/env python3
"""Build the review-walkthrough HTML companion from a finished markdown file.

Usage:
    python3 build-html.py <walkthrough.md> --out <walkthrough.html> \\
        --branch <branch> --base <base> [--lang fa|en|de|es] [--head <sha>]
        [--files N --added N --removed N] [--repo-root <path>]
        [--editor vscode] [--template <template.html>]

Reads the template (default: ../assets/walkthrough-template.html), parses the
markdown walkthrough into the JSON data contract, validates it, escapes it
safely, and injects only the <script id="walkthrough-data"> block.

The markdown is the single source of truth. Exit non-zero on invalid data.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = HERE.parent / "assets" / "walkthrough-template.html"

TITLE_MAX = 160

REF_RE = re.compile(
    r"(?P<path>[A-Za-z0-9_@][A-Za-z0-9_@\-/+.]*\.[A-Za-z0-9]+)"
    r":(?P<start>\d+)(?:-(?P<end>\d+))?"
)
DATA_BLOCK_RE = re.compile(
    r'(<script\s+type="application/json"\s+id="walkthrough-data">)(.*?)(</script>)',
    re.DOTALL,
)
VALID_EDITORS = {"vscode", "vscode-insiders", "cursor", "windsurf", "vscodium"}
VALID_CATEGORIES = {
    "edge-case", "state", "layout", "concurrency", "persistence", "other",
}

CATEGORY_HINTS = [
    ({"edge", "boundary", "null", "empty", "zero", "مرزی"}, "edge-case"),
    ({"state", "render", "re-render", "rerender"}, "state"),
    ({"layout", "css", "flex", "style", "چیدمان", "استایل"}, "layout"),
    ({"race", "mutex", "concurr", "order", "همزمانی"}, "concurrency"),
    ({"persist", "reset", "cache", "stale", "ماندگاری"}, "persistence"),
]

AFFECTS_RE = re.compile(
    r"\*\*\s*(?:Affects|بخش‌های تحت‌تأثیر|Betrifft|Afecta)\s*:?\s*\*\*\s*(.+)"
)

SKIM_RE = re.compile(
    r"(?:[Ss]kim|بررسی گذرا|Überfliegen|Vistazo rápido)\s*:?\s*(.+)"
)

# A parenthesized full-path file:line mention, e.g.
# "(src/foo/Bar.tsx:35-40):". Long paths are shortened to basename form so
# the renderer shows them inline as short links ("(Bar.tsx:35):") and omits
# the duplicate footnote. Basename-only mentions pass through untouched.
FULL_PAREN_REF_RE = re.compile(
    r"\(\s*[A-Za-z0-9_@][A-Za-z0-9_@\-/+.]*\/[^()]*\.[A-Za-z0-9]+:\d+(?:-\d+)?\s*\)\s*:?"
)

SCOPE_TITLES = {
    "small": {
        "en": "Small, self-contained change — read in one pass.",
        "fa": "تغییر کوچک و یکپارچه — در یک نگاه بخوانید.",
        "de": "Kleine, überschaubare Änderung — in einem Durchgang lesen.",
        "es": "Cambio pequeño y autocontenido — leer de una pasada.",
    },
    "medium": {
        "en": "Medium change — follow the reading order below.",
        "fa": "تغییر متوسط — ترتیب بررسی زیر را دنبال کنید.",
        "de": "Mittlere Änderung — der Lesereihenfolge unten folgen.",
        "es": "Cambio mediano — seguir el orden de lectura.",
    },
    "large": {
        "en": "Large change — check the split boundary first.",
        "fa": "تغییر بزرگ — ابتدا مرز تفکیک را بررسی کنید.",
        "de": "Große Änderung — zuerst die Aufteilungsgrenze prüfen.",
        "es": "Cambio grande — revisar primero el límite de división.",
    },
}

READING_PREFIX = {
    "en": "Read in order",
    "fa": "ترتیب بررسی",
    "de": "Lesereihenfolge",
    "es": "Orden de lectura",
}

VERIFY_PREFIX = {
    "en": "Run these {n} checks on a device.",
    "fa": "این {n} مورد را روی دستگاه بررسی کنید.",
    "de": "Diese {n} Prüfungen auf einem Gerät durchführen.",
    "es": "Ejecutar estas {n} comprobaciones en un dispositivo.",
}


def fail(msg):
    print(f"build-html: error: {msg}", file=sys.stderr)
    sys.exit(1)


def git(*args):
    try:
        out = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=15
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def detect_lang(text):
    if "راهنمای بررسی" in text:
        return "fa"
    if "Review-Überblick" in text or "Lesereihenfolge" in text:
        return "de"
    if "Guía de Revisión" in text or "Lectura Sugerido" in text:
        return "es"
    return "en"


def base_lang(lang):
    return (lang or "en").split("-")[0].lower()


def slugify(text, taken):
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "step"
    slug, i = base, 2
    while slug in taken:
        slug = f"{base}-{i}"
        i += 1
    taken.add(slug)
    return slug


def clean_inline(text):
    """Strip markdown links/images/formatting to plain text for JSON."""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(
        r"\[([^\]]*)\]\(([^)]*)\)",
        lambda m: m.group(1) if m.group(2) == "#" else f"{m.group(1)} ({m.group(2)})",
        text,
    )
    text = text.replace("**", "").replace("__", "")
    return text.strip(" -")


def parse_refs(text):
    refs = []
    for m in REF_RE.finditer(text):
        start = int(m.group("start"))
        end = int(m.group("end")) if m.group("end") else None
        if "/" not in m.group("path") and "\\" not in m.group("path"):
            pass  # bare filenames are fine (skim-style or root files)
        refs.append(
            {
                "path": m.group("path"),
                "startLine": start,
                **({"endLine": end} if end and end != start else {}),
            }
        )
    # de-dupe, max 3
    seen, uniq = set(), []
    for r in refs:
        key = (r["path"], r["startLine"], r.get("endLine"))
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    return uniq[:3]


def strip_body(text):
    """Shorten parenthesized full-path mentions to basename form.

    `([src/a/Bar.tsx:35](#))` arrives here as `(src/a/Bar.tsx:35):` (after
    link cleanup) and becomes `(Bar.tsx:35):`, which the renderer linkifies
    inline — so no separate footnote is needed for it.
    """

    def short(m):
        inner = REF_RE.search(m.group(0))
        if not inner:
            return m.group(0)
        base = inner.group("path").rsplit("/", 1)[-1]
        loc = base + ":" + inner.group("start")
        if inner.group("end"):
            loc += "-" + inner.group("end")
        return "(" + loc + "):"

    text = FULL_PAREN_REF_RE.sub(short, text)
    # Collapse an immediately duplicated mention: "(A:1): (A:1): body" → "(A:1): body".
    text = re.sub(
        r"(\([^()]+:\d+(?:-\d+)?\)\s*:?)\s*\1", r"\1", text
    )
    return re.sub(r"\s{2,}", " ", text).strip(" :")


def split_sections(md):
    """Split markdown into (level, heading, body) chunks on ### headings."""
    parts = re.split(r"(?m)^(#{1,3})\s+(.*)\s*$", md)
    # parts[0] = pre-title text, then triples of (hashes, heading, body)
    chunks = [("pre", "", parts[0])]
    for i in range(1, len(parts) - 1, 3):
        chunks.append((parts[i], parts[i + 1].strip(), parts[i + 2].strip()))
    return chunks


def bullets(body):
    items = []
    for line in body.splitlines():
        m = re.match(r"\s*[-*]\s+(?:\[[ xX]\]\s+)?(.*)", line)
        if m and m.group(1).strip():
            items.append(m.group(1).strip())
    return items


def is_split_heading(h):
    return bool(
        re.search(r"split|تفکیک|aufteilung|sugerencia|divisi", h, re.IGNORECASE)
    )


def guess_category(title, body):
    hay = f"{title} {body}".lower()
    for words, cat in CATEGORY_HINTS:
        if any(w in hay for w in words):
            return cat
    return "other"


def scope_title_for(files, added, removed, lang):
    total = added + removed
    bucket = "medium"
    if files <= 5 and total <= 200:
        bucket = "small"
    elif files > 15 or total > 800:
        bucket = "large"
    lang = base_lang(lang)
    if lang not in SCOPE_TITLES[bucket]:
        lang = "en"
    return SCOPE_TITLES[bucket][lang]


def reading_title_for(roles, lang):
    lang = base_lang(lang)
    prefix = READING_PREFIX.get(lang, READING_PREFIX["en"])
    joined = " → ".join(roles)
    title = f"{prefix}: {joined}" if joined else prefix
    if len(title) > TITLE_MAX:
        title = title[: TITLE_MAX - 1].rstrip() + "…"
    return title


def test_title_for(items, lang):
    lang = base_lang(lang)
    template = VERIFY_PREFIX.get(lang, VERIFY_PREFIX["en"])
    return template.format(n=len(items))[:TITLE_MAX]


def tracked_by_basename(root):
    """Map basename -> [repo-relative paths] from `git ls-files`.

    Used to resolve basename-only refs (e.g. `Bar.tsx:35`) to their full
    repo-relative path so editor links open the real file. Returns {} when
    the root is unknown or not a git checkout.
    """
    if not root:
        return {}
    try:
        out = subprocess.run(
            ["git", "-C", root, "ls-files"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        return {}
    if out.returncode != 0:
        return {}
    m = {}
    for line in out.stdout.splitlines():
        line = line.strip()
        if line:
            m.setdefault(line.rsplit("/", 1)[-1], []).append(line)
    return m


def parse_markdown(md, args, lang, root):
    lines = md.splitlines()
    title = next((l[2:].strip() for l in lines if l.startswith("# ")), "Review")
    title = clean_inline(re.sub(r"^[^:]*:\s*", "", title)) or clean_inline(
        next((l[2:].strip() for l in lines if l.startswith("# ")), "Review")
    )

    chunks = [c for c in split_sections(md) if c[0] != "pre"]
    h3 = [(h, b) for level, h, b in chunks if level == "###"]
    if len(h3) < 4:
        fail(
            f"expected at least 4 '###' sections (gist, gotchas, reading, test), "
            f"found {len(h3)}"
        )
    idx = 0
    split_rec = None
    if is_split_heading(h3[0][0]):
        split_rec = h3[0][1]
        idx = 1
    gist_sec, gotcha_sec, reading_sec, test_sec = (
        h3[idx][1], h3[idx + 1][1], h3[idx + 2][1], h3[idx + 3][1],
    )
    gist_head, gotcha_head, reading_head, test_head = (
        h3[idx][0], h3[idx + 1][0], h3[idx + 2][0], h3[idx + 3][0],
    )

    # scope bar: **Branch:** b -> base ... X files (+Y / -Z)
    m = re.search(r"(\d+)\s+files?\s*\(\+(\d+)\s*/\s*[−-](\d+)\)", md)
    files = args.files if args.files is not None else int(m.group(1)) if m else 0
    added = args.added if args.added is not None else int(m.group(2)) if m else 0
    removed = args.removed if args.removed is not None else int(m.group(3)) if m else 0
    am = AFFECTS_RE.search(md)
    affects = clean_inline(am.group(1)) if am else ""

    gist = [
        clean_inline(s)
        for s in re.split(r"\n+", gist_sec)
        if clean_inline(s)
    ][:3]
    if not gist:
        fail("gist section is empty")

    # Resolve basename-only refs against the working tree so every stored
    # path is repo-relative and every editor link opens the real file.
    by_base = tracked_by_basename(root)

    def resolve(path):
        if "/" in path:
            return path
        cands = by_base.get(path, [])
        return cands[0] if len(cands) == 1 else path

    taken = {"scope", "reading-order", "what-to-test"}
    steps = [
        {
            "id": "scope",
            "kind": "scope",
            "section": clean_inline(gist_head)[:40] or "Scope",
            "title": scope_title_for(files, added, removed, lang)[:TITLE_MAX],
            "gist": gist,
            "affects": affects or gist[-1],
        }
    ]
    if split_rec:
        rec_lines = [clean_inline(s) for s in re.split(r"\n+", split_rec) if clean_inline(s)]
        steps.append(
            {
                "id": "split",
                "kind": "split",
                "section": clean_inline(h3[0][0])[:40] or "Split",
                "title": (rec_lines[0][:TITLE_MAX] if rec_lines else "Consider splitting."),
                "recommendation": " ".join(rec_lines) or "Consider splitting.",
            }
        )

    gotchas = bullets(gotcha_sec)
    if not 1 <= len(gotchas) <= 4:
        fail(f"expected 1-4 gotcha bullets, found {len(gotchas)} (fix the markdown first)")
    for b in gotchas:
        refs = parse_refs(b)
        if not refs:
            fail(f"gotcha without a verifiable file:line ref: {b[:80]}")
        for r in refs:
            r["path"] = resolve(r["path"])
        title_b = re.sub(r"^\*\*(.+?)\*\*.*", r"\1", b)
        title_b = clean_inline(title_b)[:TITLE_MAX]
        body = strip_body(clean_inline(re.sub(r"^\*\*.+?\*\*\s*", "", b)))
        steps.append(
            {
                "id": slugify(title_b, taken),
                "kind": "gotcha",
                "section": clean_inline(gotcha_head)[:40] or "Gotcha",
                "title": title_b,
                "category": guess_category(title_b, body),
                "body": body or title_b,
                "refs": refs,
            }
        )

    reading = bullets(reading_sec)
    if not reading:
        fail("reading-order section has no items")
    items = []
    for b in reading:
        refs = parse_refs(b)
        if not refs:
            continue
        r = refs[0]
        r["path"] = resolve(r["path"])
        role_m = re.match(r"\*\*(.+?)\*\*", b)
        role = clean_inline(role_m.group(1)) if role_m else r["path"]
        summary = strip_body(
            clean_inline(re.sub(r"^\*\*.+?\*\*\s*", "", b))
        ) or role
        items.append(
            {
                "role": role[:80],
                "path": r["path"],
                "startLine": r["startLine"],
                **({"endLine": r["endLine"]} if "endLine" in r else {}),
                "summary": summary,
            }
        )
    if not items:
        fail("no reading-order item has a file:line ref")
    skim_m = SKIM_RE.search(reading_sec)
    skim = []
    if skim_m:
        skim = [
            p.strip(" `*") for p in re.split(r"[,،]", skim_m.group(1)) if "." in p
        ][:8]
    steps.append(
        {
            "id": "reading-order",
            "kind": "reading",
            "section": clean_inline(reading_head)[:40] or "Reading",
            "title": reading_title_for([i["role"] for i in items], lang),
            "items": items,
            **({"skim": skim} if skim else {}),
        }
    )

    tests = bullets(test_sec)
    if len(tests) < 2:
        fail(f"expected 2-3 test bullets, found {len(tests)}")
    test_items = [clean_inline(t) for t in tests[:3]]
    steps.append(
        {
            "id": "what-to-test",
            "kind": "test",
            "section": clean_inline(test_head)[:40] or "Test",
            "title": test_title_for(test_items, lang),
            "items": test_items,
        }
    )
    return title, steps, (files, added, removed)


def validate(data):
    kinds = [s["kind"] for s in data["steps"]]
    assert kinds[0] == "scope", "first step must be scope"
    assert kinds[-1] == "test", "last step must be test"
    assert kinds.count("scope") == 1 and kinds.count("reading") == 1
    assert kinds.count("test") == 1 and kinds.count("split") <= 1
    assert 1 <= kinds.count("gotcha") <= 4, "gotcha count"
    if "split" in kinds:
        assert kinds[1] == "split", "split must follow scope"
    assert kinds.index("reading") > max(
        i for i, k in enumerate(kinds) if k == "gotcha"
    ), "reading must follow gotchas"
    ids = [s["id"] for s in data["steps"]]
    assert len(set(ids)) == len(ids), "duplicate step ids"
    for s in data["steps"]:
        assert len(s["title"]) <= TITLE_MAX, f"title too long: {s['id']}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("markdown", help="finished walkthrough .md")
    ap.add_argument("--out", "--html", dest="out", required=True)
    ap.add_argument("--branch", default="")
    ap.add_argument("--base", default="")
    ap.add_argument("--lang", default="")
    ap.add_argument("--head", default="")
    ap.add_argument("--files", type=int, default=None)
    ap.add_argument("--added", type=int, default=None)
    ap.add_argument("--removed", type=int, default=None)
    ap.add_argument("--repo-root", default="")
    ap.add_argument("--editor", default="vscode")
    ap.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    args = ap.parse_args()

    md_path = Path(args.markdown)
    if not md_path.exists():
        fail(f"markdown not found: {md_path}")
    md = md_path.read_text(encoding="utf-8")

    tpl_path = Path(args.template)
    if not tpl_path.exists():
        fail(f"template not found: {tpl_path}")
    tpl = tpl_path.read_text(encoding="utf-8")
    if not DATA_BLOCK_RE.search(tpl):
        fail("template has no walkthrough-data block")

    if args.editor not in VALID_EDITORS:
        fail(f"unknown editor: {args.editor}")
    lang = args.lang or detect_lang(md)
    head = args.head or git("rev-parse", "--short", "HEAD") or "HEAD"
    repo_root = args.repo_root or git("rev-parse", "--show-toplevel")
    # Never store a literal `~`: editors cannot resolve it in file URLs.
    repo_root = os.path.abspath(os.path.expanduser(repo_root)) if repo_root else ""

    title, steps, (nfiles, nadded, nremoved) = parse_markdown(md, args, lang, repo_root)
    data = {
        "schemaVersion": 1,
        "lang": lang,
        "meta": {
            "title": title[:TITLE_MAX],
            "branch": args.branch or "branch",
            "base": args.base or "main",
            "headSha": head,
            "stats": {"files": nfiles, "added": nadded, "removed": nremoved},
            "markdownPath": str(md_path.resolve()),
        },
        "repo": {
            **({"root": repo_root} if repo_root else {}),
            "editor": args.editor,
        },
        "steps": steps,
    }
    try:
        validate(data)
    except AssertionError as e:
        fail(f"contract validation: {e}")

    payload = (
        json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )
    # sanity: it must parse back
    json.loads(payload.replace("\\u003c", "<"))
    html = DATA_BLOCK_RE.sub(
        lambda m: m.group(1) + payload + m.group(3), tpl, count=1
    )
    Path(args.out).write_text(html, encoding="utf-8")
    print(
        f"wrote {args.out}: {len(steps)} steps "
        f"({sum(1 for s in steps if s['kind']=='gotcha')} gotchas, "
        f"{len([s for s in steps if s['kind']=='reading'][0]['items'])} reading items)"
    )


if __name__ == "__main__":
    main()
