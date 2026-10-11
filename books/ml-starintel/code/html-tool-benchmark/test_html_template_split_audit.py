"""BK08 template-leakage audit regressions using real offline HTML execution."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from offline_html_trace_executor import TraceFailure
from html_template_split_audit import audit_and_evaluate, demo_partitions, template_digest


class TemplateSplitAuditTests(unittest.TestCase):
    def specimen(self):
        return copy.deepcopy(demo_partitions())

    def expect(self, code, rows):
        with self.assertRaises(TraceFailure) as raised:
            audit_and_evaluate(rows)
        self.assertEqual(raised.exception.code, code)

    def test_demo_five_family_outputs_are_measured(self):
        report = audit_and_evaluate(self.specimen())
        self.assertEqual(report["samples"], 5)
        self.assertEqual(report["family_count"], 5)
        self.assertEqual([report["splits"][k]["samples"] for k in ("train", "dev", "test")], [3, 1, 1])
        self.assertEqual(report["splits"]["dev"]["metrics"]["extraction_success"], 0.0)

    def test_family_overlap_is_rejected_even_with_different_markup(self):
        rows = self.specimen()
        moved = copy.deepcopy(rows["train"][0])
        moved["id"] = "tables_02"
        moved["pages"] = {"/unique.html": "<custom id='not_same'>Z</custom>"}
        moved["start"] = "/unique.html"
        moved["gold_trace"] = [{"op": "select", "selector": "#not_same"}, {"op": "extract", "field": "name"}]
        moved["candidate_trace"] = copy.deepcopy(moved["gold_trace"])
        moved["gold_extractions"] = {"name": "Z"}
        moved["gold_visited"] = ["/unique.html"]
        rows["dev"].append(moved)
        self.expect("split_leakage", rows)

    def test_identical_templates_across_different_families_are_rejected(self):
        rows = self.specimen()
        rows["test"][0]["pages"] = copy.deepcopy(rows["dev"][0]["pages"])
        rows["test"][0]["start"] = rows["dev"][0]["start"]
        rows["test"][0]["gold_trace"] = copy.deepcopy(rows["dev"][0]["gold_trace"])
        rows["test"][0]["candidate_trace"] = copy.deepcopy(rows["dev"][0]["candidate_trace"])
        rows["test"][0]["gold_extractions"] = copy.deepcopy(rows["dev"][0]["gold_extractions"])
        rows["test"][0]["gold_visited"] = copy.deepcopy(rows["dev"][0]["gold_visited"])
        self.expect("split_leakage", rows)

    def test_text_href_and_id_value_changes_do_not_mask_clone(self):
        one = "<article id='a'><span class='left'>Ada</span><a href='one.html'>Open</a></article>"
        two = "<article id='b'><span class='right'>Grace</span><a href='two.html'>Details</a></article>"
        self.assertEqual(template_digest(one), template_digest(two))

    def test_structure_changes_do_change_digest(self):
        self.assertNotEqual(template_digest("<article><span>Ada</span></article>"),
                            template_digest("<article><p>Ada</p></article>"))

    def test_attribute_key_changes_do_change_digest(self):
        self.assertNotEqual(template_digest("<a href='a'>Hello</a>"),
                            template_digest("<a id='a'>Hello</a>"))

    def test_attribute_order_and_whitespace_ignore_decoration(self):
        self.assertEqual(template_digest("<div id='a' class='item'> A </div>"),
                         template_digest("<div class='different' id='b'>Another</div>"))

    def test_template_fingerprint_ignores_html_comment(self):
        self.assertEqual(template_digest("<div><p>hey</p></div>"),
                         template_digest("<!-- builder note --><div><p>bye</p></div>"))

    def test_duplicate_identity_fails_across_partitions(self):
        rows = self.specimen()
        rows["test"][0]["id"] = rows["dev"][0]["id"]
        self.expect("split_leakage", rows)

    def test_tampered_gold_must_fail_before_metrics(self):
        rows = self.specimen()
        rows["train"][0]["gold_extractions"]["name"] = "invented"
        self.expect("gold_mismatch", rows)

    def test_missing_split_and_empty_split_rejected(self):
        rows = self.specimen()
        del rows["test"]
        self.expect("invalid_record", rows)
        rows = self.specimen()
        rows["test"] = []
        self.expect("invalid_record", rows)

    def test_input_permutation_is_deterministic(self):
        rows = self.specimen()
        expected = audit_and_evaluate(rows)
        rows["train"].reverse()
        for group in rows.values():
            for row in group:
                row["pages"] = dict(reversed(list(row["pages"].items())))
        self.assertEqual(audit_and_evaluate(rows), expected)

    def test_static_demo_cli_repeated_exact_bytes(self):
        cmd = [sys.executable, str(Path(__file__).with_name("html_template_split_audit.py")), "--demo"]
        first = subprocess.run(cmd, check=True, capture_output=True).stdout
        second = subprocess.run(cmd, check=True, capture_output=True).stdout
        self.assertEqual(first, second)
        self.assertTrue(json.loads(first)["passed"])

    def test_cli_jsonl_partitions_exact_evaluation(self):
        rows = self.specimen()
        with tempfile.TemporaryDirectory() as td:
            arguments = []
            for split in ("train", "dev", "test"):
                path = Path(td) / (split + ".jsonl")
                path.write_text("\n".join(json.dumps(r) for r in rows[split]) + "\n", encoding="utf-8")
                arguments.extend(["--" + split, str(path)])
            cmd = [sys.executable, str(Path(__file__).with_name("html_template_split_audit.py")), *arguments]
            actual = json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout)
            self.assertEqual(actual["audit"], audit_and_evaluate(rows))

    def test_template_digest_hex(self):
        digest = template_digest("<p class='a'>x</p>")
        self.assertEqual(len(digest), 64)
        self.assertEqual(set(digest) - set("0123456789abcdef"), set())


if __name__ == "__main__":
    unittest.main()
