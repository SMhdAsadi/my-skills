import copy
import sys
import unittest
from pathlib import Path

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from walkthrough_schema import (
    ValidationError,
    is_safe_path,
    validate_walkthrough,
)


def make_valid_v3():
    return {
        "schemaVersion": 3,
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
        "overview": {
            "title": "Token refresh pipeline and session lock",
            "summary": [
                "Updates token expiration handling across API clients.",
                "Ensures expired tokens trigger a single deduplicated refresh.",
            ],
            "affects": "User authentication and session lifecycle",
            "split": {
                "recommendation": "Consider separating container config from token refresh logic.",
                "boundaries": ["Token refresh deduplication", "Build environment config"],
            },
            "skim": ["README.md", "Makefile"],
        },
        "slices": [
            {
                "id": "token-refresh",
                "title": "Deduplicate concurrent token refresh requests",
                "summary": [
                    "Adds an in-flight promise lock so parallel 401 responses share one refresh call."
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
                        "title": "Race condition on token refresh",
                        "body": "Multiple concurrent API calls can trigger parallel refresh requests before lock is set.",
                        "refs": [
                            {"path": "src/auth/token.ts", "startLine": 42, "endLine": 50},
                            {"path": "Dockerfile", "startLine": 10},
                            {"path": ".env.example", "startLine": 3},
                        ],
                        "lookFor": "Check if a mutex or in-flight promise deduplication is used.",
                        "extra": ["Worst case is an expired token with no refresh path."],
                    }
                ],
                "qa": [
                    "Test token expiry with expired JWT.",
                    "Verify simultaneous API calls share a single refresh promise.",
                ],
            },
            {
                "id": "session-cleanup",
                "title": "Clear cached session state on permanent refresh failure",
                "summary": [
                    "Evicts stale credentials when the refresh endpoint returns 401."
                ],
                "files": [
                    {
                        "role": "Failure Handler",
                        "path": "src/auth/token.ts",
                        "startLine": 90,
                        "endLine": 130,
                        "summary": "Clears storage and broadcasts logout event.",
                    }
                ],
                "headsUp": [],
                "qa": [],
            },
        ],
        "crossCutting": {
            "title": "Cross-Cutting Risks & Checks",
            "headsUp": [
                {
                    "title": "End-to-end session eviction ordering",
                    "body": "In-flight requests queued during refresh must fail cleanly if logout clears storage.",
                    "refs": [],
                    "lookFor": "Verify pending callers reject instead of hanging.",
                }
            ],
            "qa": ["Expire refresh token mid-flight and confirm user lands on login screen."],
        },
    }


