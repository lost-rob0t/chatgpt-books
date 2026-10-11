"""BK08: UTF-8 boundary regressions for static fixture data and JSONL inputs.

JSON permits escaped surrogate code points even though UTF-8 cannot encode them.
The benchmark must return a typed deterministic error, not crash on serialization.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from offline_html_trace_executor import (
    TraceFailure,
    demo_records,
    evaluate,
    read_jsonl,
    resolve_page,
    run_trace,
)


class FixtureUtf8BoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.row = demo_records()[0]  # table fixture with a single well-formed page

    def expect_code(self, code, callback):
        with self.assertRaises(TraceFailure) as raised:
            callback()
        self.assertEqual(raised.exception.code, code)

    def test_lone_surrogates_in_fixture_html_have_typed_bounds_failure(self):
        for bad in ("\ud800", "\udfff", "alpha\udbffbeta", "\ud800\ud800"):
            with self.subTest(bad=repr(bad)):
                row = copy.deepcopy(self.row)
                row["pages"][row["start"]] += bad
                self.expect_code("parse_bounds", lambda: evaluate([row]))

    def test_lone_surrogates_in_page_paths_have_typed_navigation_failure(self):
        for bad in ("/bad\ud800.html", "/\udfff/next", "https://fixture.invalid/\ud800"):
            with self.subTest(bad=repr(bad)):
                self.expect_code("unsafe_navigation", lambda: resolve_page(bad))

    def test_lone_surrogate_in_inventory_key_rejected_before_any_html_execution(self):
        row = copy.deepcopy(self.row)
        html = row["pages"].pop(row["start"])
        row["pages"]["/invalid\ud800.html"] = html
        self.expect_code("unsafe_navigation", lambda: run_trace(row["pages"], row["start"], row["gold_trace"]))

    def test_jsonl_escaped_surrogate_is_typed_and_never_leaks_to_output(self):
        row = copy.deepcopy(self.row)
        row["pages"][row["start"]] += "\ud800"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.jsonl"
            path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
            loaded = read_jsonl(path)
            self.expect_code("parse_bounds", lambda: evaluate(loaded))

    def test_valid_non_ascii_content_is_still_accepted_and_has_stable_provenance(self):
        row = copy.deepcopy(self.row)
        row["pages"][row["start"]] = row["pages"][row["start"]].replace("Ada", "Zoë 🚀")
        row["gold_extractions"]["name"] = "Zoë 🚀"
        assert row["candidate_trace"] == row["gold_trace"]
        one = evaluate([row]); two = evaluate([row])
        self.assertEqual(one, two)
        self.assertEqual(one["metrics"]["sequence_success"], 1)
        self.assertEqual(one["cases"][0]["observed"]["extractions"]["name"], "Zoë 🚀")
        self.assertEqual(len(one["cases"][0]["observed"]["page_sha256"][row["start"]]), 64)

    def test_valid_non_ascii_path_is_allowed_on_static_origin(self):
        self.assertEqual(resolve_page("/pages/café.html"), "/pages/café.html")
        self.assertEqual(resolve_page("/pages/🚀.html"), "/pages/🚀.html")

    def test_non_string_fixture_values_keep_their_typed_bounds_failure(self):
        for bad in (None, 123, [], {"html": "x"}):
            with self.subTest(bad=bad):
                row = copy.deepcopy(self.row)
                row["pages"][row["start"]] = bad
                self.expect_code("parse_bounds", lambda: evaluate([row]))

    def test_regression_preserves_existing_gold_and_malformed_family(self):
        for row in demo_records():
            with self.subTest(family=row["family"]):
                authoritative = run_trace(row["pages"], row["start"], row["gold_trace"])
                self.assertEqual(authoritative["extractions"], row["gold_extractions"])
                self.assertEqual(authoritative["visited"], row["gold_visited"])


if __name__ == "__main__":
    unittest.main()
