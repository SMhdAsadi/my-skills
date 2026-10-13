import unittest
import sys
from pathlib import Path

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from walkthrough_schema import (
    ValidationError,
    validate_walkthrough,
    is_safe_path,
)


class TestWalkthroughSchema(unittest.TestCase):
    def setUp(self):
        self.valid_data = {
            "schemaVersion": 2,
            "lang": "en",
            "meta": {
                "title": "Authentication Token Refresh",
                "branch": "feat/token-refresh",
                "base": "main",
                "headSha": "a1b2c3d",
                "stats": {"files": 3, "added": 45, "removed": 12},
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
                    "title": "Race condition on token refresh",
                    "category": "concurrency",
                    "body": "Multiple concurrent API calls can trigger parallel refresh requests.",
                    "refs": [
                        {"path": "src/auth/token.ts", "startLine": 42, "endLine": 50},
                        {"path": "Dockerfile", "startLine": 10},
                        {"path": ".env.example", "startLine": 3},
                    ],
                    "lookFor": "Check if a mutex or in-flight promise deduplication is used.",
                },
                {
                    "id": "reading-order",
                    "kind": "reading",
                    "section": "Reading Order",
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
                    "skim": ["README.md", "Makefile"],
                },
                {
                    "id": "what-to-test",
                    "kind": "test",
                    "section": "Verification",
                    "title": "Run these 2 checks on a device.",
                    "items": [
                        "Test token expiry with expired JWT.",
                        "Verify simultaneous API calls share a single refresh promise.",
                    ],
                },
            ],
        }

    def test_valid_data_passes_validation(self):
        validated = validate_walkthrough(self.valid_data)
        self.assertEqual(validated["schemaVersion"], 2)
        self.assertEqual(len(validated["steps"]), 4)

    def test_supports_schema_version_1_and_2(self):
        data_v1 = dict(self.valid_data)
        data_v1["schemaVersion"] = 1
        validated = validate_walkthrough(data_v1)
        self.assertEqual(validated["schemaVersion"], 1)

    def test_extensionless_and_dotfiles_are_valid_paths(self):
        self.assertTrue(is_safe_path("Dockerfile"))
        self.assertTrue(is_safe_path("Makefile"))
        self.assertTrue(is_safe_path(".env"))
        self.assertTrue(is_safe_path(".env.production"))
        self.assertTrue(is_safe_path("bin/run-service"))
        self.assertTrue(is_safe_path("scripts/deploy"))
        self.assertTrue(is_safe_path("src/auth/token.ts"))

        self.assertFalse(is_safe_path("/absolute/path"))
        self.assertFalse(is_safe_path("./relative/path"))
        self.assertFalse(is_safe_path("../parent/path"))
        self.assertFalse(is_safe_path("path/with/../traversal"))
        self.assertFalse(is_safe_path("path\\with\\backslash"))
        self.assertFalse(is_safe_path(""))

    def test_rejects_parenthesized_path_prefix_in_gotcha_body(self):
        bad_data = dict(self.valid_data)
        bad_data["steps"] = [dict(s) for s in self.valid_data["steps"]]
        bad_data["steps"][1]["body"] = "(token.ts:42): This body starts with an awkward path prefix."
        with self.assertRaises(ValidationError) as ctx:
            validate_walkthrough(bad_data)
        self.assertIn("pure prose", str(ctx.exception).lower())

    def test_rejects_parenthesized_path_prefix_in_reading_summary(self):
        bad_data = dict(self.valid_data)
        bad_data["steps"] = [dict(s) for s in self.valid_data["steps"]]
        bad_data["steps"][2]["items"][0]["summary"] = "(token.ts:1-80): Leading path prefix in summary."
        with self.assertRaises(ValidationError) as ctx:
            validate_walkthrough(bad_data)
        self.assertIn("pure prose", str(ctx.exception).lower())

    def test_rejects_invalid_step_order(self):
        bad_data = dict(self.valid_data)
        # Put reading before gotcha
        steps = list(self.valid_data["steps"])
        steps[1], steps[2] = steps[2], steps[1]
        bad_data["steps"] = steps
        with self.assertRaises(ValidationError):
            validate_walkthrough(bad_data)

    def test_rejects_missing_scope_first(self):
        bad_data = dict(self.valid_data)
        bad_data["steps"] = self.valid_data["steps"][1:]
        with self.assertRaises(ValidationError):
            validate_walkthrough(bad_data)

    def test_rejects_missing_test_last(self):
        bad_data = dict(self.valid_data)
        bad_data["steps"] = self.valid_data["steps"][:-1]
        with self.assertRaises(ValidationError):
            validate_walkthrough(bad_data)

    def test_allows_optional_split_step(self):
        split_step = {
            "id": "split",
            "kind": "split",
            "section": "Split Recommendation",
            "title": "Large change — split domain logic from presentation.",
            "recommendation": "Separate the auth service migration from UI updates.",
            "boundaries": ["Auth token service", "Login UI view"],
        }
        data_with_split = dict(self.valid_data)
        data_with_split["steps"] = [
            self.valid_data["steps"][0],
            split_step,
            self.valid_data["steps"][1],
            self.valid_data["steps"][2],
            self.valid_data["steps"][3],
        ]
        validated = validate_walkthrough(data_with_split)
        self.assertEqual(len(validated["steps"]), 5)
        self.assertEqual(validated["steps"][1]["kind"], "split")

    def test_supports_new_ide_names(self):
        for editor in ["vscode", "cursor", "windsurf", "zed", "android-studio", "studio", "goland", "idea", "webstorm", "pycharm", "copy"]:
            data = dict(self.valid_data)
            data["repo"] = {"root": "/root", "defaultEditor": editor}
            validated = validate_walkthrough(data)
            self.assertEqual(validated["repo"]["defaultEditor"], editor)

    def test_rejects_duplicate_step_ids(self):
        bad_data = dict(self.valid_data)
        bad_data["steps"] = [dict(s) for s in self.valid_data["steps"]]
        bad_data["steps"][1]["id"] = "scope"  # duplicate
        with self.assertRaises(ValidationError):
            validate_walkthrough(bad_data)

    def test_rejects_empty_refs_in_gotcha(self):
        bad_data = dict(self.valid_data)
        bad_data["steps"] = [dict(s) for s in self.valid_data["steps"]]
        bad_data["steps"][1]["refs"] = []
        with self.assertRaises(ValidationError):
            validate_walkthrough(bad_data)

    def test_rejects_invalid_line_numbers(self):
        bad_data = dict(self.valid_data)
        bad_data["steps"] = [dict(s) for s in self.valid_data["steps"]]
        bad_data["steps"][1]["refs"] = [{"path": "file.ts", "startLine": 0}]
        with self.assertRaises(ValidationError) as ctx:
            validate_walkthrough(bad_data)
        self.assertIn("startLine", str(ctx.exception))

        bad_data["steps"][1]["refs"] = [{"path": "file.ts", "startLine": 50, "endLine": 40}]
        with self.assertRaises(ValidationError) as ctx:
            validate_walkthrough(bad_data)
        self.assertIn("endLine", str(ctx.exception))

    def test_rejects_title_exceeding_max_length(self):
        bad_data = dict(self.valid_data)
        bad_data["steps"] = [dict(s) for s in self.valid_data["steps"]]
        bad_data["steps"][1]["title"] = "X" * 161
        with self.assertRaises(ValidationError) as ctx:
            validate_walkthrough(bad_data)
        self.assertIn("160", str(ctx.exception))

    def test_rejects_path_traversal_in_refs_and_skim(self):
        bad_data = dict(self.valid_data)
        bad_data["steps"] = [dict(s) for s in self.valid_data["steps"]]
        bad_data["steps"][1]["refs"] = [{"path": "../../etc/passwd", "startLine": 1}]
        with self.assertRaises(ValidationError):
            validate_walkthrough(bad_data)

        bad_data["steps"][1]["refs"] = [{"path": "src/valid.ts", "startLine": 1}]
        bad_data["steps"][2]["skim"] = ["/absolute/path.md"]
        with self.assertRaises(ValidationError):
            validate_walkthrough(bad_data)

    def test_rejects_non_kebab_case_step_ids(self):
        bad_data = dict(self.valid_data)
        bad_data["steps"] = [dict(s) for s in self.valid_data["steps"]]
        bad_data["steps"][1]["id"] = "Invalid_ID!"
        with self.assertRaises(ValidationError) as ctx:
            validate_walkthrough(bad_data)
        self.assertIn("kebab-case", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
