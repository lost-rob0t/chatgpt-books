"""BK08: reject ambiguous JSONL corpus inputs before any HTML evaluation."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from offline_html_trace_executor import TraceFailure, demo_records, evaluate, read_jsonl


class JsonlIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.row = copy.deepcopy(demo_records()[0])

    def load(self, *lines):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.jsonl"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return read_jsonl(path)

    def rejects(self, line):
        with self.assertRaises(TraceFailure) as failure:
            self.load(line)
        self.assertEqual(failure.exception.code, "invalid_record")

    def test_duplicate_root_and_escaped_identity(self):
        line = json.dumps(self.row, sort_keys=True)
        for member in ('"id":"tables_01"', '"id":"changed_01"', '"\\u0069d":"tables_01"'):
            with self.subTest(member=member):
                self.rejects(line[:-1] + "," + member + "}")

    def test_duplicate_nested_page_action_and_gold_field(self):
        line = json.dumps(self.row, sort_keys=True)
        key = json.dumps(self.row["start"]) + ": "
        selector = '"selector": "td#table-name"'
        golden = '"gold_extractions": {"name": "Ada"}'
        for altered in (
            line.replace(key, key + json.dumps(self.row["pages"][self.row["start"]]) + ", " + key, 1),
            line.replace(selector, selector + ", " + selector, 1),
            line.replace(golden, '"gold_extractions": {"name": "Ada", "name": "Ada"}', 1),
        ):
            with self.subTest(altered=altered[:60]):
                self.rejects(altered)

    def test_nonfinite_numbers_and_exponent_overflow(self):
        for token in ("NaN", "Infinity", "-Infinity", "1e999"):
            with self.subTest(token=token):
                row = copy.deepcopy(self.row)
                row["candidate_trace"][0]["selector"] = 1.5
                line = json.dumps(row, sort_keys=True).replace("1.5", token, 1)
                self.rejects(line)

    def test_deep_nesting_rejected_and_quoted_brackets_allowed(self):
        self.rejects("[" * 1000 + "0" + "]" * 1000)
        row = copy.deepcopy(self.row)
        row["pages"][row["start"]] += "<p>" + "[{" * 128 + "</p>"
        self.assertEqual(self.load(json.dumps(row))[0]["pages"], row["pages"])

    def test_all_lines_validated_before_scoring(self):
        valid = json.dumps(self.row, sort_keys=True)
        with self.assertRaises(TraceFailure) as failure:
            self.load(valid, valid[:-1] + ',"id":"shadowed_01"}')
        self.assertEqual(failure.exception.code, "invalid_record")

    def test_valid_unicode_and_permuted_key_order_are_deterministic(self):
        row = copy.deepcopy(self.row)
        row["pages"][row["start"]] = row["pages"][row["start"]].replace("Ada", "Zoë 🚀")
        row["gold_extractions"]["name"] = "Zoë 🚀"
        one = self.load(json.dumps(row, sort_keys=True, ensure_ascii=False))
        two = self.load(json.dumps(row, sort_keys=False, ensure_ascii=False))
        self.assertEqual(evaluate(one), evaluate(two))
        self.assertEqual(evaluate(one)["metrics"]["sequence_success"], 1)


if __name__ == "__main__":
    unittest.main()
