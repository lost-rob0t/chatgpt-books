"""BK08: independently observed failure dimensions, without inventing failures on invalid traces."""
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


class MultiLabelFailureDiagnosticsTests(unittest.TestCase):
    @staticmethod
    def specimen(family: str = "tables") -> dict:
        row = copy.deepcopy(next(r for r in demo_records() if r["family"] == family))
        row["candidate_trace"] = copy.deepcopy(row["gold_trace"])
        return row

    def test_valid_trace_reports_all_three_independent_mismatches(self):
        row = self.specimen("pagination")
        row["candidate_trace"] = [
            {"op": "select", "selector": "a#next-page"},
            {"op": "extract", "field": "name"},
        ]
        scored = evaluate([row])
        case = scored["cases"][0]
        self.assertEqual(case["observed"]["extractions"], {"name": "Next"})
        self.assertEqual(case["observed"]["visited"], ["/pages/one.html"])
        self.assertEqual(case["failure"], "extraction_mismatch")
        self.assertEqual(case["failure_reasons"], [
            "extraction_mismatch", "navigation_mismatch", "sequence_mismatch"])
        self.assertEqual(scored["failure_reason_counts"], {
            "extraction_mismatch": 1, "navigation_mismatch": 1, "sequence_mismatch": 1})

    def test_only_sequence_deviates_when_same_node_has_other_selector(self):
        row = self.specimen("tables")
        row["candidate_trace"][0]["selector"] = "#table-name"
        case = evaluate([row])["cases"][0]
        self.assertEqual(case["extraction_success"], 1)
        self.assertEqual(case["navigation_success"], 1)
        self.assertEqual(case["sequence_success"], 0)
        self.assertEqual(case["failure"], "sequence_mismatch")
        self.assertEqual(case["failure_reasons"], ["sequence_mismatch"])

    def test_navigation_and_sequence_fail_without_extraction_failure(self):
        row = self.specimen("tables")
        row["pages"]["/tables/index.html"] += "<a id='go' href='other.html'>Next</a>"
        row["pages"]["/tables/other.html"] = "<p id='other-name'>Ada</p>"
        row["candidate_trace"] = [
            {"op": "select", "selector": "#go"},
            {"op": "follow", "kind": "next"},
            {"op": "select", "selector": "#other-name"},
            {"op": "extract", "field": "name"},
        ]
        case = evaluate([row])["cases"][0]
        self.assertEqual(case["extraction_success"], 1)
        self.assertEqual(case["navigation_success"], 0)
        self.assertEqual(case["failure"], "navigation_mismatch")
        self.assertEqual(case["failure_reasons"], ["navigation_mismatch", "sequence_mismatch"])

    def test_invalid_candidate_has_only_observed_typed_failure(self):
        row = self.specimen()
        row["candidate_trace"] = [
            {"op": "select", "selector": "#table-name"},
            {"op": "extract", "field": "name"},
            {"op": "select", "selector": "#nonexistent"},
        ]
        case = evaluate([row])["cases"][0]
        self.assertEqual(case["failure"], "selector_zero")
        self.assertEqual(case["failure_reasons"], ["selector_zero"])
        self.assertEqual(case["observed"]["extractions"], {})
        self.assertEqual(case["field_value_f1"], 0)

    def test_invalid_action_does_not_fabricate_secondary_mismatches(self):
        row = self.specimen()
        row["candidate_trace"] = [{"op": "extract", "field": "name"}]
        case = evaluate([row])["cases"][0]
        self.assertEqual(case["failure"], "invalid_action")
        self.assertEqual(case["failure_reasons"], ["invalid_action"])

    def test_clean_run_has_empty_reasons_and_no_failure_counts(self):
        row = self.specimen()
        scored = evaluate([row])
        self.assertIsNone(scored["cases"][0]["failure"])
        self.assertEqual(scored["cases"][0]["failure_reasons"], [])
        self.assertEqual(scored["failure_reason_counts"], {})

    def test_counted_reasons_are_multilabel_not_sample_partition(self):
        rows = [self.specimen(), self.specimen("pagination"), self.specimen(), self.specimen()]
        for i, row in enumerate(rows):
            row["id"] = f"variant_{i}"
        rows[1]["candidate_trace"] = [
            {"op": "select", "selector": "#next-page"},
            {"op": "extract", "field": "name"},
        ]
        rows[2]["candidate_trace"][0]["selector"] = "#table-name"
        rows[3]["candidate_trace"] = [{"op": "extract", "field": "name"}]
        scored = evaluate(rows)
        self.assertEqual(scored["samples"], 4)
        self.assertEqual(scored["failure_reason_counts"], {
            "extraction_mismatch": 1,
            "invalid_action": 1,
            "navigation_mismatch": 1,
            "sequence_mismatch": 2,
        })
        self.assertGreater(sum(scored["failure_reason_counts"].values()), scored["samples"])
        self.assertEqual(scored, evaluate(list(reversed(rows))))

    def test_report_schema_and_prior_metrics_are_preserved(self):
        result = evaluate(demo_records())
        self.assertEqual(result["schema"], "bk08.static-html-execution/v4")
        self.assertEqual(result["metrics"]["extraction_success"], .8)
        self.assertEqual(result["metrics"]["field_value_f1"], .8)
        self.assertEqual(result["metrics"]["sequence_success"], .8)
        self.assertEqual(result["failure_reason_counts"], {"selector_zero": 1})

    def test_cross_split_audit_exposes_reason_counts_after_leakage_gate(self):
        report = audit_and_evaluate(demo_partitions())
        self.assertEqual(report["schema"], "bk08.template-held-out/v4")
        self.assertEqual(report["splits"]["train"]["failure_reason_counts"], {})
        self.assertEqual(report["splits"]["dev"]["failure_reason_counts"], {"selector_zero": 1})
        self.assertEqual(report["splits"]["test"]["failure_reason_counts"], {})

    def test_baselines_report_primary_and_multilabel_counts_separately(self):
        report = run_bench(projected_partitions())
        self.assertEqual(report["schema"], "bk08.heldout-node-baselines/v4")
        for method in report["baselines"].values():
            for split in method.values():
                self.assertEqual(sum(split["failure_counts"].values()), split["samples"])
                self.assertIn("failure_reason_counts", split)
        dev = report["baselines"]["train_only_node_ranker"]["dev"]
        self.assertEqual(dev["failure_counts"], {"extraction_mismatch": 24})
        self.assertEqual(dev["failure_reason_counts"], {
            "extraction_mismatch": 24, "navigation_mismatch": 24, "sequence_mismatch": 24})

    def test_all_three_demo_clis_are_deterministic_and_versioned(self):
        here = Path(__file__).resolve().parent
        cases = (
            ("offline_html_trace_executor.py", "schema", "bk08.static-html-execution/v4"),
            ("html_template_split_audit.py", "audit", "bk08.template-held-out/v4"),
            ("html_heldout_baselines.py", "report", "bk08.heldout-node-baselines/v4"),
        )
        for filename, key, version in cases:
            with self.subTest(script=filename):
                args = [sys.executable, str(here / filename), "--demo"]
                first = subprocess.run(args, check=True, capture_output=True).stdout
                second = subprocess.run(args, check=True, capture_output=True).stdout
                self.assertEqual(first, second)
                data = json.loads(first)
                payload = data if key == "schema" else data[key]
                self.assertEqual(payload["schema"], version)


if __name__ == "__main__":
    unittest.main()
