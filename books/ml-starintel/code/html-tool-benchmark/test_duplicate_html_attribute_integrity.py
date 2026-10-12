"""BK08: duplicate attributes make static HTML gold fixtures ambiguous.

The offline parser must reject ambiguous markup before either gold or candidate
trace scoring. Browsers' error recovery is intentionally outside this oracle.
"""
from __future__ import annotations

import copy
import json
import unittest

from offline_html_trace_executor import TraceFailure, demo_records, evaluate, run_trace
from html_template_split_audit import audit_and_evaluate, demo_partitions


class DuplicateHtmlAttributeIntegrityTests(unittest.TestCase):
    def reject(self, html: str) -> None:
        for attempt in ([], [{"op": "select", "selector": "#record"}]):
            with self.subTest(html=html, attempt=attempt):
                with self.assertRaises(TraceFailure) as caught:
                    run_trace({"/index.html": html}, "/index.html", attempt)
                self.assertEqual(caught.exception.code, "parse_bounds")
                self.assertIn("duplicate HTML attribute", str(caught.exception))

    def test_duplicate_href_with_different_targets_is_not_first_wins(self):
        self.reject('<a id="record" href="/good.html" href="/bad.html">Go</a>')

    def test_duplicate_href_with_same_target_is_not_implicitly_canonical(self):
        self.reject('<a id="record" href="/same.html" href="/same.html">Go</a>')

    def test_html_case_insensitive_duplicate_attributes(self):
        self.reject('<a id="record" href="/a" HREF="/b">Go</a>')

    def test_repeated_id_is_ambiguous_even_with_identical_value(self):
        self.reject('<p id="record" id="record">Ada</p>')

    def test_repeated_class_is_ambiguous(self):
        self.reject('<p id="record" class="person" CLASS="other">Ada</p>')

    def test_repeated_data_attribute_is_ambiguous(self):
        self.reject('<p id="record" data-value="A" data-value="B">Ada</p>')

    def test_unquoted_repeated_attribute_is_ambiguous(self):
        self.reject('<a id=record href=/a href=/b>Go</a>')

    def test_self_closing_tag_duplicate_attribute_is_ambiguous(self):
        self.reject('<input id="record" value="A" value="B" />')

    def test_duplicate_on_unvisited_page_fails_preflight(self):
        pages = {"/index.html": '<p id="record">Ada</p>',
                 "/hidden.html": '<a href="/one" href="/two">unvisited</a>'}
        with self.assertRaises(TraceFailure) as caught:
            run_trace(pages, "/index.html", [])
        self.assertEqual(caught.exception.code, "parse_bounds")

    def test_distinct_attribute_names_preserve_extraction(self):
        pages = {"/index.html": '<p id="record" class="person" data-value="A">Ada</p>'}
        trace = [{"op": "select", "selector": "#record"}, {"op": "extract", "field": "name"}]
        self.assertEqual(run_trace(pages, "/index.html", trace)["extractions"], {"name": "Ada"})

    def test_separate_nodes_with_same_id_keep_selector_ambiguous(self):
        html = '<p id="record">A</p><p id="record">B</p>'
        with self.assertRaises(TraceFailure) as caught:
            run_trace({"/index.html": html}, "/index.html", [{"op": "select", "selector": "#record"}])
        self.assertEqual(caught.exception.code, "selector_ambiguous")

    def test_gold_evaluator_does_not_score_first_wins_markup(self):
        row = copy.deepcopy(demo_records()[0])
        path = row["start"]
        row["pages"][path] = row["pages"][path].replace("id='table-name'", "id='table-name' id='record'")
        with self.assertRaises(TraceFailure) as caught:
            evaluate([row])
        self.assertEqual(caught.exception.code, "parse_bounds")

    def test_split_audit_rejects_ambiguous_unvisited_page(self):
        partitions = demo_partitions()
        partitions["test"][0]["pages"]["/unvisited-duplicate.html"] = '<p title="x" title="y">X</p>'
        with self.assertRaises(TraceFailure) as caught:
            audit_and_evaluate(partitions)
        self.assertEqual(caught.exception.code, "parse_bounds")

    def test_error_and_success_are_deterministic(self):
        html = '<p class="a" CLASS="b">X</p>'
        errors = []
        for _ in range(2):
            try:
                run_trace({"/index.html": html}, "/index.html", [])
            except TraceFailure as exc:
                errors.append((exc.code, str(exc)))
        self.assertEqual(len(errors), 2)
        self.assertEqual(errors[0], errors[1])
        row = demo_records()[0]
        self.assertEqual(json.dumps(evaluate([row]), sort_keys=True),
                         json.dumps(evaluate([row]), sort_keys=True))


if __name__ == "__main__":
    unittest.main()
