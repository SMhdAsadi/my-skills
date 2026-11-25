import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from walkthrough_generator import (
    CompileError,
    CompileResult,
    compile_walkthrough,
    fix_rtl_arrows,
    render_html,
    render_markdown,
    resolve_paths_against_diff,
)
from walkthrough_schema import ValidationError


def make_sample_en():
    return {
        "schemaVersion": 3,
        "lang": "en",
        "meta": {
            "title": "Token Refresh Flow",
            "branch": "feat/token-refresh",
            "base": "main",
            "headSha": "a1b2c3d",
            "stats": {"files": 3, "added": 50, "removed": 10},
            "markdownPath": "/path/to/walkthrough.md",
        },
        "repo": {
            "root": "/Users/developer/project",
            "defaultEditor": "vscode",
        },
        "overview": {
            "title": "Deduplicated token refresh & session eviction",
            "summary": [
                "Updates token expiration handling across API clients.",
                "Ensures expired tokens trigger a clean single-flight refresh.",
            ],
            "affects": "User authentication and session lifecycle",
            "split": {
                "recommendation": "Separate Dockerfile updates if deploying independently.",
                "boundaries": ["Token refresh lock", "Container build"],
            },
            "skim": ["README.md", "package-lock.json"],
        },
        "slices": [
            {
                "id": "token-refresh",
                "title": "Deduplicate concurrent token refresh",
                "summary": [
                    "Coordinates parallel 401 responses behind a single refresh promise."
                ],
                "files": [
                    {
                        "role": "Token Service",
                        "path": "src/auth/token.ts",
                        "startLine": 1,
                        "endLine": 80,
                        "status": "modified",
                        "summary": "Core token parsing and validation routines.",
                    },
                    {
                        "role": "Container Config",
                        "path": "Dockerfile",
                        "startLine": 1,
                        "status": "added",
                        "summary": "Build environment updates.",
                    },
                ],
                "headsUp": [
                    {
                        "title": "Parallel refresh race window",
                        "body": "Multiple concurrent API calls can trigger parallel refresh requests before lock is acquired.",
                        "refs": [
                            {"path": "src/auth/token.ts", "startLine": 42, "endLine": 50}
                        ],
                        "lookFor": "Check if an in-flight refresh promise is deduplicated.",
                    }
                ],
                "qa": [
                    "Test token expiry with expired JWT.",
                    "Verify simultaneous API calls share a single refresh promise.",
                ],
            },
            {
                "id": "session-eviction",
                "title": "Evict stale credentials on failure",
                "summary": ["Clears cached tokens when refresh fails with 401."],
                "files": [
                    {
                        "role": "Eviction Handler",
                        "path": "src/auth/token.ts",
                        "startLine": 90,
                        "endLine": 120,
                        "summary": "Clears storage and resets client state.",
                    }
                ],
                "headsUp": [],
                "qa": [],
            },
        ],
        "crossCutting": {
            "title": "Cross-Cutting Notes",
            "headsUp": [
                {
                    "title": "Session cleanup ordering",
                    "body": "Queued callers must reject cleanly when eviction runs.",
                    "refs": [],
                    "lookFor": "Confirm no caller hangs forever.",
                }
            ],
            "qa": ["Expire refresh token mid-flight and confirm redirect to login."],
        },
    }


def make_sample_fa():
    return {
        "schemaVersion": 3,
        "lang": "fa",
        "meta": {
            "title": "مدیریت توکن احراز هویت",
            "branch": "feat/token-refresh",
            "base": "main",
            "headSha": "a1b2c3d",
            "stats": {"files": 2, "added": 50, "removed": 10},
        },
        "repo": {
            "root": "/Users/developer/project",
            "defaultEditor": "vscode",
        },
        "overview": {
            "title": "به‌روزرسانی منطق تازه‌سازی توکن",
            "summary": ["این تغییر منطق تازه‌سازی توکن را یکپارچه می‌کند."],
            "affects": "ماژول احراز هویت و مدیریت نشست‌ها",
            "skim": ["README.md"],
        },
        "slices": [
            {
                "id": "token-refresh",
                "title": "همگام‌سازی تازه‌سازی توکن",
                "summary": ["درخواست‌های همزمان به یک پرامیس مشترک وصل می‌شوند."],
                "files": [
                    {
                        "role": "سرویس توکن",
                        "path": "src/auth/token.ts",
                        "startLine": 1,
                        "endLine": 80,
                        "summary": "توابع اعتبارسنجی و پارس توکن.",
                    }
                ],
                "headsUp": [
                    {
                        "title": "همزمانی در تازه‌سازی توکن",
                        "body": "چندین فراخوانی همزمان ممکن است درخواست‌های موازی تازه‌سازی ارسال کنند.",
                        "refs": [
                            {"path": "src/auth/token.ts", "startLine": 42, "endLine": 50}
                        ],
                    }
                ],
                "qa": [
                    "تست انقضای توکن با JWT منقضی.",
                    "بررسی اشتراک پرامیس تازه‌سازی در فراخوانی‌های همزمان.",
                ],
            }
        ],
    }


