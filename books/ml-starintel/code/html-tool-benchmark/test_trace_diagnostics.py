"""BK08 trace diagnostics: offline, deterministic stdlib unit checks."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import trace_diagnostics as td


class TraceDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.cases = td.demo_cases()

    def _case(self, name):
        return next(c for c in self.cases if c["id"] == name)

    def test_exact_gold_success(self):
        row = td.diagnose(self._case("correct"))
        self.assertEqual(row["sequence_success"], 1)
        self.assertEqual(row["edit_distance"], 0)
        self.assertEqual(row["exact_call_accuracy"], 1.0)

    def test_missing_action_aligns_remaining_exact(self):
        row = td.diagnose(self._case("missing-field"))
        self.assertEqual(row["fault_counts"], {"missing_action": 1})
        self.assertEqual(row["exact_calls"], 2)
        self.assertEqual(row["first_fault"]["gold_index"], 1)
        self.assertEqual(row["first_fault"]["predicted_index"], None)

    def test_inserted_action_not_cascade(self):
        row = td.diagnose(self._case("inserted-nav"))
        self.assertEqual(row["fault_counts"], {"extra_action": 1})
        self.assertEqual(row["exact_calls"], 3)

    def test_wrong_selector_fault(self):
        row = td.diagnose(self._case("wrong-selector"))
        self.assertEqual(row["fault_counts"], {"wrong_selector": 1})
        self.assertEqual(row["matching_tool_actions"], 3)
        self.assertLess(row["argument_accuracy"], 1)

    def test_wrong_tool_fault(self):
        row = td.diagnose(self._case("wrong-tool"))
        self.assertEqual(row["fault_counts"], {"wrong_tool": 1})
        self.assertEqual(row["exact_calls"], 1)

    def test_empty_prediction_fault(self):
        row = td.diagnose(self._case("empty-prediction"))
        self.assertEqual(row["fault_counts"], {"missing_action": 2})
        self.assertEqual(row["exact_call_accuracy"], 0)

    def test_empty_both_are_exact_with_defined_denominator(self):
        row = td.diagnose({"id": "empty", "gold": [], "predicted": []})
        self.assertEqual(row["sequence_success"], 1)
        self.assertEqual(row["exact_call_accuracy"], 0)
        self.assertEqual(row["edit_distance"], 0)

    def test_all_demo_cases_reproducible(self):
        self.assertEqual(td.evaluate(self.cases), td.evaluate(self.cases))
        self.assertEqual(td.evaluate(self.cases), td.evaluate(list(reversed(self.cases))))

    def test_metrics_in_range(self):
        report = td.evaluate(self.cases)
        self.assertEqual(report["examples"], len(self.cases))
        for value in report["metrics"].values():
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 1)

    def test_duplicate_case_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            td.evaluate([self.cases[0], self.cases[0]])

    def test_bad_argument_schema_rejected(self):
        case = copy.deepcopy(self.cases[0])
        case["predicted"][0]["args"]["secret"] = "x"
        with self.assertRaisesRegex(ValueError, "unexpected"):
            td.evaluate([case])

    def test_invalid_action_type_rejected(self):
        case = copy.deepcopy(self.cases[0])
        case["predicted"][0]["tool"] = "eval"
        with self.assertRaisesRegex(ValueError, "invalid tool"):
            td.evaluate([case])

    def test_invalid_field_rejected(self):
        case = copy.deepcopy(self.cases[0])
        case["predicted"][1]["args"]["field"] = "password"
        with self.assertRaisesRegex(ValueError, "field"):
            td.evaluate([case])

    def test_action_budget_rejected(self):
        case = copy.deepcopy(self.cases[0])
        case["gold"] = case["gold"] * 20
        with self.assertRaisesRegex(ValueError, "budget"):
            td.evaluate([case])

    def test_case_count_budget_rejected(self):
        row = self.cases[0]
        with self.assertRaisesRegex(ValueError, "case count"):
            td.evaluate([{**row, "id": f"case-{i}"} for i in range(td.MAX_CASES + 1)])

    def test_tool_arg_mismatch_navigation_taxonomy(self):
        c = self._case("inserted-nav")
        gold = [c["predicted"][1]]
        pred = [{"tool": "follow_next", "args": {"selector": "a[rel=prev]"}}]
        row = td.diagnose({"id": "nav", "gold": gold, "predicted": pred})
        self.assertEqual(row["fault_counts"], {"wrong_navigation_selector": 1})

    def test_tool_arg_mismatch_field_taxonomy(self):
        gold = [{"tool": "extract", "args": {"selector": ".f", "field": "title"}}]
        pred = [{"tool": "extract", "args": {"selector": ".f", "field": "score"}}]
        row = td.diagnose({"id": "field", "gold": gold, "predicted": pred})
        self.assertEqual(row["fault_counts"], {"wrong_field": 1})

    def test_jsonl_io_and_one_command_cli(self):
        entry = Path(td.__file__)
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "cases.jsonl"
            file.write_text("\n".join(json.dumps(c) for c in self.cases) + "\n", encoding="utf-8")
            a = subprocess.check_output([sys.executable, str(entry), "--input", str(file)])
            b = subprocess.check_output([sys.executable, str(entry), "--input", str(file)])
            self.assertEqual(a, b)
            self.assertEqual(json.loads(a)["examples"], 6)

    def test_one_command_demo_without_network(self):
        with patch("socket.socket", side_effect=AssertionError("network attempted")):
            self.assertEqual(td.evaluate(td.demo_cases()), td.evaluate(td.demo_cases()))
        result = subprocess.check_output([sys.executable, str(Path(td.__file__)), "--demo"])
        self.assertEqual(json.loads(result)["examples"], 6)

    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            orig = root / "real.jsonl"
            orig.write_text("{}\n")
            alias = root / "alias.jsonl"
            alias.symlink_to(orig)
            with self.assertRaisesRegex(ValueError, "symlink"):
                td.read_jsonl(alias)

    def test_oversize_line_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "big.jsonl"
            file.write_bytes(b" " * (td.MAX_LINE_BYTES + 1) + b"\n")
            with self.assertRaisesRegex(ValueError, "line"):
                td.read_jsonl(file)

    def test_unknown_fields_fail_closed(self):
        case = copy.deepcopy(self.cases[0])
        case["url"] = "https://example.org"
        with self.assertRaisesRegex(ValueError, "exactly"):
            td.evaluate([case])


if __name__ == "__main__":
    unittest.main()
