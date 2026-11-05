#!/usr/bin/env python3
"""Batch plan ingestion and evidence verification for mr-comment-triage v2."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import helpers  # noqa: E402
import _common  # noqa: E402
import triage_state as state_cmd  # noqa: E402


def run_state(case: helpers.RepoCase, *argv):
    cap = helpers.capture()
    cap.run(state_cmd.main, ["--state", str(case.state_path), *argv])
    return cap


def plan_item(**overrides) -> dict:
    """One plan-document item, already valid against the RepoCase checkout."""
    item = {
        "threadIds": ["gl:d1"],
        "verdict": "ACCEPT",
        "severity": "blocking",
        "claim": "The guard is missing.",
        "evidence": ["src/app.py:3:no guard"],
        "action": "Add the guard.",
        "replyDraft": "Added the guard.",
    }
    item.update(overrides)
    return item


class PlanCase(helpers.RepoCase):
    def write_plan(self, payload, name: str = "plan.json") -> Path:
        path = self.tmp_path / name
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def plan(self, payload, *argv, name: str = "plan.json"):
        path = self.write_plan(payload, name)
        return run_state(self, "plan", "--from", str(path), *argv)


class PlanIngestionTests(PlanCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.write_state()

    def test_array_plan_writes_every_item_and_prints_the_table(self):
        cap = self.plan(
            [
                plan_item(),
                plan_item(
                    threadIds=["gl:d2"],
                    verdict="PUSH_BACK",
                    severity=None,
                    evidence=[{"path": "src/app.py", "line": 12}],
                    action="",
                    replyDraft="Not a bug: the caller validates first.",
                ),
            ]
        )
        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertIn("2 item", cap.stdout)
        self.assertIn("| # | Anchor | Verdict | Severity | Status | Proposed action |", cap.stdout)
        self.assertIn("| 1 |", cap.stdout)
        self.assertIn("| 2 |", cap.stdout)

        state = self.read_state()
        self.assertEqual([item["n"] for item in state["items"]], [1, 2])
        first, second = state["items"]
        self.assertEqual(first["status"], "proposed")
        self.assertEqual(first["severity"], "blocking")
        self.assertEqual(
            first["evidence"],
            [{"path": "src/app.py", "line": 3, "note": "no guard"}],
        )
        self.assertEqual(first["posts"], [])
        self.assertIsNone(first["approvedAt"])
        self.assertIsNone(first["approvalHash"])
        self.assertEqual(second["severity"], "correctness")
        self.assertEqual(second["verdict"], "PUSH_BACK")
        self.assertEqual(
            second["evidence"], [{"path": "src/app.py", "line": 12, "note": ""}]
        )
        self.assertEqual(state["events"][-1]["type"], "planned")
        self.assertNotIn("approved", [event["type"] for event in state["events"]])

    def test_object_document_with_items_is_accepted(self):
        cap = self.plan({"generatedBy": "reviewer", "items": [plan_item()]})
        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual([item["n"] for item in self.read_state()["items"]], [1])

    def test_plan_replaces_items_wholesale(self):
        self.write_state(items=[helpers.make_item(7)])
        cap = self.plan([plan_item()])
        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual([item["n"] for item in self.read_state()["items"]], [1])

    def test_missing_numbers_are_assigned_by_position(self):
        cap = self.plan(
            [plan_item(), plan_item(threadIds=["gl:d2"])]
        )
        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual([item["n"] for item in self.read_state()["items"]], [1, 2])

    def test_explicit_numbers_are_kept(self):
        cap = self.plan([plan_item(n=5)])
        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual([item["n"] for item in self.read_state()["items"]], [5])

    def test_duplicate_thread_within_an_item_is_deduped_in_order(self):
        cap = self.plan(
            [plan_item(threadIds=["gl:d1", "gl:d2", "gl:d1"])]
        )
        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual(
            self.read_state()["items"][0]["threadIds"], ["gl:d1", "gl:d2"]
        )

    def test_dry_run_prints_the_table_without_writing(self):
        self.write_state(items=[helpers.make_item(7)])
        before = self.state_path.read_bytes()
        cap = self.plan([plan_item()], "--dry-run")
        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertIn("1 item", cap.stdout)
        self.assertIn("| # | Anchor |", cap.stdout)
        self.assertIn("dry run", cap.stdout.lower())
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertNotIn("planned", [event["type"] for event in self.read_state()["events"]])

    def test_empty_plan_is_valid_and_clears_items(self):
        self.write_state(items=[helpers.make_item(7)])
        cap = self.plan({"items": []})
        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertIn("0 item", cap.stdout)
        self.assertEqual(self.read_state()["items"], [])


class PlanRejectionTests(PlanCase, unittest.TestCase):
    """Every rejection leaves the state file byte-identical."""

    def reject(self, payload, expected: str):
        self.write_state(items=[helpers.make_item(7)])
        before = self.state_path.read_bytes()
        cap = self.plan(payload)
        self.assertEqual(cap.code, 1, cap.stdout)
        self.assertIn(expected.lower(), cap.stderr.lower())
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertEqual(self.read_state()["items"][0]["n"], 7)

    def test_unknown_thread_id(self):
        self.reject([plan_item(threadIds=["gl:nope"])], "unknown thread id")

    def test_duplicate_item_number(self):
        self.reject(
            [plan_item(n=1), plan_item(n=1, threadIds=["gl:d2"])],
            "duplicate item number",
        )

    def test_zero_item_number(self):
        self.reject([plan_item(n=0)], "positive integer")

    def test_negative_item_number(self):
        self.reject([plan_item(n=-2)], "positive integer")

    def test_string_item_number(self):
        self.reject([plan_item(n="1")], "positive integer")

    def test_unknown_verdict(self):
        self.reject([plan_item(verdict="MAYBE")], "verdict")

    def test_missing_verdict(self):
        item = plan_item()
        item.pop("verdict")
        self.reject([item], "verdict")

    def test_unknown_severity(self):
        self.reject([plan_item(severity="critical")], "severity")

    def test_missing_thread_ids(self):
        item = plan_item()
        item.pop("threadIds")
        self.reject([item], "threadids")

    def test_empty_thread_ids(self):
        self.reject([plan_item(threadIds=[])], "threadids")

    def test_code_verdict_requires_an_action(self):
        self.reject([plan_item(action="   ")], "action")

    def test_code_verdict_requires_the_action_field(self):
        item = plan_item()
        item.pop("action")
        self.reject([item], "action")

    def test_reply_only_verdict_requires_a_reply_draft(self):
        self.reject(
            [plan_item(verdict="PUSH_BACK", action="", replyDraft="  ")],
            "replydraft",
        )

    def test_evidence_must_be_a_list(self):
        self.reject([plan_item(evidence="src/app.py:3")], "evidence")

    def test_evidence_entry_must_be_a_string_or_an_object(self):
        self.reject([plan_item(evidence=[3])], "evidence")

    def test_evidence_string_needs_a_line(self):
        self.reject([plan_item(evidence=["src/app.py"])], "evidence")

    def test_evidence_path_must_exist_at_head(self):
        self.reject([plan_item(evidence=["src/missing.py:1"])], "src/missing.py")

    def test_evidence_line_must_be_within_the_file(self):
        self.reject([plan_item(evidence=["src/app.py:13"])], "past the end")

    def test_evidence_line_must_be_positive(self):
        self.reject([plan_item(evidence=["src/app.py:0"])], "positive")

    def test_evidence_object_line_must_be_an_int(self):
        self.reject(
            [plan_item(evidence=[{"path": "src/app.py", "line": "3"}])], "line"
        )

    def test_same_thread_in_two_items_rejects(self):
        self.reject(
            [plan_item(), plan_item(threadIds=["gl:d1"], verdict="PUSH_BACK", action="")],
            "gl:d1",
        )

    def test_item_must_be_an_object(self):
        self.reject(["not an item"], "object")

    def test_unknown_top_level_document_is_rejected(self):
        self.reject({"threads": []}, "items")

    def test_items_must_be_a_list(self):
        self.reject({"items": 5}, "items")

    def test_invalid_json_is_rejected(self):
        self.reject("{not json", "json")

    def test_missing_plan_file_is_rejected(self):
        self.write_state()
        before = self.state_path.read_bytes()
        cap = run_state(
            self, "plan", "--from", str(self.tmp_path / "does-not-exist.json")
        )
        self.assertEqual(cap.code, 1)
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_one_bad_item_rejects_the_whole_plan(self):
        self.write_state()
        good = plan_item()
        bad = plan_item(threadIds=["gl:nope"], verdict="ACCEPT")
        cap = self.plan([good, bad])
        self.assertEqual(cap.code, 1)
        self.assertEqual(self.read_state()["items"], [])
        self.assertEqual(self.read_state()["events"], [])


class EvidenceVerificationTests(PlanCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.write_state()

    def test_string_and_object_evidence_are_normalized(self):
        cap = self.plan(
            [
                plan_item(
                    evidence=[
                        "src/app.py:1:first line",
                        {"path": "src/app.py", "line": 12, "note": "last line"},
                    ]
                )
            ]
        )
        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual(
            self.read_state()["items"][0]["evidence"],
            [
                {"path": "src/app.py", "line": 1, "note": "first line"},
                {"path": "src/app.py", "line": 12, "note": "last line"},
            ],
        )

    def test_evidence_is_checked_against_the_repo_root_not_the_cwd(self):
        self.write_state()
        path = self.write_plan([plan_item(evidence=["src/app.py:2"])])
        try:
            os.chdir(self.root / "src")
            cap = run_state(self, "plan", "--from", str(path))
        finally:
            os.chdir(self.root)
        self.assertEqual(cap.code, 0, cap.stderr)

    def test_verify_evidence_helper_accepts_entries_at_head(self):
        entries = _common.verify_evidence(
            ["src/app.py:4:why", {"path": "src/app.py", "line": 5}], self.root
        )
        self.assertEqual(
            entries,
            [
                {"path": "src/app.py", "line": 4, "note": "why"},
                {"path": "src/app.py", "line": 5, "note": ""},
            ],
        )

    def test_verify_evidence_helper_rejects_a_missing_path(self):
        with self.assertRaises(_common.ScriptError):
            _common.verify_evidence(["src/nope.py:1"], self.root)

    def test_verify_evidence_helper_rejects_a_path_outside_the_repo(self):
        with self.assertRaises(_common.ScriptError):
            _common.verify_evidence(["../outside.py:1"], self.root)


class ApproveEvidenceGateTests(PlanCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.write_state()

    def test_approve_refuses_evidence_past_the_end_of_the_file(self):
        self.write_state(
            items=[
                helpers.make_item(
                    1, evidence=[{"path": "src/app.py", "line": 99, "note": "typo"}]
                )
            ]
        )
        before = self.state_path.read_bytes()
        cap = run_state(self, "approve", "1")
        self.assertEqual(cap.code, 1)
        self.assertIn("src/app.py", cap.stderr)
        self.assertIn("past the end", cap.stderr.lower())
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertEqual(self.read_state()["items"][0]["status"], "proposed")
        self.assertIsNone(self.read_state()["items"][0]["approvalHash"])

    def test_approve_refuses_a_missing_evidence_path(self):
        self.write_state(
            items=[
                helpers.make_item(
                    1, evidence=[{"path": "src/missing.py", "line": 1, "note": ""}]
                )
            ]
        )
        cap = run_state(self, "approve", "1")
        self.assertEqual(cap.code, 1)
        self.assertIn("src/missing.py", cap.stderr)
        self.assertEqual(self.read_state()["items"][0]["status"], "proposed")

    def test_approve_accepts_evidence_at_head(self):
        self.write_state(
            items=[
                helpers.make_item(
                    1, evidence=[{"path": "src/app.py", "line": 12, "note": "ok"}]
                )
            ]
        )
        cap = run_state(self, "approve", "1")
        self.assertEqual(cap.code, 0, cap.stderr)
        self.assertEqual(self.read_state()["items"][0]["status"], "approved")

    def test_held_reply_only_items_do_not_block_the_batch(self):
        self.write_state(
            items=[
                helpers.make_item(1),
                helpers.make_item(
                    2,
                    verdict="CLARIFY",
                    action="",
                    replyDraft="Which behaviour?",
                    evidence=[{"path": "src/missing.py", "line": 1, "note": ""}],
                ),
            ]
        )
        cap = run_state(self, "approve", "all")
        self.assertEqual(cap.code, 0, cap.stderr)
        items = {item["n"]: item for item in self.read_state()["items"]}
        self.assertEqual(items[1]["status"], "approved")
        self.assertEqual(items[2]["status"], "proposed")


if __name__ == "__main__":
    unittest.main()