class TestWalkthroughGenerator(unittest.TestCase):
    def setUp(self):
        self.sample_data_en = make_sample_en()
        self.sample_data_fa = make_sample_fa()

    def test_render_markdown_english(self):
        md = render_markdown(self.sample_data_en)
        self.assertIn("# Review Walkthrough: Token Refresh Flow", md)
        self.assertIn(
            "**Branch:** `feat/token-refresh` → `main` • **3 files (+50 / -10)**",
            md,
        )
        self.assertIn("**Affects:** User authentication and session lifecycle", md)
        self.assertIn("### Split Recommendation", md)
        self.assertIn("### Overview", md)
        self.assertIn("<details>", md)
        self.assertIn("Skim (2 files)", md)
        self.assertIn("## 1. Deduplicate concurrent token refresh", md)
        self.assertIn("### Files", md)
        self.assertIn(
            "- [ ] **Token Service** ([src/auth/token.ts:1-80](#)): Core token parsing and validation routines.",
            md,
        )
        self.assertIn("### Heads Up", md)
        self.assertIn(
            "- **Parallel refresh race window** ([src/auth/token.ts:42-50](#)): Multiple concurrent API calls can trigger parallel refresh requests before lock is acquired.",
            md,
        )
        self.assertIn("  - *Check: Check if an in-flight refresh promise is deduplicated.*", md)
        self.assertIn("### What to Test", md)
        self.assertIn("- [ ] Test token expiry with expired JWT.", md)

        # Slice 2 has 0 headsUp and 0 qa: verify no empty subheadings after Slice 2
        slice2_pos = md.index("## 2. Evict stale credentials on failure")
        cc_pos = md.index("## Cross-Cutting Notes")
        slice2_block = md[slice2_pos:cc_pos]
        self.assertIn("### Files", slice2_block)
        self.assertNotIn("### Heads Up", slice2_block)
        self.assertNotIn("### What to Test", slice2_block)

        # Cross-Cutting zero-refs headsUp renders cleanly without empty parens
        cc_block = md[cc_pos:]
        self.assertIn(
            "- **Session cleanup ordering**: Queued callers must reject cleanly when eviction runs.",
            cc_block,
        )
        self.assertIn(
            "- [ ] Expire refresh token mid-flight and confirm redirect to login.",
            cc_block,
        )

    def test_render_markdown_omits_empty_optional_sections(self):
        minimal = {
            "schemaVersion": 3,
            "lang": "en",
            "meta": {
                "title": "Rename Helper",
                "branch": "refactor/helper",
                "base": "main",
                "headSha": "abc1234",
                "stats": {"files": 1, "added": 2, "removed": 2},
            },
            "overview": {
                "title": "Single helper rename",
                "affects": "String utilities",
            },
            "slices": [
                {
                    "id": "rename-helper",
                    "title": "Rename formatSlug",
                    "summary": ["Renames formatSlug to normalizeSlug."],
                    "files": [
                        {
                            "role": "Helper",
                            "path": "src/slug.ts",
                            "startLine": 5,
                            "summary": "Updates function name.",
                        }
                    ],
                }
            ],
        }
        md = render_markdown(minimal)
        self.assertIn("## 1. Rename formatSlug", md)
        self.assertNotIn("### Overview", md)
        self.assertNotIn("### Split Recommendation", md)
        self.assertNotIn("<details>", md)
        self.assertNotIn("### Heads Up", md)
        self.assertNotIn("### What to Test", md)
        self.assertNotIn("Cross-Cutting", md)

    def test_render_markdown_persian(self):
        md = render_markdown(self.sample_data_fa)
        self.assertIn("# راهنمای بررسی: مدیریت توکن احراز هویت", md)
        self.assertIn("**برنچ:** `feat/token-refresh` → `main` • **۲ فایل (+50 / -10)**", md)
        self.assertIn("**بخش‌های تحت‌تأثیر:** ماژول احراز هویت و مدیریت نشست‌ها", md)
        self.assertIn("### خلاصه تغییرات", md)
        self.assertIn("بررسی گذرا (۱ فایل)", md)
        self.assertIn("## 1. همگام‌سازی تازه‌سازی توکن", md)
        self.assertIn("### فایل‌ها", md)
        self.assertIn("### نکات حساس و ریسک‌ها", md)
        self.assertIn("### مواردی که باید تست شوند", md)
        self.assertIn("- [ ] تست انقضای توکن با JWT منقضی.", md)

    def test_render_html_inlines_json(self):
        fake_template = (
            '<!doctype html><html><head>'
            '<script type="application/json" id="walkthrough-data">{}</script>'
            '</head><body><div id="app"></div></body></html>'
        )
        html = render_html(self.sample_data_en, fake_template)
        self.assertIn('<script type="application/json" id="walkthrough-data">', html)
        self.assertIn('"schemaVersion":3', html)
        self.assertIn('"Token Refresh Flow"', html)
        self.assertNotIn("</script><script>", html)

    def test_resolve_paths_against_diff_v3(self):
        diff_files = [
            "src/auth/token.ts",
            "src/api/client.ts",
            "docs/README.md",
            "src/a/dup.ts",
            "src/b/dup.ts",
        ]
        data = copy.deepcopy(self.sample_data_en)
        data["overview"]["skim"] = ["README.md", "dup.ts"]
        data["slices"][0]["files"][0]["path"] = "token.ts"
        data["slices"][0]["headsUp"][0]["refs"] = [{"path": "client.ts", "startLine": 12}]
        data["crossCutting"]["headsUp"][0]["refs"] = [{"path": "token.ts", "startLine": 95}]

        resolved = resolve_paths_against_diff(data, diff_files)
        self.assertEqual(resolved["overview"]["skim"], ["docs/README.md", "dup.ts"])
        self.assertEqual(resolved["slices"][0]["files"][0]["path"], "src/auth/token.ts")
        self.assertEqual(
            resolved["slices"][0]["headsUp"][0]["refs"][0]["path"],
            "src/api/client.ts",
        )
        self.assertEqual(
            resolved["crossCutting"]["headsUp"][0]["refs"][0]["path"],
            "src/auth/token.ts",
        )

    def test_cli_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "walkthrough.json"
            json_path.write_text(json.dumps(self.sample_data_en), encoding="utf-8")

            cli_script = SCRIPTS_DIR / "build-walkthrough.py"
            res = subprocess.run(
                [sys.executable, str(cli_script), str(json_path), "--out-dir", tmpdir],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, f"CLI failed: {res.stderr}")
            self.assertIn("2 slices", res.stdout)
            self.assertIn("2 heads-up", res.stdout)
            self.assertIn("3 files", res.stdout)
            self.assertIn("3 qa", res.stdout)

            md_file = Path(tmpdir) / "walkthrough.md"
            html_file = Path(tmpdir) / "walkthrough.html"

            self.assertTrue(md_file.exists(), "Markdown file was not created")
            self.assertTrue(html_file.exists(), "HTML file was not created")
            self.assertIn("Token Refresh Flow", md_file.read_text(encoding="utf-8"))
            self.assertIn("walkthrough-data", html_file.read_text(encoding="utf-8"))

    def test_cli_rejects_invalid_v2_and_writes_nothing(self):
        bad_v2 = {
            "schemaVersion": 2,
            "lang": "en",
            "meta": {
                "title": "Legacy v2",
                "branch": "feat/x",
                "base": "main",
                "headSha": "abc1234",
                "stats": {"files": 1, "added": 1, "removed": 0},
            },
            "steps": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "walkthrough.json"
            json_path.write_text(json.dumps(bad_v2), encoding="utf-8")

            cli_script = SCRIPTS_DIR / "build-walkthrough.py"
            res = subprocess.run(
                [sys.executable, str(cli_script), str(json_path), "--out-dir", tmpdir],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(res.returncode, 0)
            self.assertIn("schemaVersion", res.stderr)
            self.assertIn(str(json_path.resolve()), res.stderr)
            self.assertFalse((Path(tmpdir) / "walkthrough.md").exists())
            self.assertFalse((Path(tmpdir) / "walkthrough.html").exists())

    def test_shim_delegates_to_build_walkthrough(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "walkthrough.json"
            json_path.write_text(json.dumps(self.sample_data_en), encoding="utf-8")

            shim_script = SCRIPTS_DIR / "build-html.py"
            out_html = Path(tmpdir) / "out.html"
            res = subprocess.run(
                [sys.executable, str(shim_script), str(json_path), "--out", str(out_html)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, f"Shim failed: {res.stderr}")
            self.assertTrue(out_html.exists(), "Shim did not produce HTML output")

    def test_fix_rtl_arrows_helper(self):
        self.assertEqual(
            fix_rtl_arrows("ترتیب بررسی: بخش اول → بخش دوم -> بخش سوم ➔ بخش چهارم", is_rtl=True),
            "ترتیب بررسی: بخش اول ← بخش دوم ← بخش سوم ← بخش چهارم",
        )
        self.assertEqual(
            fix_rtl_arrows("بررسی تابع `a -> b` و مدل داده → کنترلر", is_rtl=True),
            "بررسی تابع `a -> b` و مدل داده ← کنترلر",
        )
        self.assertEqual(
            fix_rtl_arrows("Read in order: A → B -> C", is_rtl=False),
            "Read in order: A → B -> C",
        )

    def test_render_markdown_persian_normalizes_arrows(self):
        data = copy.deepcopy(self.sample_data_fa)
        data["meta"]["title"] = "مدیریت توکن: احراز هویت → لایه نشست"
        data["slices"][0]["title"] = "مسیر درخواست → قفل همزمانی"
        data["slices"][0]["headsUp"][0]["title"] = "نکته: ریکوئست → کش"
        md = render_markdown(data)
        self.assertIn("مدیریت توکن: احراز هویت ← لایه نشست", md)
        self.assertIn("مسیر درخواست ← قفل همزمانی", md)
        self.assertIn("نکته: ریکوئست ← کش", md)

    def test_compile_walkthrough_in_memory(self):
        result = compile_walkthrough(self.sample_data_en, write_files=False)
        self.assertIsInstance(result, CompileResult)
        self.assertIn("# Review Walkthrough: Token Refresh Flow", result.markdown)
        self.assertIn('<script type="application/json" id="walkthrough-data">', result.html)
        self.assertIn('"Token Refresh Flow"', result.html)
        self.assertEqual(result.stats["slices"], 2)
        self.assertEqual(result.stats["heads_up"], 2)
        self.assertEqual(result.stats["files"], 3)
        self.assertEqual(result.stats["qa_items"], 3)
        self.assertGreaterEqual(result.elapsed_ms, 0.0)
        self.assertIsNone(result.md_path)
        self.assertIsNone(result.html_path)

    def test_compile_walkthrough_writes_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "walkthrough.json"
            json_path.write_text(json.dumps(self.sample_data_en), encoding="utf-8")

            result = compile_walkthrough(json_path, out_dir=tmpdir)
            self.assertIsNotNone(result.md_path)
            self.assertIsNotNone(result.html_path)
            self.assertTrue(result.md_path.exists())
            self.assertTrue(result.html_path.exists())
            self.assertIn("Token Refresh Flow", result.md_path.read_text(encoding="utf-8"))
            self.assertIn("walkthrough-data", result.html_path.read_text(encoding="utf-8"))

    def test_compile_walkthrough_with_diff_files(self):
        spec = copy.deepcopy(self.sample_data_en)
        spec["slices"][0]["headsUp"][0]["refs"] = [{"path": "token.ts", "startLine": 42}]
        diff_files = ["src/auth/token.ts", "README.md"]
        result = compile_walkthrough(spec, diff_files=diff_files, write_files=False)
        self.assertEqual(
            result.data["slices"][0]["headsUp"][0]["refs"][0]["path"],
            "src/auth/token.ts",
        )

    def test_compile_walkthrough_raises_on_invalid_schema(self):
        with self.assertRaises(ValidationError):
            compile_walkthrough({"schemaVersion": 3, "meta": {}}, write_files=False)

    def test_compile_walkthrough_raises_on_missing_file(self):
        with self.assertRaises(CompileError):
            compile_walkthrough("/non/existent/path/walkthrough.json", write_files=False)


if __name__ == "__main__":
    unittest.main()
