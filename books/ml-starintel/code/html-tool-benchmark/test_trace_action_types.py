"""BK08 regression: untrusted JSON actions must yield typed failures, not crash evaluation."""
from __future__ import annotations

import copy
import json
import unittest

from offline_html_trace_executor import TraceFailure, demo_records, evaluate, run_trace


class ActionTypeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.navigation = [
            row for row in demo_records() if row["family"] in {"pagination", "detail"}
        ]
        self.assertEqual({row["family"] for row in self.navigation}, {"pagination", "detail"})

    def test_nested_or_unhashable_follow_kinds_are_typed(self):
        # JSON deserialization preserves arrays and objects, including nested variants.
        invalid_kinds = ([], {}, ["next"], {"next": True}, [[]], {"x": {"y": 1}})
        for case in self.navigation:
            for kind in invalid_kinds:
                with self.subTest(family=case["family"], kind=kind):
                    actions = copy.deepcopy(case["gold_trace"])
                    actions[1]["kind"] = kind
                    with self.assertRaises(TraceFailure) as context:
                        run_trace(case["pages"], case["start"], actions)
                    self.assertEqual(context.exception.code, "invalid_action")

    def test_evaluate_catches_invalid_candidate_kind(self):
        for case in self.navigation:
            for kind in ([], {}, ["next"], {"next": "next"}):
                with self.subTest(family=case["family"], kind=kind):
                    row = copy.deepcopy(case)
                    row["candidate_trace"] = copy.deepcopy(row["gold_trace"])
                    row["candidate_trace"][1]["kind"] = kind
                    scored = evaluate([row])
                    self.assertEqual(scored["cases"][0]["failure"], "invalid_action")
                    self.assertEqual(scored["metrics"]["sequence_success"], 0)
                    self.assertEqual(scored["metrics"]["extraction_success"], 0)
                    self.assertEqual(scored["metrics"]["navigation_success"], 0)

    def test_scalar_follow_kinds_are_typed(self):
        for case in self.navigation:
            for kind in (None, 0, True, "", "NEXT", "next/../detail"):
                with self.subTest(family=case["family"], kind=kind):
                    actions = copy.deepcopy(case["gold_trace"])
                    actions[1]["kind"] = kind
                    with self.assertRaises(TraceFailure) as context:
                        run_trace(case["pages"], case["start"], actions)
                    self.assertEqual(context.exception.code, "invalid_action")

    def test_valid_follow_kinds_preserve_gold_results(self):
        for case in self.navigation:
            with self.subTest(family=case["family"]):
                actual = run_trace(case["pages"], case["start"], case["gold_trace"])
                self.assertEqual(actual["extractions"], case["gold_extractions"])
                self.assertEqual(actual["visited"], case["gold_visited"])
                self.assertEqual(evaluate([case])["metrics"]["sequence_success"], 1)

    def test_jsonl_compatible_action_round_trip(self):
        for case in self.navigation:
            row = copy.deepcopy(case)
            row["candidate_trace"] = copy.deepcopy(row["gold_trace"])
            row["candidate_trace"][1]["kind"] = {"unexpected": ["detail"]}
            round_tripped = json.loads(json.dumps(row, sort_keys=True))
            scored = evaluate([round_tripped])
            self.assertEqual(scored["cases"][0]["failure"], "invalid_action")

    def test_case_scoring_remains_deterministic(self):
        for case in self.navigation:
            row = copy.deepcopy(case)
            row["candidate_trace"] = copy.deepcopy(row["gold_trace"])
            row["candidate_trace"][1]["kind"] = ["next"]
            first = json.dumps(evaluate([row]), sort_keys=True, separators=(",", ":"))
            second = json.dumps(evaluate([row]), sort_keys=True, separators=(",", ":"))
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
