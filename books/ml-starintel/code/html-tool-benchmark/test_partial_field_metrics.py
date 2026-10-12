"""BK08 native tests: exact field/value partial metrics, not fuzzy matches."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from offline_html_trace_executor import demo_records, evaluate
from html_template_split_audit import audit_and_evaluate, demo_partitions


class PartialFieldMetricTests(unittest.TestCase):
    def record(self):
        gold = [{"op": "select", "selector": "#first"}, {"op": "extract", "field": "first"},
                {"op": "select", "selector": "#second"}, {"op": "extract", "field": "second"}]
        return {"id": "multi_01", "family": "multi", "pages": {
                "/x.html": "<p id='first'>Ada</p><p id='second'>Grace</p><p id='noise'>Wrong</p>"},
                "start": "/x.html", "gold_trace": gold, "candidate_trace": copy.deepcopy(gold),
                "gold_extractions": {"first": "Ada", "second": "Grace"}, "gold_visited": ["/x.html"]}

    def test_precision_recall_matrix_preserves_binary_success(self):
        for name, edit, expected, binary in (
            ("exact", lambda r: None, (1, 1, 1), 1),
            ("wrong_value", lambda r: r["candidate_trace"][2].update(selector="#noise"), (.5, .5, .5), 0),
            ("missing", lambda r: r.update(candidate_trace=r["candidate_trace"][:2]),
             (1, .5, .666667), 0),
            ("spurious", lambda r: r["candidate_trace"].extend([
                {"op": "select", "selector": "#noise"}, {"op": "extract", "field": "extra"}]),
             (.666667, 1, .8), 0),
            ("all_wrong", lambda r: (r["candidate_trace"][0].update(selector="#noise"),
                                     r["candidate_trace"][2].update(selector="#noise")), (0, 0, 0), 0),
        ):
            with self.subTest(name=name):
                row = self.record()
                edit(row)
                case = evaluate([row])["cases"][0]
                self.assertEqual(tuple(case[key] for key in
                    ("field_value_precision", "field_value_recall", "field_value_f1")), expected)
                self.assertEqual(case["extraction_success"], binary)

    def test_invalid_trace_is_fail_closed_not_partially_credited(self):
        row = self.record()
        row["candidate_trace"] = row["candidate_trace"][:2] + [
            {"op": "select", "selector": "#missing"}]
        case = evaluate([row])["cases"][0]
        self.assertEqual(case["failure"], "selector_zero")
        self.assertEqual([case[x] for x in ("field_value_precision", "field_value_recall", "field_value_f1")],
                         [0, 0, 0])

    def test_noop_candidate_receives_zero_partial_credit(self):
        row = self.record()
        row["candidate_trace"] = []
        case = evaluate([row])["cases"][0]
        self.assertEqual(case["field_value_f1"], 0)
        self.assertEqual(case["extraction_success"], 0)

    def test_visually_equivalent_unicode_values_are_not_exact_matches(self):
        row = self.record()
        row["pages"]["/x.html"] = (
            "<p id='first'>Ada</p><p id='second'>caf\u00e9</p><p id='noise'>cafe\u0301</p>")
        row["gold_extractions"]["second"] = "caf\u00e9"
        row["candidate_trace"][2]["selector"] = "#noise"
        case = evaluate([row])["cases"][0]
        self.assertEqual(case["field_value_f1"], .5)
        self.assertEqual(case["observed"]["extractions"]["second"], "cafe\u0301")

    def test_aggregate_is_per_example_mean_not_field_weighted(self):
        a, b = self.record(), self.record()
        b["id"] = "multi_02"
        b["candidate_trace"] = b["candidate_trace"][:2]
        result = evaluate([a, b])
        self.assertEqual((result["metrics"]["field_value_precision"],
                          result["metrics"]["field_value_recall"],
                          result["metrics"]["field_value_f1"]), (1, .75, .833333))
        self.assertEqual(result["metrics"]["extraction_success"], .5)
        self.assertEqual(result, evaluate([b, a]))

    def test_demo_and_split_auditor_keep_original_strict_gates(self):
        result = evaluate(demo_records())
        self.assertEqual(result["schema"], "bk08.static-html-execution/v2")
        self.assertEqual(result["metrics"]["field_value_f1"], .8)
        self.assertEqual(result["metrics"]["sequence_success"], .8)
        audit = audit_and_evaluate(demo_partitions())
        self.assertEqual(audit["schema"], "bk08.template-held-out/v2")
        self.assertEqual([audit["splits"][p]["metrics"]["field_value_f1"]
                          for p in ("train", "dev", "test")], [1, 0, 1])

    def test_existing_offline_clis_expose_reproducible_diagnostics(self):
        here = Path(__file__).resolve().parent
        for module in ("offline_html_trace_executor.py", "html_template_split_audit.py"):
            with self.subTest(module=module):
                cmd = [sys.executable, str(here / module), "--demo"]
                one = subprocess.run(cmd, capture_output=True, check=True).stdout
                two = subprocess.run(cmd, capture_output=True, check=True).stdout
                self.assertEqual(one, two)
                output = json.loads(one)
                metrics = (output["metrics"] if module.startswith("offline") else
                           output["audit"]["splits"]["dev"]["metrics"])
                self.assertIn("field_value_f1", metrics)


if __name__ == "__main__":
    unittest.main()
