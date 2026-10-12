"""BK08: offline compound-selector grammar and end-to-end oracle invariants."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from html_template_split_audit import audit_and_evaluate, demo_partitions
from offline_html_trace_executor import (
    BoundedParser, TraceFailure, _bounded_selector, demo_records,
    evaluate, run_trace, select_one,
)


class BoundedCompoundSelectorTests(unittest.TestCase):
    HTML = (
        '<section><div id="record" class="person selected active">Ada</div>'
        '<div id="decoy" class="person selected">Grace</div>'
        '<span id="other" class="active">Linus</span></section>'
    )

    def parse(self, html=None):
        parser = BoundedParser()
        parser.feed(self.HTML if html is None else html)
        parser.close()
        return parser.root

    def expect_invalid(self, selector):
        with self.assertRaises(TraceFailure) as raised:
            select_one(self.parse(), selector)
        self.assertEqual(raised.exception.code, "invalid_action", repr(selector))

    def test_id_and_class_component_order_are_equivalent(self):
        root = self.parse()
        for selector in ("div#record.person", "div.person#record", "#record.person",
                         ".person#record.active", "div.active#record.selected.person"):
            with self.subTest(selector=selector):
                self.assertEqual(select_one(root, selector).text(), "Ada")

    def test_two_classes_disambiguate_without_an_id(self):
        root = self.parse()
        self.assertEqual(select_one(root, "div.selected.active").attrs["id"], "record")
        self.assertEqual(select_one(root, ".active.selected").attrs["id"], "record")

    def test_three_class_intersection_is_permutation_invariant(self):
        root = self.parse()
        for selector in (".person.active.selected", ".selected.person.active", "div.selected.active.person"):
            with self.subTest(selector=selector):
                self.assertEqual(select_one(root, selector).attrs["id"], "record")

    def test_more_than_three_class_components_remain_invalid(self):
        self.expect_invalid("div.person.selected.active.fourth")

    def test_duplicate_id_components_are_invalid(self):
        for selector in ("div#record#record", "div.person#record.selected#decoy"):
            with self.subTest(selector=selector):
                self.expect_invalid(selector)

    def test_unsupported_css_families_stay_invalid(self):
        for selector in ("div > span", "div span", "div + span", "[id=record]",
                         "div[id=record]", "div:hover", "div,span", "*", "div#", "div..person"):
            with self.subTest(selector=selector):
                self.expect_invalid(selector)

    def test_component_name_boundaries_still_apply(self):
        for selector in ("div.#record", "div#a:b", "div.person#1bad", "div.Person!",
                         "div." + "a" * 65, "div#" + "z" * 65):
            with self.subTest(selector=selector):
                self.expect_invalid(selector)

    def test_no_selector_or_oversized_selector(self):
        for selector in ("", "z" * 161, None, 123, [], {}):
            with self.subTest(selector=selector):
                self.expect_invalid(selector)

    def test_repeated_class_component_is_idempotent_under_budget(self):
        self.assertEqual(select_one(self.parse(), "#record.active.active").text(), "Ada")

    def test_disjoint_class_intersection_returns_typed_zero(self):
        with self.assertRaises(TraceFailure) as raised:
            select_one(self.parse(), "#decoy.selected.active")
        self.assertEqual(raised.exception.code, "selector_zero")

    def test_broad_class_still_fails_with_typed_ambiguity(self):
        with self.assertRaises(TraceFailure) as raised:
            select_one(self.parse(), "div.person.selected")
        self.assertEqual(raised.exception.code, "selector_ambiguous")

    def test_parser_returns_canonical_parts_without_changing_names(self):
        self.assertEqual(_bounded_selector("div.active#record.person"),
                         ("div", "record", ("active", "person")))

    def test_run_trace_executes_compound_class_intersection(self):
        result = run_trace({"/index.html": self.HTML}, "/index.html", [
            {"op": "select", "selector": "div.active#record.selected.person"},
            {"op": "extract", "field": "name"},
        ])
        self.assertEqual(result["extractions"], {"name": "Ada"})
        self.assertEqual(result["visited"], ["/index.html"])

    def test_equal_html_outcomes_can_still_have_unequal_action_accuracy(self):
        row = deepcopy(next(r for r in demo_records() if r["family"] == "cards"))
        row["pages"][row["start"]] = '<span id="card-title" class="person chosen">Grace</span>'
        row["gold_trace"][0]["selector"] = "span.chosen#card-title.person"
        row["candidate_trace"] = deepcopy(row["gold_trace"])
        row["candidate_trace"][0]["selector"] = "span#card-title.person.chosen"
        result = evaluate([row])["cases"][0]
        self.assertEqual(result["extraction_success"], 1)
        self.assertEqual(result["navigation_success"], 1)
        self.assertEqual(result["sequence_success"], 0)
        self.assertEqual(result["exact_call_accuracy"], 0.5)
        self.assertEqual(result["first_divergence_index"], 0)

    def test_split_auditor_accepts_new_gold_without_relaxing_leakage(self):
        partitions = deepcopy(demo_partitions())
        record = next(r for r in partitions["train"] if r["family"] == "tables")
        record["pages"][record["start"]] = (
            '<table><tr><td id="table-name" class="row name primary">Ada</td></tr></table>'
        )
        record["gold_trace"][0]["selector"] = "td.primary#table-name.row.name"
        record["candidate_trace"] = deepcopy(record["gold_trace"])
        self.assertEqual(audit_and_evaluate(partitions)["samples"], 5)
        clone = deepcopy(record)
        clone["id"] = "new_identity"
        clone["family"] = "new_family"
        partitions["test"][0] = clone
        with self.assertRaises(TraceFailure) as raised:
            audit_and_evaluate(partitions)
        self.assertEqual(raised.exception.code, "split_leakage")

    def test_full_jsonl_cli_scores_compound_selector_reproducibly(self):
        row = deepcopy(next(r for r in demo_records() if r["family"] == "tables"))
        row["pages"][row["start"]] = '<td id="table-name" class="row name chosen">Ada</td>'
        row["gold_trace"][0]["selector"] = "td.row#table-name.name.chosen"
        row["candidate_trace"] = deepcopy(row["gold_trace"])
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp, "case.jsonl")
            source.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf8")
            cmd = [sys.executable, str(Path(__file__).with_name("offline_html_trace_executor.py")),
                   "--evaluate", str(source)]
            first = subprocess.run(cmd, check=True, capture_output=True).stdout
            second = subprocess.run(cmd, check=True, capture_output=True).stdout
            self.assertEqual(first, second)
            scored = json.loads(first)
            self.assertEqual(scored["metrics"]["extraction_success"], 1.0)
            self.assertEqual(scored["metrics"]["sequence_success"], 1.0)


if __name__ == "__main__":
    unittest.main()
