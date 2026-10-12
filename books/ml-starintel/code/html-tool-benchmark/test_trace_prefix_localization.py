"""BK08: exact first-divergence localization without inventing execution success."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from html_heldout_baselines import projected_partitions, run_bench
from html_template_split_audit import audit_and_evaluate, demo_partitions
from offline_html_trace_executor import demo_records, evaluate


class TracePrefixLocalizationTests(unittest.TestCase):
    @staticmethod
    def specimen(family="tables"):
        row = copy.deepcopy(next(x for x in demo_records() if x["family"] == family))
        row["candidate_trace"] = copy.deepcopy(row["gold_trace"])
        return row

    def test_perfect_trace_has_full_prefix_and_no_divergence(self):
        case = evaluate([self.specimen()])["cases"][0]
        self.assertEqual(case["gold_prefix_fraction"], 1.0)
        self.assertIsNone(case["first_divergence_index"])
        self.assertEqual(case["sequence_success"], 1)

    def test_early_and_late_error_share_exact_call_score_but_not_prefix(self):
        early = self.specimen()
        early["candidate_trace"][0]["selector"] = "#missing"
        late = self.specimen()
        late["candidate_trace"][1]["field"] = "other"
        cases = [evaluate([row])["cases"][0] for row in (early, late)]
        self.assertEqual([x["exact_call_accuracy"] for x in cases], [.5, .5])
        self.assertEqual([x["gold_prefix_fraction"] for x in cases], [0.0, .5])
        self.assertEqual([x["first_divergence_index"] for x in cases], [0, 1])

    def test_missing_final_action_diverges_at_candidate_end(self):
        row = self.specimen()
        row["candidate_trace"] = row["candidate_trace"][:1]
        case = evaluate([row])["cases"][0]
        self.assertEqual(case["gold_prefix_fraction"], .5)
        self.assertEqual(case["first_divergence_index"], 1)
        self.assertEqual(case["extraction_success"], 0)

    def test_extra_action_after_complete_gold_retains_full_prefix_not_success(self):
        row = self.specimen()
        row["candidate_trace"].append({"op": "select", "selector": "#table-name"})
        case = evaluate([row])["cases"][0]
        self.assertEqual(case["gold_prefix_fraction"], 1.0)
        self.assertEqual(case["first_divergence_index"], len(row["gold_trace"]))
        self.assertEqual(case["exact_call_accuracy"], .666667)
        self.assertEqual(case["sequence_success"], 0)
        self.assertEqual(case["failure_reasons"], ["sequence_mismatch"])

    def test_invalid_after_correct_prefix_is_not_executed_success(self):
        row = self.specimen()
        row["candidate_trace"][1] = {"op": "follow", "kind": "next"}
        case = evaluate([row])["cases"][0]
        self.assertEqual(case["gold_prefix_fraction"], .5)
        self.assertEqual(case["first_divergence_index"], 1)
        self.assertEqual(case["failure_reasons"], ["invalid_action"])
        self.assertEqual(case["observed"]["extractions"], {})
        self.assertEqual(case["extraction_success"], 0)

    def test_wrong_first_operation_stays_zero_even_if_second_matches(self):
        row = self.specimen()
        row["candidate_trace"][0]["selector"] = "#wrong"
        case = evaluate([row])["cases"][0]
        self.assertEqual(case["exact_call_accuracy"], .5)
        self.assertEqual(case["gold_prefix_fraction"], 0.0)
        self.assertEqual(case["first_divergence_index"], 0)

    def test_equivalent_selector_has_no_exact_action_prefix_credit(self):
        row = self.specimen()
        row["candidate_trace"][0]["selector"] = "#table-name"
        case = evaluate([row])["cases"][0]
        self.assertEqual(case["gold_prefix_fraction"], 0.0)
        self.assertEqual(case["extraction_success"], 1)
        self.assertEqual(case["failure_reasons"], ["sequence_mismatch"])

    def test_four_action_navigation_detects_middle_divergence(self):
        row = self.specimen("pagination")
        row["candidate_trace"][2]["selector"] = "#wrong"
        case = evaluate([row])["cases"][0]
        self.assertEqual(case["first_divergence_index"], 2)
        self.assertEqual(case["gold_prefix_fraction"], .5)
        self.assertEqual(case["exact_call_accuracy"], .75)
        self.assertEqual(case["failure_reasons"], ["selector_zero"])

    def test_empty_candidate_locates_divergence_at_zero(self):
        row = self.specimen()
        row["candidate_trace"] = []
        case = evaluate([row])["cases"][0]
        self.assertEqual(case["gold_prefix_fraction"], 0.0)
        self.assertEqual(case["first_divergence_index"], 0)
        self.assertEqual(case["sequence_success"], 0)

    def test_aggregate_is_mean_of_per_example_prefix_not_last_case(self):
        one = self.specimen()
        two = self.specimen()
        two["id"] = "tables_02"
        two["candidate_trace"][0]["selector"] = "#wrong"
        measured = evaluate([one, two])
        self.assertEqual(measured["metrics"]["gold_prefix_fraction"], .5)
        self.assertEqual(measured, evaluate(list(reversed([one, two]))))

    def test_demo_has_new_version_and_distinguishes_prefix_from_exact_calls(self):
        measured = evaluate(demo_records())
        self.assertEqual(measured["schema"], "bk08.static-html-execution/v4")
        self.assertEqual(measured["metrics"]["gold_prefix_fraction"], .8)
        self.assertEqual(measured["metrics"]["exact_call_accuracy"], .9)
        self.assertEqual(measured["metrics"]["sequence_success"], .8)

    def test_pre_scored_template_partitions_forward_gold_prefix_metric(self):
        output = audit_and_evaluate(demo_partitions())
        self.assertEqual(output["schema"], "bk08.template-held-out/v4")
        self.assertEqual([output["splits"][key]["metrics"]["gold_prefix_fraction"]
                          for key in ("train", "dev", "test")], [1.0, 0.0, 1.0])

    def test_train_only_baselines_emit_metric_without_extra_labels(self):
        output = run_bench(projected_partitions())
        self.assertEqual(output["schema"], "bk08.heldout-node-baselines/v4")
        self.assertEqual(output["ranker_fit"]["train_examples"], 24)
        for method in output["baselines"].values():
            for partition in method.values():
                self.assertIn("gold_prefix_fraction", partition["metrics"])
                self.assertTrue(0 <= partition["metrics"]["gold_prefix_fraction"] <= 1)

    def test_all_three_clis_are_stable_and_report_versioned_prefix(self):
        base = Path(__file__).resolve().parent
        for script, key in (("offline_html_trace_executor.py", None),
                            ("html_template_split_audit.py", "audit"),
                            ("html_heldout_baselines.py", "report")):
            with self.subTest(script=script):
                command = [sys.executable, str(base / script), "--demo"]
                a = subprocess.run(command, capture_output=True, check=True).stdout
                b = subprocess.run(command, capture_output=True, check=True).stdout
                self.assertEqual(a, b)
                payload = json.loads(a)
                if key is None:
                    metrics = payload["metrics"]
                elif key == "audit":
                    metrics = payload["audit"]["splits"]["train"]["metrics"]
                else:
                    metrics = payload["report"]["baselines"]["static_heuristic"]["train"]["metrics"]
                self.assertIn("gold_prefix_fraction", metrics)


if __name__ == "__main__":
    unittest.main()
