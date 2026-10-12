"""BK08: static navigation must not interpret backslashes as portable URL separators."""
from __future__ import annotations

import copy
import json
import unittest

from html_template_split_audit import audit_and_evaluate, demo_partitions
from offline_html_trace_executor import TraceFailure, demo_records, evaluate, resolve_page, run_trace


class BackslashUrlAmbiguityTests(unittest.TestCase):
    def assert_unsafe(self, fn, *args):
        with self.assertRaises(TraceFailure) as caught:
            fn(*args)
        self.assertEqual(caught.exception.code, "unsafe_navigation")
        return str(caught.exception)

    def test_relative_backslash_path_is_not_a_page_reference(self):
        self.assert_unsafe(resolve_page, "v2\\record.html", "/catalog/index.html")

    def test_absolute_backslash_path_is_not_a_page_reference(self):
        self.assert_unsafe(resolve_page, "/catalog\\record.html", "/catalog/index.html")

    def test_windows_unc_like_reference_is_not_a_page_reference(self):
        self.assert_unsafe(resolve_page, "\\\\other.invalid\\share", "/catalog/index.html")

    def test_same_origin_url_containing_backslash_is_not_canonical(self):
        self.assert_unsafe(resolve_page, "https://fixture.invalid/catalog\\record.html", "/catalog/index.html")

    def test_backslash_in_start_is_rejected_before_lookup(self):
        pages = {"/index.html": '<p id="name">Ada</p>'}
        self.assert_unsafe(run_trace, pages, "/index\\html", [])

    def test_backslash_page_inventory_key_is_preflight_rejected(self):
        pages = {"/index.html": '<p id="name">Ada</p>', "/unused\\record.html": '<p>Other</p>'}
        self.assert_unsafe(run_trace, pages, "/index.html", [])

    def test_backslash_follow_is_rejected_with_valid_supplied_pages(self):
        pages = {"/catalog/index.html": '<a id="next" href="v2\\record.html">Next</a>',
                 "/catalog/v2/record.html": '<p id="name">Ada</p>'}
        actions = [{"op": "select", "selector": "#next"}, {"op": "follow", "kind": "next"}]
        self.assert_unsafe(run_trace, pages, "/catalog/index.html", actions)

    def test_backslash_document_base_is_rejected(self):
        pages = {"/catalog/index.html": '<base href="v2\\"><p id="name">Ada</p>'}
        self.assert_unsafe(run_trace, pages, "/catalog/index.html", [])

    def test_unvisited_document_base_backslash_fails_preflight(self):
        pages = {"/index.html": '<p id="name">Ada</p>',
                 "/unvisited.html": '<base href="v2\\"><p>Other</p>'}
        self.assert_unsafe(run_trace, pages, "/index.html", [])

    def test_gold_evaluation_does_not_accept_ambiguous_follow(self):
        row = copy.deepcopy(demo_records()[3])
        row["pages"]["/details/index.html"] = row["pages"]["/details/index.html"].replace(
            'item.html', 'item\\old.html')
        self.assert_unsafe(evaluate, [row])

    def test_heldout_audit_rejects_before_scoring(self):
        splits = demo_partitions()
        row = next(item for item in splits["train"] if item["family"] == "detail")
        row["pages"]["/details/index.html"] = row["pages"]["/details/index.html"].replace(
            'item.html', 'item\\old.html')
        self.assert_unsafe(audit_and_evaluate, splits)

    def test_literal_backslash_in_plain_html_text_remains_valid_data(self):
        pages = {"/index.html": '<p id="name">C:\\Users\\Ada</p>'}
        actions = [{"op": "select", "selector": "#name"}, {"op": "extract", "field": "name"}]
        self.assertEqual(run_trace(pages, "/index.html", actions)["extractions"],
                         {"name": "C:\\Users\\Ada"})

    def test_normal_slash_paths_and_relative_follow_remain_valid(self):
        pages = {"/catalog/index.html": '<a id="next" href="v2/record.html">Next</a>',
                 "/catalog/v2/record.html": '<p id="name">Ada</p>'}
        actions = [{"op": "select", "selector": "#next"}, {"op": "follow", "kind": "next"},
                   {"op": "select", "selector": "#name"}, {"op": "extract", "field": "name"}]
        result = run_trace(pages, "/catalog/index.html", actions)
        self.assertEqual(result["visited"], ["/catalog/index.html", "/catalog/v2/record.html"])
        self.assertEqual(result["extractions"], {"name": "Ada"})

    def test_repeated_bad_path_has_deterministic_failure(self):
        one = self.assert_unsafe(resolve_page, "v2\\record.html", "/catalog/index.html")
        two = self.assert_unsafe(resolve_page, "v2\\record.html", "/catalog/index.html")
        self.assertEqual(one, two)

    def test_existing_offline_demo_output_remains_deterministic(self):
        one = json.dumps(evaluate(demo_records()), sort_keys=True, separators=(",", ":"))
        two = json.dumps(evaluate(demo_records()), sort_keys=True, separators=(",", ":"))
        self.assertEqual(one, two)


if __name__ == "__main__":
    unittest.main()
