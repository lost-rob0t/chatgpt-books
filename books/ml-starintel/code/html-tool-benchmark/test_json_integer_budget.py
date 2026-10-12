"""BK08: integer tokens in offline JSONL are bounded independently of Python settings."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from offline_html_trace_executor import TraceFailure, read_jsonl


class JSONIntegerBudgetTests(unittest.TestCase):
    def parse(self, literal: str):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            path.write_text('{"numeric":' + literal + '}\n', encoding="utf-8")
            return read_jsonl(path)

    def assert_invalid_integer(self, literal: str):
        with self.assertRaises(TraceFailure) as caught:
            self.parse(literal)
        self.assertEqual(caught.exception.code, "invalid_record")
        self.assertIn("integer", str(caught.exception).lower())

    def test_budget_is_a_fixed_explicit_constant(self):
        from offline_html_trace_executor import MAX_JSON_INTEGER_DIGITS
        self.assertEqual(MAX_JSON_INTEGER_DIGITS, 256)

    def test_positive_integer_at_budget_parses_exactly(self):
        literal = "9" * 256
        self.assertEqual(self.parse(literal)[0]["numeric"], int(literal))

    def test_negative_integer_at_budget_parses_exactly(self):
        literal = "-" + "9" * 256
        self.assertEqual(self.parse(literal)[0]["numeric"], int(literal))

    def test_positive_integer_over_budget_fails_closed(self):
        self.assert_invalid_integer("9" * 257)

    def test_negative_integer_over_budget_fails_closed(self):
        self.assert_invalid_integer("-" + "9" * 257)

    def test_very_large_int_uses_typed_failure_not_python_valueerror(self):
        self.assert_invalid_integer("8" * 6_000)

    def test_later_line_integer_is_preflight_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            path.write_text('{"numeric":1}\n{"numeric":' + "8" * 6_000 + '}\n', encoding="utf-8")
            with self.assertRaises(TraceFailure) as caught:
                read_jsonl(path)
            self.assertEqual(caught.exception.code, "invalid_record")

    def test_quoted_digits_do_not_count_as_integer_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            path.write_text(json.dumps({"numeric": "9" * 6_000}) + "\n", encoding="utf-8")
            self.assertEqual(read_jsonl(path)[0]["numeric"], "9" * 6_000)

    def test_regular_zero_negative_and_small_positive_unchanged(self):
        self.assertEqual(self.parse("0")[0]["numeric"], 0)
        self.assertEqual(self.parse("-0")[0]["numeric"], 0)
        self.assertEqual(self.parse("8675309")[0]["numeric"], 8_675_309)

    def test_finite_float_parsing_remains_distinct(self):
        self.assertEqual(self.parse("12.5")[0]["numeric"], 12.5)

    def test_nonfinite_exponent_remains_a_typed_invalid_record(self):
        with self.assertRaises(TraceFailure) as caught:
            self.parse("1e999999")
        self.assertEqual(caught.exception.code, "invalid_record")

    def test_cli_rejects_oversized_literal_with_no_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            path.write_text('{"numeric":' + "9" * 6_000 + '}\n', encoding="utf-8")
            executor = Path(__file__).with_name("offline_html_trace_executor.py")
            command = [sys.executable, str(executor), "--evaluate", str(path)]
            first = subprocess.run(command, capture_output=True, text=True)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 2)
            self.assertEqual(first.stderr, second.stderr)
            self.assertIn("invalid_record", first.stderr)
            self.assertNotIn("Traceback", first.stderr)
            self.assertEqual(first.stdout, "")


if __name__ == "__main__":
    unittest.main()
