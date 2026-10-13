"""BK08 gold-trace URL controls: DEL/C1 characters are not static page identity."""
from __future__ import annotations

import json
import unittest

from offline_html_trace_executor import TraceFailure, demo_records, evaluate, resolve_page, run_trace


GOOD = "<a id='ok' href='next.html'>Next</a><span id='value'>Ada</span>"


def case_for_bad_link(character: str) -> dict:
    pages = {"/index.html": GOOD.replace("next.html", f"next{character}.html"),
             "/other.html": "<span id='value'>Bob</span>"}
    gold = [{"op": "select", "selector": "#value"}, {"op": "extract", "field": "name"}]
    candidate = [{"op": "select", "selector": "#ok"}, {"op": "follow", "kind": "detail"}]
    return {"id": "control_case", "family": "controls", "pages": pages,
            "start": "/index.html", "gold_trace": gold, "candidate_trace": candidate,
            "gold_extractions": {"name": "Ada"}, "gold_visited": ["/index.html"]}


class URLControlIdentityTests(unittest.TestCase):
    def assert_unsafe(self, value: str, base: str = "/") -> None:
        with self.assertRaises(TraceFailure) as failure:
            resolve_page(value, base)
        self.assertEqual(failure.exception.code, "unsafe_navigation")

    def test_del_in_absolute_path(self) -> None:
        self.assert_unsafe("/item\x7f.html")

    def test_c1_next_line_in_relative_path(self) -> None:
        self.assert_unsafe("item\x85.html", "/catalog/index.html")

    def test_all_del_c1_controls_are_unsafe(self) -> None:
        for point in range(0x7F, 0xA0):
            with self.subTest(point=hex(point)):
                self.assert_unsafe("/item" + chr(point) + ".html")

    def test_fixed_origin_absolute_url_rejects_controls(self) -> None:
        self.assert_unsafe("https://fixture.invalid/catalog/\x9fitem.html")

    def test_controls_after_relative_directory_are_not_normalized_away(self) -> None:
        self.assert_unsafe("next\x80.html", "/catalog/index.html")

    def test_unicode_filename_without_control_still_supported(self) -> None:
        self.assertEqual(resolve_page("/café.html"), "/café.html")

    def test_safe_fixed_origin_absolute_url_preserved(self) -> None:
        self.assertEqual(resolve_page("https://fixture.invalid/a.html"), "/a.html")

    def test_existing_query_and_fragment_rejection_preserved(self) -> None:
        for value in ("/item?", "/item#", "/item?q=x", "/item#value"):
            with self.subTest(value=value):
                self.assert_unsafe(value)


class GoldTraceControlTests(unittest.TestCase):
    def test_bad_start_path_fails_closed(self) -> None:
        with self.assertRaises(TraceFailure) as failure:
            run_trace({"/index.html": GOOD}, "/index\x7f.html", [])
        self.assertEqual(failure.exception.code, "unsafe_navigation")

    def test_invalid_page_key_fails_closed(self) -> None:
        with self.assertRaises(TraceFailure) as failure:
            run_trace({"/index\x85.html": GOOD}, "/index\x85.html", [])
        self.assertEqual(failure.exception.code, "unsafe_navigation")

    def test_unvisited_invalid_page_key_fails_closed(self) -> None:
        with self.assertRaises(TraceFailure) as failure:
            run_trace({"/index.html": GOOD, "/unvisited\x80.html": "<div>bad</div>"}, "/index.html", [])
        self.assertEqual(failure.exception.code, "unsafe_navigation")

    def test_follow_rejects_c1_href(self) -> None:
        record = case_for_bad_link("\x85")
        with self.assertRaises(TraceFailure) as failure:
            run_trace(record["pages"], record["start"], record["candidate_trace"])
        self.assertEqual(failure.exception.code, "unsafe_navigation")

    def test_candidate_failure_typed_and_observed_discarded(self) -> None:
        report = evaluate([case_for_bad_link("\x7f")]); case = report["cases"][0]
        self.assertEqual(case["failure"], "unsafe_navigation")
        self.assertEqual(case["failure_reasons"], ["unsafe_navigation"])
        self.assertEqual(case["observed"], {"extractions": {}, "visited": [], "page_sha256": {}})

    def test_gold_follow_does_not_normalize_control(self) -> None:
        row = case_for_bad_link("\x9f")
        row["gold_trace"] = row["candidate_trace"]
        row["candidate_trace"] = []
        row["gold_extractions"] = {}
        with self.assertRaises(TraceFailure) as failure:
            evaluate([row])
        self.assertEqual(failure.exception.code, "unsafe_navigation")

    def test_safe_fixture_demo_unchanged(self) -> None:
        report = evaluate(demo_records())
        self.assertEqual(report["samples"], 5)
        self.assertEqual(report["failure_reason_counts"], {"selector_zero": 1})

    def test_deterministic_scoring_under_record_reordering(self) -> None:
        rows = demo_records()
        first = json.dumps(evaluate(rows), sort_keys=True, separators=(",", ":"))
        second = json.dumps(evaluate(list(reversed(rows))), sort_keys=True, separators=(",", ":"))
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
