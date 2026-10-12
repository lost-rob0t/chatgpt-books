"""BK08: score aggregate means from raw rational inputs, never rounded cases."""
from __future__ import annotations

import json
import unittest

from html_template_split_audit import audit_and_evaluate
from offline_html_trace_executor import evaluate, run_trace


HTML = "<div id='a'>Ada</div><div id='b'>Bob</div>"


def call_case(name: str, length: int, matches: int, *, family: str = "rounding") -> dict:
    """Build valid gold and candidate traces with `matches / length` exact calls."""
    assert 1 <= matches < length - 1
    gold = [{"op": "select", "selector": "#a"} for _ in range(length - 1)]
    gold.append({"op": "extract", "field": "name"})
    candidate = [{"op": "select", "selector": "#a" if n < matches else "#b"}
                 for n in range(length - 1)]
    candidate.append({"op": "extract", "field": "other"})
    return {"id": name, "family": family, "pages": {"/": HTML}, "start": "/",
            "gold_trace": gold, "candidate_trace": candidate,
            "gold_extractions": {"name": "Ada"}, "gold_visited": ["/"]}


def fields_case(name: str, fields: int, matches: int, *, family: str = "rounding") -> dict:
    """Build valid traces with precisely `matches / fields` correct field values."""
    gold = [{"op": "select", "selector": "#a"}]
    gold.extend({"op": "extract", "field": f"f{n}"} for n in range(fields))
    candidate = [{"op": "select", "selector": "#a"}]
    for n in range(fields):
        if n == matches:
            candidate.append({"op": "select", "selector": "#b"})
        candidate.append({"op": "extract", "field": f"f{n}"})
    return {"id": name, "family": family, "pages": {"/": HTML}, "start": "/",
            "gold_trace": gold, "candidate_trace": candidate,
            "gold_extractions": {f"f{n}": "Ada" for n in range(fields)},
            "gold_visited": ["/"]}


class ExactCallAggregationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [call_case("triple", 3, 1), call_case("ninth", 9, 4)]

    def test_exact_calls_use_raw_mean(self) -> None:
        self.assertEqual(evaluate(self.rows)["metrics"]["exact_call_accuracy"], 0.388889)

    def test_arguments_use_raw_mean(self) -> None:
        self.assertEqual(evaluate(self.rows)["metrics"]["argument_accuracy"], 0.388889)

    def test_prefix_fraction_uses_raw_mean(self) -> None:
        self.assertEqual(evaluate(self.rows)["metrics"]["gold_prefix_fraction"], 0.388889)

    def test_case_values_still_six_digits(self) -> None:
        scores = {x["id"]: x for x in evaluate(self.rows)["cases"]}
        for name, score in (("triple", 0.333333), ("ninth", 0.444444)):
            self.assertEqual(scores[name]["exact_call_accuracy"], score)
            self.assertEqual(scores[name]["argument_accuracy"], score)

    def test_same_operation_accuracy_unchanged(self) -> None:
        self.assertEqual(evaluate(self.rows)["metrics"]["tool_accuracy"], 1.0)

    def test_semantic_failure_classification_unchanged(self) -> None:
        for case in evaluate(self.rows)["cases"]:
            self.assertEqual(case["extraction_success"], 0)
            self.assertEqual(case["navigation_success"], 1)
            self.assertEqual(case["sequence_success"], 0)
            self.assertEqual(case["failure_reasons"], ["extraction_mismatch", "sequence_mismatch"])

    def test_reordering_cases_preserves_byte_identical_report(self) -> None:
        result_a = json.dumps(evaluate(self.rows), sort_keys=True, separators=(",", ":"))
        result_b = json.dumps(evaluate(list(reversed(self.rows))), sort_keys=True, separators=(",", ":"))
        self.assertEqual(result_a, result_b)

    def test_single_case_means_equal_rendered_cases(self) -> None:
        scored = evaluate([self.rows[0]])
        self.assertEqual(scored["cases"][0]["exact_call_accuracy"],
                         scored["metrics"]["exact_call_accuracy"])


class FieldValueAggregationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [fields_case("triple_fields", 3, 1), fields_case("ninth_fields", 9, 4)]

    def test_value_precision_uses_raw_mean(self) -> None:
        self.assertEqual(evaluate(self.rows)["metrics"]["field_value_precision"], 0.388889)

    def test_value_recall_uses_raw_mean(self) -> None:
        self.assertEqual(evaluate(self.rows)["metrics"]["field_value_recall"], 0.388889)

    def test_value_f1_uses_raw_mean(self) -> None:
        self.assertEqual(evaluate(self.rows)["metrics"]["field_value_f1"], 0.388889)

    def test_field_values_remain_individually_rounded(self) -> None:
        scored = {x["id"]: x for x in evaluate(self.rows)["cases"]}
        self.assertEqual(scored["triple_fields"]["field_value_f1"], 0.333333)
        self.assertEqual(scored["ninth_fields"]["field_value_f1"], 0.444444)

    def test_valid_gold_and_candidate_execution(self) -> None:
        for row in self.rows:
            expected = run_trace(row["pages"], row["start"], row["gold_trace"])
            actual = run_trace(row["pages"], row["start"], row["candidate_trace"])
            self.assertEqual(expected["extractions"], row["gold_extractions"])
            self.assertEqual(expected["visited"], row["gold_visited"])
            self.assertEqual(actual["visited"], row["gold_visited"])

    def test_audit_inherits_correct_raw_mean(self) -> None:
        dev = call_case("dev_case", 3, 1, family="dev_family")
        dev["pages"] = {"/": "<article>" + HTML + "</article>"}
        test = call_case("test_case", 9, 4, family="test_family")
        test["pages"] = {"/": "<main><section>" + HTML + "</section></main>"}
        report = audit_and_evaluate({"train": self.rows, "dev": [dev], "test": [test]})
        self.assertEqual(report["splits"]["train"]["metrics"]["field_value_f1"], 0.388889)


if __name__ == "__main__":
    unittest.main()
