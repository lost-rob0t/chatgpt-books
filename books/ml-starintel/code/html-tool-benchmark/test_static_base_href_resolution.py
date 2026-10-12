"""BK08: static <base href> semantics are deterministic and origin confined."""
from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

from offline_html_trace_executor import TraceFailure, evaluate, run_trace


class StaticBaseHrefResolutionTests(unittest.TestCase):
    @staticmethod
    def fixture(base: str = '<head><base href="/catalog/v2/"></head>') -> dict:
        pages = {
            "/catalog/index.html": base + '<body><a id="entry" href="record.html">Record</a></body>',
            "/catalog/record.html": '<p id="name">Incorrect directory</p>',
            "/catalog/v2/record.html": '<p id="name">Ada</p>',
        }
        gold = [
            {"op": "select", "selector": "#entry"},
            {"op": "follow", "kind": "detail"},
            {"op": "select", "selector": "#name"},
            {"op": "extract", "field": "name"},
        ]
        return {"id": "base_href_01", "family": "base_href", "pages": pages,
                "start": "/catalog/index.html", "gold_trace": gold,
                "candidate_trace": copy.deepcopy(gold), "gold_extractions": {"name": "Ada"},
                "gold_visited": ["/catalog/index.html", "/catalog/v2/record.html"]}

    def test_explicit_absolute_path_base_changes_relative_anchor_resolution(self):
        case = self.fixture()
        observed = run_trace(case["pages"], case["start"], case["gold_trace"])
        self.assertEqual(observed["visited"], case["gold_visited"])
        self.assertEqual(observed["extractions"], case["gold_extractions"])

    def test_base_relative_to_document_is_applied_once(self):
        case = self.fixture('<base href="v2/">')
        self.assertEqual(run_trace(case["pages"], case["start"], case["gold_trace"])["visited"],
                         case["gold_visited"])

    def test_absolute_same_origin_base_is_supported(self):
        case = self.fixture('<base href="https://fixture.invalid/catalog/v2/">')
        self.assertEqual(run_trace(case["pages"], case["start"], case["gold_trace"])["visited"],
                         case["gold_visited"])

    def test_base_file_path_uses_parent_directory(self):
        case = self.fixture('<base href="/catalog/v2/landing.html">')
        self.assertEqual(run_trace(case["pages"], case["start"], case["gold_trace"])["visited"],
                         case["gold_visited"])

    def test_base_with_no_href_does_not_change_navigation(self):
        case = self.fixture('<head><base target="_self"></head>')
        case["gold_extractions"] = {"name": "Incorrect directory"}
        case["gold_visited"][-1] = "/catalog/record.html"
        self.assertEqual(run_trace(case["pages"], case["start"], case["gold_trace"])["visited"],
                         case["gold_visited"])

    def test_empty_base_href_keeps_document_resolution(self):
        case = self.fixture('<base href="">')
        case["gold_extractions"] = {"name": "Incorrect directory"}
        case["gold_visited"][-1] = "/catalog/record.html"
        self.assertEqual(run_trace(case["pages"], case["start"], case["gold_trace"])["visited"],
                         case["gold_visited"])

    def test_template_base_does_not_affect_active_page(self):
        case = self.fixture('<template><base href="/catalog/v2/"></template>')
        case["gold_extractions"] = {"name": "Incorrect directory"}
        case["gold_visited"][-1] = "/catalog/record.html"
        self.assertEqual(run_trace(case["pages"], case["start"], case["gold_trace"])["visited"],
                         case["gold_visited"])

    def test_two_base_href_declarations_fail_closed(self):
        case = self.fixture('<base href="/catalog/v2/"><base href="/catalog/">')
        with self.assertRaises(TraceFailure) as caught:
            run_trace(case["pages"], case["start"], case["gold_trace"])
        self.assertEqual(caught.exception.code, "unsafe_navigation")

    def test_external_base_href_fails_closed(self):
        case = self.fixture('<base href="https://outside.invalid/catalog/v2/">')
        with self.assertRaises(TraceFailure) as caught:
            run_trace(case["pages"], case["start"], case["gold_trace"])
        self.assertEqual(caught.exception.code, "unsafe_navigation")

    def test_base_query_and_percent_encodings_fail_closed(self):
        for value in ("/catalog/v2/?q=one", "/catalog/%76%32/", "/catalog/../v2/"):
            with self.subTest(value=value):
                case = self.fixture(f'<base href="{value}">')
                with self.assertRaises(TraceFailure) as caught:
                    run_trace(case["pages"], case["start"], case["gold_trace"])
                self.assertEqual(caught.exception.code, "unsafe_navigation")

    def test_unvisited_page_base_is_preflight_validated(self):
        case = self.fixture('<base href="/catalog/v2/">')
        case["pages"]["/never-opened.html"] = '<base href="https://other.invalid/">'
        with self.assertRaises(TraceFailure) as caught:
            run_trace(case["pages"], case["start"], [])
        self.assertEqual(caught.exception.code, "unsafe_navigation")

    def test_scored_gold_enforces_base_semantics(self):
        case = self.fixture()
        report = evaluate([case])
        self.assertEqual(report["cases"][0]["navigation_success"], 1)
        self.assertEqual(report["cases"][0]["extraction_success"], 1)
        self.assertEqual(report["cases"][0]["observed"]["visited"], case["gold_visited"])

    def test_wrong_gold_page_fails_instead_of_becoming_success(self):
        case = self.fixture()
        case["gold_visited"][-1] = "/catalog/record.html"
        with self.assertRaises(TraceFailure) as caught:
            evaluate([case])
        self.assertEqual(caught.exception.code, "gold_mismatch")

    def test_report_remains_byte_identical_and_never_uses_network(self):
        case = self.fixture()
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            one = json.dumps(evaluate([case]), sort_keys=True)
            two = json.dumps(evaluate([case]), sort_keys=True)
        self.assertEqual(one, two)


if __name__ == "__main__":
    unittest.main()
