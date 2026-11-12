from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import figma_snapshot as fs  # noqa: E402

URL = "https://www.figma.com/design/b5LeA9hY1u4XAlbKXciALw/Virasty-UI-Design?node-id=5150-60514&m=auto"


class ParsingTests(unittest.TestCase):
    def test_design_url(self):
        target = fs.parse_target(URL)
        self.assertEqual(target.file_key, "b5LeA9hY1u4XAlbKXciALw")
        self.assertEqual(target.node_id, "5150:60514")
        self.assertEqual(target.kind, "design")

    def test_file_url_without_node(self):
        target = fs.parse_target("https://www.figma.com/file/abcdef1234567890/Name")
        self.assertEqual(target.file_key, "abcdef1234567890")
        self.assertIsNone(target.node_id)
        self.assertEqual(target.kind, "file")

    def test_proto_and_board(self):
        self.assertEqual(fs.parse_target("https://figma.com/proto/abc123def456/Flow?node-id=1-2").node_id, "1:2")
        self.assertEqual(fs.parse_target("https://www.figma.com/board/abc123def456/Board").kind, "board")

    def test_bare_key(self):
        target = fs.parse_target("abcdef1234567890")
        self.assertEqual(target.file_key, "abcdef1234567890")
        self.assertIsNone(target.node_id)

    def test_invalid_target(self):
        with self.assertRaises(fs.FigmaError) as ctx:
            fs.parse_target("https://example.com/design/abc123def456")
        self.assertEqual(ctx.exception.code, fs.EXIT_TARGET)

    def test_node_id_normalization(self):
        self.assertEqual(fs.normalize_node_id("1-2"), "1:2")
        self.assertEqual(fs.normalize_node_id("I1-2;3-4"), "I1:2;3:4")
        with self.assertRaises(fs.FigmaError):
            fs.normalize_node_id("1/2")

    def test_sanitize(self):
        self.assertEqual(fs.sanitize_id("8:658"), "8_658")
        self.assertEqual(fs.sanitize_id("I1:2;3:4"), "I1_2_3_4")


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cache = fs.Cache(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_default_budget_and_spend(self):
        self.assertEqual(self.cache.budget(), 20)
        self.cache.assert_budget()
        self.cache.spend("node", "filekey12345", "1:2")
        self.assertEqual(self.cache.usage()["spent"], 1)
        self.assertEqual(self.cache.remaining(), 19)

    def test_budget_env_override(self):
        with mock.patch.dict(fs.os.environ, {fs.BUDGET_ENV: "5"}):
            self.assertEqual(self.cache.budget(), 5)

    def test_budget_exhausted(self):
        self.cache.set_budget(1)
        self.cache.spend("index", "filekey12345")
        with self.assertRaises(fs.FigmaError) as ctx:
            self.cache.assert_budget()
        self.assertEqual(ctx.exception.code, fs.EXIT_BUDGET)

    def test_month_rollover(self):
        self.cache._write_json(self.cache.usage_path, {"month": "2000-01", "spent": 99, "entries": []})
        usage = self.cache.usage()
        self.assertEqual(usage["spent"], 0)
        self.assertEqual(usage["month"], fs.month_key())

    def test_record(self):
        self.cache.record(7)
        self.assertEqual(self.cache.usage()["spent"], 7)
        self.assertEqual(self.cache.remaining(), 13)

    def test_manifest_entry_versions(self):
        self.cache.update_manifest("filekey12345", kind="index", version="v1", name="Test")
        self.cache.update_manifest("filekey12345", kind="node", version="v1", node_id="1:2")
        self.cache.update_manifest("filekey12345", kind="image", version="v1", node_id="1:2", fmt="png", scale=2.0)
        manifest = self.cache.manifest("filekey12345")
        self.assertEqual(self.cache.entry_version(manifest, "index"), "v1")
        self.assertEqual(self.cache.entry_version(manifest, "node", node_id="1:2"), "v1")
        self.assertEqual(self.cache.entry_version(manifest, "image", node_id="1:2", fmt="png", scale=2.0), "v1")

    def test_atomic_write(self):
        path = self.cache.home / "nested" / "data.json"
        self.cache.write_json_file(path, {"ok": True})
        self.assertTrue(path.is_file())
        self.assertFalse(path.with_name(path.name + ".tmp").exists())
        self.assertEqual(json.loads(path.read_text()), {"ok": True})

    def test_prune(self):
        old = self.cache.file_dir("oldfilekey123")
        old.mkdir(parents=True)
        (old / "manifest.json").write_text("{}")
        old_time = 0
        import os

        os.utime(old / "manifest.json", (old_time, old_time))
        removed, _ = self.cache.prune(1)
        self.assertEqual(removed, ["oldfilekey123"])
        self.assertFalse(old.exists())


class SummaryTests(unittest.TestCase):
    def test_summarize_index(self):
        data = {
            "name": "File",
            "role": "viewer",
            "version": "v1",
            "lastModified": "2026-01-01",
            "document": {"children": [{"id": "0:1", "name": "Page", "children": [{"id": "1:2"}, {"id": "1:3"}]}]},
            "components": {"a": {}},
            "componentSets": {},
            "styles": {"s": {}, "t": {}},
        }
        summary = fs.summarize_index(data)
        self.assertEqual(summary["total_top_level"], 2)
        self.assertEqual(summary["components"], 1)
        self.assertEqual(summary["styles"], 2)

    def test_summarize_node(self):
        data = {
            "version": "v1",
            "nodes": {
                "1:2": {
                    "document": {
                        "id": "1:2",
                        "name": "Screen",
                        "type": "FRAME",
                        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 200},
                        "children": [
                            {"id": "1:3", "name": "Title", "type": "TEXT", "characters": "Hello"},
                            {"id": "1:4", "name": "Box", "type": "RECTANGLE"},
                        ],
                    },
                    "components": {},
                    "styles": {},
                }
            },
        }
        summary = fs.summarize_node(data, "1:2")
        self.assertEqual(summary["name"], "Screen")
        self.assertEqual(summary["child_count"], 2)
        self.assertEqual(summary["texts"][0]["characters"], "Hello")


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cache = fs.Cache(Path(self.temp.name))
        self.target = fs.parse_target(URL)

    def tearDown(self):
        self.temp.cleanup()

    def test_dry_run_does_not_spend(self):
        service = fs.SnapshotService(self.cache, dry_run=True)
        result = service.index(self.target)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["spent"], 1)
        self.assertEqual(self.cache.usage()["spent"], 0)

    def test_budget_exhausted_before_fetch(self):
        self.cache.set_budget(0)
        service = fs.SnapshotService(self.cache)
        with self.assertRaises(fs.FigmaError) as ctx:
            service.index(self.target)
        self.assertEqual(ctx.exception.code, fs.EXIT_BUDGET)

    def test_node_requires_node_id(self):
        target = fs.parse_target("abcdef1234567890")
        service = fs.SnapshotService(self.cache)
        with self.assertRaises(fs.FigmaError) as ctx:
            service.node(target)
        self.assertEqual(ctx.exception.code, fs.EXIT_TARGET)

    def test_offline_node_hit(self):
        path = self.cache.node_path(self.target.file_key, self.target.node_id)
        data = {
            "version": "v1",
            "nodes": {
                self.target.node_id: {
                    "document": {"id": self.target.node_id, "name": "Cached", "type": "FRAME", "children": []}
                }
            },
        }
        self.cache.write_json_file(path, data)
        self.cache.update_manifest(self.target.file_key, kind="node", version="v1", node_id=self.target.node_id)
        service = fs.SnapshotService(self.cache, offline=True)
        result = service.node(self.target)
        self.assertTrue(result["hit"])
        self.assertEqual(result["spent"], 0)
        self.assertEqual(result["summary"]["name"], "Cached")

    def test_offline_miss(self):
        service = fs.SnapshotService(self.cache, offline=True)
        with self.assertRaises(fs.FigmaError) as ctx:
            service.node(self.target)
        self.assertEqual(ctx.exception.code, fs.EXIT_TARGET)

    def test_offline_image_hit(self):
        path = self.cache.image_path(self.target.file_key, self.target.node_id, "png", 2.0)
        self.cache.write_bytes_file(path, b"png")
        self.cache.update_manifest(
            self.target.file_key, kind="image", version="v1", node_id=self.target.node_id, fmt="png", scale=2.0
        )
        service = fs.SnapshotService(self.cache, offline=True)
        result = service.render(self.target, fmt="png", scale=2.0)
        self.assertTrue(result["hit"])
        self.assertEqual(result["spent"], 0)


