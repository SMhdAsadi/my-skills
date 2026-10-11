import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from walkthrough_generator import (
    render_markdown,
    render_html,
    resolve_paths_against_diff,
)


class TestWalkthroughGenerator(unittest.TestCase):
    def setUp(self):
        self.sample_data_en = {
            "schemaVersion": 2,
            "lang": "en",
            "meta": {
                "title": "Token Refresh Flow",
                "branch": "feat/token-refresh",
                "base": "main",
                "headSha": "a1b2c3d",
                "stats": {"files": 2, "added": 50, "removed": 10},
                "markdownPath": "/path/to/walkthrough.md",
            },
            "repo": {
                "root": "/Users/developer/project",
                "defaultEditor": "vscode",
            },
            "steps": [
                {
                    "id": "scope",
                    "kind": "scope",
                    "section": "Scope",
                    "title": "Small, self-contained change — read in one pass.",
                    "gist": [
                        "Updates token expiration handling.",
                        "Ensures expired tokens trigger a clean refresh.",
                    ],
                    "affects": "User authentication and session lifecycle",
                },
                {
                    "id": "token-race",
                    "kind": "gotcha",
                    "section": "Heads Up",
                    "title": "Parallel refresh race window",
                    "category": "concurrency",
                    "body": "Multiple concurrent API calls can trigger parallel refresh requests before lock is acquired.",
                    "refs": [
                        {"path": "src/auth/token.ts", "startLine": 42, "endLine": 50},
                    ],
                    "lookFor": "Check if an in-flight refresh promise is deduplicated.",
                },
                {
                    "id": "reading-order",
                    "kind": "reading",
                    "section": "Suggested Reading Order",
                    "title": "Read in order: Token Service → Config",
                    "items": [
                        {
                            "role": "Token Service",
                            "path": "src/auth/token.ts",
                            "startLine": 1,
                            "endLine": 80,
                            "summary": "Core token parsing and validation routines.",
                        },
                        {
                            "role": "Container Config",
                            "path": "Dockerfile",
                            "startLine": 1,
                            "summary": "Build environment updates.",
                        },
                    ],
                    "skim": ["README.md"],
                },
                {
                    "id": "what-to-test",
                    "kind": "test",
                    "section": "What to Test",
                    "title": "Run these 2 checks on a device.",
                    "items": [
                        "Test token expiry with expired JWT.",
                        "Verify simultaneous API calls share a single refresh promise.",
                    ],
                },
            ],
        }

        self.sample_data_fa = {
            "schemaVersion": 2,
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
            "steps": [
                {
                    "id": "scope",
                    "kind": "scope",
                    "section": "دامنه",
                    "title": "تغییر کوچک و یکپارچه — در یک نگاه بخوانید.",
                    "gist": ["این تغییر منطق تازه‌سازی توکن را به‌روز می‌کند."],
                    "affects": "ماژول احراز هویت و مدیریت نشست‌ها",
                },
                {
                    "id": "token-race",
                    "kind": "gotcha",
                    "section": "نکات حساس و ریسک‌ها",
                    "title": "همزمانی در تازه‌سازی توکن",
                    "category": "concurrency",
                    "body": "چندین فراخوانی همزمان ممکن است درخواست‌های موازی تازه‌سازی ارسال کنند.",
                    "refs": [
                        {"path": "src/auth/token.ts", "startLine": 42, "endLine": 50},
                    ],
                },
                {
                    "id": "reading-order",
                    "kind": "reading",
                    "section": "ترتیب پیشنهادی بررسی",
                    "title": "ترتیب بررسی: سرویس توکن",
                    "items": [
                        {
                            "role": "سرویس توکن",
                            "path": "src/auth/token.ts",
                            "startLine": 1,
                            "endLine": 80,
                            "summary": "توابع اعتبارسنجی و پارس توکن.",
                        },
                    ],
                    "skim": ["README.md"],
                },
                {
                    "id": "what-to-test",
                    "kind": "test",
                    "section": "مواردی که باید تست شوند",
                    "title": "این ۲ مورد را روی دستگاه بررسی کنید.",
                    "items": [
                        "تست انقضای توکن با JWT منقضی.",
                        "بررسی اشتراک پرامیس تازه‌سازی در فراخوانی‌های همزمان.",
                    ],
                },
            ],
        }

    def test_render_markdown_english(self):
        md = render_markdown(self.sample_data_en)
        self.assertIn("# Review Walkthrough: Token Refresh Flow", md)
        self.assertIn("**Branch:** `feat/token-refresh` → `main` • **2 files (+50 / -10)**", md)
        self.assertIn("**Affects:** User authentication and session lifecycle", md)
        self.assertIn("### The Gist", md)
        self.assertIn("### Heads Up", md)
        # Check gotcha line format: title + anchor + pure prose
        self.assertIn(
            "- **Parallel refresh race window** ([src/auth/token.ts:42-50](#)): Multiple concurrent API calls can trigger parallel refresh requests before lock is acquired.",
            md,
        )
        self.assertIn("### Suggested Reading Order", md)
        self.assertIn(
            "- [ ] **Token Service** ([src/auth/token.ts:1-80](#)): Core token parsing and validation routines.",
            md,
        )
        self.assertIn("*Skim: `README.md`*", md)
        self.assertIn("### What to Test", md)
        self.assertIn("- Test token expiry with expired JWT.", md)

    def test_render_markdown_persian(self):
        md = render_markdown(self.sample_data_fa)
        self.assertIn("# راهنمای بررسی: مدیریت توکن احراز هویت", md)
        self.assertIn("**برنچ:** `feat/token-refresh` → `main` • **۲ فایل (+50 / -10)**", md)
        self.assertIn("**بخش‌های تحت‌تأثیر:** ماژول احراز هویت و مدیریت نشست‌ها", md)
        self.assertIn("### خلاصه تغییرات", md)
        self.assertIn("### نکات حساس و ریسک‌ها", md)
        self.assertIn("### ترتیب پیشنهادی بررسی", md)
        self.assertIn("### مواردی که باید تست شوند", md)
        self.assertIn("*بررسی گذرا: `README.md`*", md)

    def test_render_html_inlines_json(self):
        fake_template = (
            '<!doctype html><html><head>'
            '<script type="application/json" id="walkthrough-data">{}</script>'
            '</head><body><div id="app"></div></body></html>'
        )
        html = render_html(self.sample_data_en, fake_template)
        self.assertIn('<script type="application/json" id="walkthrough-data">', html)
        self.assertIn('"schemaVersion":2', html)
        self.assertIn('"Token Refresh Flow"', html)
        # Verify < is escaped
        self.assertNotIn('</script><script>', html)

    def test_resolve_paths_against_diff(self):
        diff_files = [
            "src/auth/token.ts",
            "src/api/client.ts",
            "Dockerfile",
        ]
        # Bare name 'token.ts' should resolve to 'src/auth/token.ts'
        data = dict(self.sample_data_en)
        data["steps"][1]["refs"] = [{"path": "token.ts", "startLine": 42}]
        resolved = resolve_paths_against_diff(data, diff_files)
        self.assertEqual(resolved["steps"][1]["refs"][0]["path"], "src/auth/token.ts")

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

            md_file = Path(tmpdir) / "walkthrough.md"
            html_file = Path(tmpdir) / "walkthrough.html"

            self.assertTrue(md_file.exists(), "Markdown file was not created")
            self.assertTrue(html_file.exists(), "HTML file was not created")
            self.assertIn("Token Refresh Flow", md_file.read_text(encoding="utf-8"))
            self.assertIn("walkthrough-data", html_file.read_text(encoding="utf-8"))

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


if __name__ == "__main__":
    unittest.main()
