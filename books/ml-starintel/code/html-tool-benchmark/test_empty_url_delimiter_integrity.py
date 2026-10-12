"""BK08: empty query/fragment delimiters are not valid offline fixture URLs."""
from __future__ import annotations

import copy
import unittest

from html_template_split_audit import audit_and_evaluate, demo_partitions
from offline_html_trace_executor import TraceFailure, evaluate, resolve_page, run_trace


class EmptyUrlDelimiterIntegrityTests(unittest.TestCase):
    """Distinguish an absent URL component from a present but empty one."""

    def expect_unsafe(self, raw: str, *, base: str = "/catalog/index.html") -> None:
        with self.assertRaises(TraceFailure) as raised:
            resolve_page(raw, base)
        self.assertEqual(raised.exception.code, "unsafe_navigation")

    @staticmethod
    def fixture(href: str) -> tuple[dict[str, str], list[dict[str, str]]]:
        pages = {
            "/catalog/index.html": f'<a id="go" href="{href}">Details</a>',
            "/catalog/item.html": '<p id="name">Ada</p>',
        }
        trace = [
            {"op": "select", "selector": "#go"},
            {"op": "follow", "kind": "detail"},
        ]
        return pages, trace

    def test_relative_empty_query(self) -> None:
        self.expect_unsafe("item.html?")

    def test_relative_empty_fragment(self) -> None:
        self.expect_unsafe("item.html#")

    def test_absolute_path_empty_query(self) -> None:
        self.expect_unsafe("/catalog/item.html?")

    def test_absolute_path_empty_fragment(self) -> None:
        self.expect_unsafe("/catalog/item.html#")

    def test_same_origin_absolute_url_empty_query(self) -> None:
        self.expect_unsafe("https://fixture.invalid/catalog/item.html?")

    def test_same_origin_absolute_url_empty_fragment(self) -> None:
        self.expect_unsafe("https://fixture.invalid/catalog/item.html#")

    def test_query_delimiter_alone(self) -> None:
        self.expect_unsafe("?")

    def test_fragment_delimiter_alone(self) -> None:
        self.expect_unsafe("#")

    def test_empty_query_at_origin_root(self) -> None:
        self.expect_unsafe("/?")

    def test_empty_fragment_at_origin_root(self) -> None:
        self.expect_unsafe("/#")

    def test_empty_query_and_fragment_combination(self) -> None:
        for raw in ("?#", "#?", "item.html?#", "item.html#?"):
            with self.subTest(raw=raw):
                self.expect_unsafe(raw)

    def test_gold_follow_empty_query_fails_typed(self) -> None:
        pages, trace = self.fixture("item.html?")
        with self.assertRaises(TraceFailure) as raised:
            run_trace(pages, "/catalog/index.html", trace)
        self.assertEqual(raised.exception.code, "unsafe_navigation")

    def test_gold_follow_empty_fragment_fails_typed(self) -> None:
        pages, trace = self.fixture("item.html#")
        with self.assertRaises(TraceFailure) as raised:
            run_trace(pages, "/catalog/index.html", trace)
        self.assertEqual(raised.exception.code, "unsafe_navigation")

    def test_corpus_audit_rejects_ambiguous_gold_before_scoring(self) -> None:
        rows = copy.deepcopy(demo_partitions())
        record = rows["dev"][0]
        record["pages"], record["gold_trace"] = self.fixture("item.html?")
        record["start"] = "/catalog/index.html"
        record["candidate_trace"] = copy.deepcopy(record["gold_trace"])
        record["gold_extractions"] = {}
        record["gold_visited"] = [record["start"], "/catalog/item.html"]
        with self.assertRaises(TraceFailure) as raised:
            audit_and_evaluate(rows)
        self.assertEqual(raised.exception.code, "unsafe_navigation")

    def test_valid_relative_and_same_origin_paths_unchanged(self) -> None:
        examples = {
            "item.html": "/catalog/item.html",
            "./item.html": None,  # dot components remain explicitly forbidden
            "/catalog/item.html": "/catalog/item.html",
            "https://fixture.invalid/catalog/item.html": "/catalog/item.html",
        }
        for raw, expected in examples.items():
            with self.subTest(raw=raw):
                if expected is None:
                    self.expect_unsafe(raw)
                else:
                    self.assertEqual(resolve_page(raw, "/catalog/index.html"), expected)
        pages, trace = self.fixture("item.html")
        self.assertEqual(run_trace(pages, "/catalog/index.html", trace)["visited"],
                         ["/catalog/index.html", "/catalog/item.html"])

    def test_nonempty_query_and_fragment_already_rejected(self) -> None:
        for raw in ("item.html?draft=1", "item.html#section"):
            with self.subTest(raw=raw):
                self.expect_unsafe(raw)

    def test_candidate_bad_fragment_is_typed_not_gold_success(self) -> None:
        pages = {
            "/catalog/index.html": '<p id="name">Ada</p><a id="go" href="item.html#">Go</a>',
            "/catalog/item.html": '<p id="extra">Grace</p>',
        }
        gold = [{"op": "select", "selector": "#name"},
                {"op": "extract", "field": "name"}]
        candidate = [{"op": "select", "selector": "#go"},
                     {"op": "follow", "kind": "detail"}]
        row = {"id": "empty_fragment_candidate", "family": "empty_fragment", "pages": pages,
               "start": "/catalog/index.html", "gold_trace": gold,
               "candidate_trace": candidate, "gold_extractions": {"name": "Ada"},
               "gold_visited": ["/catalog/index.html"]}
        result = evaluate([row])
        self.assertEqual(result["cases"][0]["failure"], "unsafe_navigation")
        self.assertEqual(result["cases"][0]["failure_reasons"], ["unsafe_navigation"])
        self.assertEqual(result["cases"][0]["extraction_success"], 0)


if __name__ == "__main__":
    unittest.main()