class ClientTests(unittest.TestCase):
    def test_auth_error_mapping(self):
        def fail(*args, **kwargs):
            raise urllib.error.HTTPError(
                "https://api.figma.com/v1/me",
                401,
                "Unauthorized",
                {"X-Test": "1"},
                io.BytesIO(b'{"err":"Token has expired"}'),
            )

        with mock.patch.object(fs.urllib.request, "urlopen", fail):
            with self.assertRaises(fs.FigmaError) as ctx:
                fs.FigmaClient("secret").whoami()
        self.assertEqual(ctx.exception.code, fs.EXIT_AUTH)
        self.assertIn("Token has expired", ctx.exception.message)

    def test_rate_limit_headers(self):
        def fail(*args, **kwargs):
            raise urllib.error.HTTPError(
                "https://api.figma.com/v1/me",
                429,
                "Too Many Requests",
                {"Retry-After": "60", "X-Figma-Rate-Limit-Type": "low"},
                io.BytesIO(b'{"err":"rate limited"}'),
            )

        with mock.patch.object(fs.urllib.request, "urlopen", fail):
            with self.assertRaises(fs.FigmaError) as ctx:
                fs.FigmaClient("secret").whoami()
        self.assertEqual(ctx.exception.code, fs.EXIT_NETWORK)
        self.assertIn("60", ctx.exception.message)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = fs.main(["--cache-home", self.temp.name] + args)
        return code, output.getvalue()

    def test_resolve_json(self):
        code, output = self.run_cli(["--json", "resolve", URL])
        self.assertEqual(code, fs.EXIT_OK)
        data = json.loads(output)
        self.assertEqual(data["file_key"], "b5LeA9hY1u4XAlbKXciALw")
        self.assertEqual(data["node_id"], "5150:60514")

    def test_status_json(self):
        code, output = self.run_cli(["--json", "status"])
        self.assertEqual(code, fs.EXIT_OK)
        data = json.loads(output)
        self.assertEqual(data["budget"], 20)
        self.assertEqual(data["spent"], 0)

    def test_budget_set(self):
        code, output = self.run_cli(["--json", "budget", "--set", "5"])
        self.assertEqual(code, fs.EXIT_OK)
        self.assertEqual(json.loads(output)["remaining"], 5)


if __name__ == "__main__":
    unittest.main()