class TestWalkthroughSchema(unittest.TestCase):
    def setUp(self):
        self.valid_data = make_valid_v3()

    def test_valid_schema_v3_passes_validation(self):
        validated = validate_walkthrough(self.valid_data)
        self.assertEqual(validated["schemaVersion"], 3)
        self.assertEqual(len(validated["slices"]), 2)

    def test_rejects_schema_versions_1_and_2(self):
        for bad_version in (1, 2, "3", True, None, 4):
            bad = copy.deepcopy(self.valid_data)
            bad["schemaVersion"] = bad_version
            with self.assertRaises(ValidationError):
                validate_walkthrough(bad)

    def test_accepts_minimal_single_slice_without_optional_fields(self):
        minimal = {
            "schemaVersion": 3,
            "lang": "en",
            "meta": {
                "title": "Rename helper",
                "branch": "refactor/helper",
                "base": "main",
                "headSha": "abc1234",
                "stats": {"files": 1, "added": 4, "removed": 4},
            },
            "overview": {
                "title": "Single-file helper rename",
                "affects": "Internal string utilities",
            },
            "slices": [
                {
                    "id": "rename-helper",
                    "title": "Rename formatSlug to normalizeSlug",
                    "summary": ["Updates the helper name and its single call site."],
                    "files": [
                        {
                            "role": "Slug helper",
                            "path": "src/utils/slug.ts",
                            "startLine": 12,
                            "summary": "Renames exported function without changing behavior.",
                        }
                    ],
                }
            ],
        }
        validated = validate_walkthrough(minimal)
        self.assertEqual(validated["schemaVersion"], 3)
        self.assertNotIn("summary", validated["overview"])
        self.assertNotIn("crossCutting", validated)

    def test_accepts_empty_overview_summary_and_zero_heads_up_and_qa(self):
        data = copy.deepcopy(self.valid_data)
        data["overview"]["summary"] = []
        del data["crossCutting"]
        data["slices"] = [data["slices"][0]]
        data["slices"][0]["headsUp"] = []
        data["slices"][0]["qa"] = []
        validated = validate_walkthrough(data)
        self.assertEqual(validated["overview"]["summary"], [])

    def test_accepts_unbounded_counts_and_long_titles(self):
        data = copy.deepcopy(self.valid_data)
        data["meta"]["title"] = "X" * 240
        data["overview"]["title"] = "Y" * 240
        data["overview"]["summary"] = [f"Paragraph {i}." for i in range(6)]
        data["overview"]["split"]["boundaries"] = [f"Boundary {i}" for i in range(12)]
        data["slices"][0]["title"] = "Z" * 240
        data["slices"][0]["files"][0]["role"] = "R" * 120
        data["slices"][0]["headsUp"] = [
            {
                "title": f"Heads up {i} " + ("long " * 40),
                "body": f"Risk details {i}.",
                "refs": [
                    {"path": f"src/f{j}.ts", "startLine": j + 1} for j in range(5)
                ],
            }
            for i in range(7)
        ]
        data["slices"][0]["qa"] = [f"Scenario {i}" for i in range(8)]
        validated = validate_walkthrough(data)
        self.assertEqual(len(validated["slices"][0]["headsUp"]), 7)
        self.assertEqual(len(validated["slices"][0]["qa"]), 8)

    def test_allows_repeated_file_path_across_slices_with_distinct_ranges(self):
        validated = validate_walkthrough(self.valid_data)
        self.assertEqual(validated["slices"][0]["files"][0]["path"], "src/auth/token.ts")
        self.assertEqual(validated["slices"][1]["files"][0]["path"], "src/auth/token.ts")
        self.assertNotEqual(
            validated["slices"][0]["files"][0]["startLine"],
            validated["slices"][1]["files"][0]["startLine"],
        )

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

    def test_rejects_parenthesized_path_prefix_in_prose(self):
        bad_hu = copy.deepcopy(self.valid_data)
        bad_hu["slices"][0]["headsUp"][0]["body"] = "(token.ts:42): Awkward leading prefix."
        with self.assertRaises(ValidationError) as ctx:
            validate_walkthrough(bad_hu)
        self.assertIn("pure prose", str(ctx.exception).lower())

        bad_file = copy.deepcopy(self.valid_data)
        bad_file["slices"][0]["files"][0]["summary"] = "(token.ts:1-80): Leading prefix."
        with self.assertRaises(ValidationError) as ctx:
            validate_walkthrough(bad_file)
        self.assertIn("pure prose", str(ctx.exception).lower())

        bad_cc = copy.deepcopy(self.valid_data)
        bad_cc["crossCutting"]["headsUp"][0]["body"] = "(token.ts:90): Cross cutting prefix."
        with self.assertRaises(ValidationError) as ctx:
            validate_walkthrough(bad_cc)
        self.assertIn("pure prose", str(ctx.exception).lower())

    def test_rejects_missing_overview_or_empty_slices(self):
        no_overview = copy.deepcopy(self.valid_data)
        del no_overview["overview"]
        with self.assertRaises(ValidationError):
            validate_walkthrough(no_overview)

        empty_slices = copy.deepcopy(self.valid_data)
        empty_slices["slices"] = []
        with self.assertRaises(ValidationError):
            validate_walkthrough(empty_slices)

        empty_files = copy.deepcopy(self.valid_data)
        empty_files["slices"][0]["files"] = []
        with self.assertRaises(ValidationError):
            validate_walkthrough(empty_files)

        empty_summary = copy.deepcopy(self.valid_data)
        empty_summary["slices"][0]["summary"] = []
        with self.assertRaises(ValidationError):
            validate_walkthrough(empty_summary)

    def test_rejects_empty_refs_in_slice_heads_up(self):
        bad = copy.deepcopy(self.valid_data)
        bad["slices"][0]["headsUp"][0]["refs"] = []
        with self.assertRaises(ValidationError):
            validate_walkthrough(bad)

        bad2 = copy.deepcopy(self.valid_data)
        del bad2["slices"][0]["headsUp"][0]["refs"]
        with self.assertRaises(ValidationError):
            validate_walkthrough(bad2)

    def test_cross_cutting_validation(self):
        # Empty crossCutting object must be rejected
        empty_cc = copy.deepcopy(self.valid_data)
        empty_cc["crossCutting"] = {"headsUp": [], "qa": []}
        with self.assertRaises(ValidationError):
            validate_walkthrough(empty_cc)

        # qa-only crossCutting is valid
        qa_only = copy.deepcopy(self.valid_data)
        qa_only["crossCutting"] = {"qa": ["End-to-end check."]}
        validated = validate_walkthrough(qa_only)
        self.assertEqual(len(validated["crossCutting"]["qa"]), 1)

        # headsUp with omitted refs in crossCutting is valid
        no_refs = copy.deepcopy(self.valid_data)
        del no_refs["crossCutting"]["headsUp"][0]["refs"]
        del no_refs["crossCutting"]["qa"]
        validated2 = validate_walkthrough(no_refs)
        self.assertEqual(len(validated2["crossCutting"]["headsUp"]), 1)

    def test_supports_all_valid_ide_names(self):
        for editor in [
            "vscode",
            "vscode-insiders",
            "cursor",
            "windsurf",
            "vscodium",
            "zed",
            "android-studio",
            "studio",
            "goland",
            "idea",
            "webstorm",
            "pycharm",
            "copy",
        ]:
            data = copy.deepcopy(self.valid_data)
            data["repo"] = {"root": "/root", "defaultEditor": editor}
            validated = validate_walkthrough(data)
            self.assertEqual(validated["repo"]["defaultEditor"], editor)

    def test_rejects_duplicate_and_non_kebab_slice_ids(self):
        dup = copy.deepcopy(self.valid_data)
        dup["slices"][1]["id"] = "token-refresh"
        with self.assertRaises(ValidationError):
            validate_walkthrough(dup)

        bad_id = copy.deepcopy(self.valid_data)
        bad_id["slices"][0]["id"] = "Invalid_ID!"
        with self.assertRaises(ValidationError) as ctx:
            validate_walkthrough(bad_id)
        self.assertIn("kebab-case", str(ctx.exception))

    def test_rejects_invalid_line_numbers_and_bool_ints(self):
        bad = copy.deepcopy(self.valid_data)
        bad["slices"][0]["headsUp"][0]["refs"] = [{"path": "file.ts", "startLine": 0}]
        with self.assertRaises(ValidationError) as ctx:
            validate_walkthrough(bad)
        self.assertIn("startLine", str(ctx.exception))

        bad["slices"][0]["headsUp"][0]["refs"] = [
            {"path": "file.ts", "startLine": 50, "endLine": 40}
        ]
        with self.assertRaises(ValidationError) as ctx:
            validate_walkthrough(bad)
        self.assertIn("endLine", str(ctx.exception))

        bad_bool = copy.deepcopy(self.valid_data)
        bad_bool["meta"]["stats"]["files"] = True
        with self.assertRaises(ValidationError):
            validate_walkthrough(bad_bool)

    def test_rejects_path_traversal_in_files_refs_and_skim(self):
        bad_ref = copy.deepcopy(self.valid_data)
        bad_ref["slices"][0]["headsUp"][0]["refs"] = [
            {"path": "../../etc/passwd", "startLine": 1}
        ]
        with self.assertRaises(ValidationError):
            validate_walkthrough(bad_ref)

        bad_file = copy.deepcopy(self.valid_data)
        bad_file["slices"][0]["files"][0]["path"] = "./src/local.ts"
        with self.assertRaises(ValidationError):
            validate_walkthrough(bad_file)

        bad_skim = copy.deepcopy(self.valid_data)
        bad_skim["overview"]["skim"] = ["/absolute/path.md"]
        with self.assertRaises(ValidationError):
            validate_walkthrough(bad_skim)

        bad_cc_ref = copy.deepcopy(self.valid_data)
        bad_cc_ref["crossCutting"]["headsUp"][0]["refs"] = [
            {"path": "../secret", "startLine": 1}
        ]
        with self.assertRaises(ValidationError):
            validate_walkthrough(bad_cc_ref)

    def test_rejects_empty_markdown_path_and_empty_default_editor(self):
        bad_md = copy.deepcopy(self.valid_data)
        bad_md["meta"]["markdownPath"] = ""
        with self.assertRaises(ValidationError):
            validate_walkthrough(bad_md)

        bad_ed = copy.deepcopy(self.valid_data)
        bad_ed["repo"]["defaultEditor"] = ""
        with self.assertRaises(ValidationError):
            validate_walkthrough(bad_ed)


if __name__ == "__main__":
    unittest.main()
