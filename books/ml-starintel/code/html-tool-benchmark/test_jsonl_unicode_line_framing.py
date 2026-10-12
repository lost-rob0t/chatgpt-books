"""BK08 regression: only ASCII LF, optionally CRLF, frames JSONL records.

Unicode line-separator code points are legal inside JSON strings. They are data,
not extra JSONL record boundaries, even though str.splitlines() treats them as
separate lines.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from offline_html_trace_executor import TraceFailure, demo_records, evaluate, read_jsonl, run_trace


class JsonlUnicodeLineFramingTests(unittest.TestCase):
    def fixture(self, marker: str) -> dict:
        row = copy.deepcopy(demo_records()[0])
        row["pages"][row["start"]] = row["pages"][row["start"]].replace("Ada", "A" + marker + "da")
        row["gold_extractions"] = run_trace(row["pages"], row["start"], row["gold_trace"])["extractions"]
        row["candidate_trace"] = copy.deepcopy(row["gold_trace"])
        return row

    def load_text(self, text: str) -> list[dict]:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "corpus.jsonl"
            path.write_bytes(text.encode("utf-8"))
            return read_jsonl(path)

    def assert_valid_separator_in_string(self, marker: str) -> None:
        row = self.fixture(marker)
        decoded = self.load_text(json.dumps(row, ensure_ascii=False) + "\n")
        self.assertEqual(decoded, [row])
        measured = evaluate(decoded)
        self.assertEqual(measured["cases"][0]["extraction_success"], 1)
        self.assertEqual(measured["cases"][0]["observed"]["extractions"]["name"], row["gold_extractions"]["name"])

    def test_line_separator_literal_in_html_string(self):
        self.assert_valid_separator_in_string("\u2028")

    def test_paragraph_separator_literal_in_html_string(self):
        self.assert_valid_separator_in_string("\u2029")

    def test_next_line_literal_in_html_string(self):
        self.assert_valid_separator_in_string("\u0085")

    def test_horizontal_tab_escape_inside_html_string(self):
        self.assert_valid_separator_in_string("\t")

    def test_multiple_records_with_literal_unicode_separator(self):
        first = self.fixture("\u2028")
        second = self.fixture("\u2029")
        second["id"] = "tables_02"
        loaded = self.load_text("\n".join(json.dumps(row, ensure_ascii=False) for row in (first, second)) + "\n")
        self.assertEqual([row["id"] for row in loaded], ["tables_01", "tables_02"])
        self.assertEqual(evaluate(loaded)["samples"], 2)

    def test_crlf_is_a_valid_physical_separator(self):
        first = self.fixture("\u2028")
        second = self.fixture("\u2029")
        second["id"] = "tables_02"
        loaded = self.load_text("\r\n".join(json.dumps(row, ensure_ascii=False) for row in (first, second)) + "\r\n")
        self.assertEqual(len(loaded), 2)

    def test_escaped_unicode_separator_works_as_before(self):
        row = self.fixture("\u2028")
        self.assertEqual(self.load_text(json.dumps(row) + "\n"), [row])

    def test_ascii_lf_outside_json_string_separates_records(self):
        row = self.fixture("X")
        other = copy.deepcopy(row)
        other["id"] = "tables_02"
        loaded = self.load_text(json.dumps(row) + "\n" + json.dumps(other))
        self.assertEqual([item["id"] for item in loaded], ["tables_01", "tables_02"])

    def assert_not_a_separator(self, marker: str):
        row = self.fixture("Z")
        other = copy.deepcopy(row)
        other["id"] = "tables_02"
        with self.assertRaises(TraceFailure) as context:
            self.load_text(json.dumps(row) + marker + json.dumps(other))
        self.assertEqual(context.exception.code, "invalid_record")

    def test_u2028_between_json_objects_is_not_record_separator(self):
        self.assert_not_a_separator("\u2028")

    def test_u2029_between_json_objects_is_not_record_separator(self):
        self.assert_not_a_separator("\u2029")

    def test_nel_between_json_objects_is_not_record_separator(self):
        self.assert_not_a_separator("\u0085")

    def test_separator_as_whole_line_is_not_silently_skipped(self):
        self.assert_not_a_separator("\n\u2028\n")

    def test_ascii_whitespace_only_lines_are_ignored_as_before(self):
        row = self.fixture("X")
        loaded = self.load_text(" \t\r\n" + json.dumps(row) + "\r\n\t \n")
        self.assertEqual(loaded, [row])

    def test_repeated_identical_unicode_corpus_bytes(self):
        row = self.fixture("\u2028")
        text = json.dumps(row, ensure_ascii=False) + "\n"
        self.assertEqual(self.load_text(text), self.load_text(text))


if __name__ == "__main__":
    unittest.main()
