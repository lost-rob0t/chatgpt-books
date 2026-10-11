"""Native, offline metamorphic checks for the complete BK08 HTML oracle."""
import copy
import hashlib
import io
from contextlib import redirect_stdout
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import html_trace_perturbations as subject
from offline_html_trace_executor import TraceFailure, demo_records, run_trace


class MetamorphicTests(unittest.TestCase):
    def test_exact_60_neutral_variants(self):
        self.assertEqual(len(subject.derived_records()), 60)

    def test_exact_five_collision_cases(self):
        self.assertEqual(len(subject.collision_records()), 5)

    def test_distinct_ids(self):
        items = subject.derived_records() + subject.collision_records()
        self.assertEqual(len(items), len({item["id"] for item in items}))

    def test_all_five_families_covered(self):
        self.assertEqual(set(subject.FAMILY_SPLITS), {x["family"] for x in demo_records()})

    def test_neutral_extractions_and_navigation_invariant(self):
        gold = {case["family"]: case for case in demo_records()}
        for case in subject.derived_records():
            with self.subTest(case=case["id"]):
                base = gold[case["source_family"]]
                a = run_trace(base["pages"], base["start"], base["gold_trace"])
                b = run_trace(case["pages"], case["start"], case["gold_trace"])
                self.assertEqual(a["extractions"], b["extractions"])
                self.assertEqual(a["visited"], b["visited"])

    def test_all_60_input_pages_have_distinct_digests(self):
        rows = subject.derived_records()
        digests = [hashlib.sha256(x["pages"][x["start"]].encode()).hexdigest() for x in rows]
        self.assertEqual(len(set(digests)), 60)

    def test_all_variants_grouped_with_source_family(self):
        for row in subject.derived_records():
            self.assertEqual(row["split"], subject.FAMILY_SPLITS[row["source_family"]])

    def test_each_collision_reports_ambiguity(self):
        for row in subject.collision_records():
            with self.subTest(case=row["id"]):
                with self.assertRaises(TraceFailure) as caught:
                    run_trace(row["pages"], row["start"], row["gold_trace"])
                self.assertEqual(caught.exception.code, "selector_ambiguous")

    def test_invalid_decoration_rejected(self):
        with self.assertRaises(AssertionError):
            subject.neutral_mutation("<p>x</p>", "alter_data", "mark")

    def test_audit_report_is_concrete(self):
        output = subject.verify()
        self.assertEqual(output["neutral_html_invariants"], 60)
        self.assertEqual(output["selector_collisions_rejected"], 5)
        self.assertTrue(output["all_passed"])

    def test_cli_byte_identical(self):
        script = Path(subject.__file__)
        command = [sys.executable, str(script), "--verify"]
        first = subprocess.run(command, check=True, capture_output=True).stdout
        second = subprocess.run(command, check=True, capture_output=True).stdout
        self.assertEqual(first, second)

    def test_wrong_collision_guard_is_detected_by_negative_control(self):
        # Controlled RED: treating both matches as success is a benchmark bug.
        with patch.object(subject, "collision_records", return_value=[]):
            # Deliberately remove collision controls and demonstrate missing coverage.
            result = subject.verify()
        self.assertEqual(result["selector_collisions_rejected"], 0)
        self.assertNotEqual(result["selector_collisions_rejected"], 5)


if __name__ == "__main__":
    unittest.main()
