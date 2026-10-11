"""BK08 native regressions: validate entire static HTML inventory, not just visited pages."""
from __future__ import annotations

import copy
from unittest import TestCase, mock

import offline_html_trace_executor as executor


class FixtureInventoryPreflightTests(TestCase):
    def assert_code(self, code: str, action) -> None:
        with self.assertRaises(executor.TraceFailure) as observed:
            action()
        self.assertEqual(observed.exception.code, code)

    def specimen(self):
        case = copy.deepcopy(executor.demo_records()[0])
        case["candidate_trace"] = copy.deepcopy(case["gold_trace"])
        return case

    def test_unvisited_page_exceeding_node_limit_fails_entire_fixture(self):
        case = self.specimen()
        case["pages"]["/unused.html"] = "<b></b>" * (executor.MAX_NODES + 1)
        self.assert_code("parse_bounds", lambda: executor.run_trace(case["pages"], case["start"], case["gold_trace"]))

    def test_gold_evaluation_rejects_unvisited_node_bomb(self):
        case = self.specimen()
        case["pages"]["/unused.html"] = "<i></i>" * (executor.MAX_NODES + 1)
        self.assert_code("parse_bounds", lambda: executor.evaluate([case]))

    def test_unvisited_page_exceeding_depth_limit_fails_fixture(self):
        case = self.specimen()
        case["pages"]["/hidden.html"] = "<div>" * (executor.MAX_DEPTH + 2)
        self.assert_code("parse_bounds", lambda: executor.run_trace(case["pages"], case["start"], case["gold_trace"]))

    def test_unvisited_page_limit_is_enforced_even_when_candidate_would_fail(self):
        case = self.specimen()
        case["candidate_trace"][0]["selector"] = "#not-there"
        case["pages"]["/hidden.html"] = "<div>" * (executor.MAX_DEPTH + 2)
        self.assert_code("parse_bounds", lambda: executor.evaluate([case]))

    def test_parse_all_pages_once_even_if_trace_revisits_one(self):
        pages = {
            "/start.html": "<a id='forward' href='detail.html'>Forward</a>",
            "/detail.html": "<a id='back' href='start.html'>Back</a>",
        }
        actions = [
            {"op": "select", "selector": "a#forward"},
            {"op": "follow", "kind": "next"},
            {"op": "select", "selector": "a#back"},
            {"op": "follow", "kind": "detail"},
            {"op": "select", "selector": "a#forward"},
            {"op": "follow", "kind": "next"},
        ]
        with mock.patch.object(executor, "BoundedParser", wraps=executor.BoundedParser) as parser:
            result = executor.run_trace(pages, "/start.html", actions)
        self.assertEqual(result["visited"], ["/start.html", "/detail.html", "/start.html", "/detail.html"])
        self.assertEqual(parser.call_count, len(pages))

    def test_unvisited_valid_markup_is_preflighted_but_not_reported_as_visited(self):
        case = self.specimen()
        case["pages"]["/unused.html"] = "<em>Safe but never fetched by a trace</em>"
        outcome = executor.run_trace(case["pages"], case["start"], case["gold_trace"])
        self.assertEqual(outcome["visited"], [case["start"]])
        self.assertEqual(set(outcome["page_sha256"]), {case["start"]})
        self.assertEqual(outcome["extractions"], case["gold_extractions"])

    def test_valid_unused_inventory_does_not_change_scores(self):
        case = self.specimen()
        expected = executor.evaluate([case])
        case["pages"]["/another.html"] = "<section><p>unused</p></section>"
        actual = executor.evaluate([case])
        self.assertEqual(expected["metrics"], actual["metrics"])
        self.assertEqual(expected["cases"][0]["observed"], actual["cases"][0]["observed"])

    def test_page_input_order_does_not_change_report(self):
        case = self.specimen()
        case["pages"]["/another.html"] = "<section id='foo'>Unused</section>"
        first = executor.evaluate([case])
        case["pages"] = dict(reversed(list(case["pages"].items())))
        self.assertEqual(first, executor.evaluate([case]))

    def test_valid_pages_at_depth_limit_still_execute(self):
        case = self.specimen()
        case["pages"]["/unused.html"] = "<div>" * (executor.MAX_DEPTH - 2)
        self.assertEqual(executor.evaluate([case])["metrics"]["extraction_success"], 1.0)

    def test_same_page_hash_remains_byte_exact(self):
        case = self.specimen()
        outcome = executor.run_trace(case["pages"], case["start"], case["gold_trace"])
        import hashlib
        self.assertEqual(outcome["page_sha256"][case["start"]],
                         hashlib.sha256(case["pages"][case["start"]].encode("utf-8")).hexdigest())
