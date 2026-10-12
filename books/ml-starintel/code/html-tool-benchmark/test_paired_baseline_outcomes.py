"""BK08: compare baseline success on identical held-out examples, not means alone."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import html_heldout_baselines as baselines
from html_template_split_audit import audit_and_evaluate
from offline_html_trace_executor import TraceFailure


METRICS = ("extraction_success", "navigation_success", "sequence_success")
BUCKETS = ("both", "heuristic_only", "ranker_only", "neither")


def case(id_: str, extraction=0, navigation=0, sequence=0):
    return {"id": id_, "extraction_success": extraction,
            "navigation_success": navigation, "sequence_success": sequence}


class PairedBaselineOutcomesTests(unittest.TestCase):
    def paired(self, left, right, metric="extraction_success"):
        helper = getattr(baselines, "_paired_counts", None)
        self.assertIsNotNone(helper, "missing paired-outcome helper")
        return helper(left, right, metric)

    def test_all_four_joint_states_are_distinguished(self):
        left = [case("both", 1), case("h_only", 1), case("r_only"), case("neither")]
        right = [case("both", 1), case("h_only"), case("r_only", 1), case("neither")]
        self.assertEqual(self.paired(left, right), dict.fromkeys(BUCKETS, 1))

    def test_pairs_by_id_not_index_and_ignores_input_permutation(self):
        left = [case("a", 1), case("b"), case("c", 1)]
        right = [case("c", 1), case("a"), case("b", 1)]
        self.assertEqual(self.paired(left, right), {
            "both": 1, "heuristic_only": 1, "ranker_only": 1, "neither": 0})
        self.assertEqual(self.paired(list(reversed(left)), list(reversed(right))),
                         self.paired(left, right))

    def test_equal_individual_success_rates_can_hide_total_disagreement(self):
        left = [case("a", 1), case("b"), case("c", 1), case("d")]
        right = [case("a"), case("b", 1), case("c"), case("d", 1)]
        matrix = self.paired(left, right)
        self.assertEqual(sum(row["extraction_success"] for row in left), 2)
        self.assertEqual(sum(row["extraction_success"] for row in right), 2)
        self.assertEqual(matrix, {"both": 0, "heuristic_only": 2,
                                  "ranker_only": 2, "neither": 0})

    def test_empty_pairing_cannot_be_reported_as_measured(self):
        with self.assertRaises(TraceFailure) as caught:
            self.paired([], [])
        self.assertEqual(caught.exception.code, "invalid_record")

    def test_duplicate_heuristic_ids_fail_closed(self):
        with self.assertRaises(TraceFailure) as caught:
            self.paired([case("a"), case("a")], [case("a")])
        self.assertEqual(caught.exception.code, "invalid_record")

    def test_duplicate_ranker_ids_fail_closed(self):
        with self.assertRaises(TraceFailure) as caught:
            self.paired([case("a")], [case("a"), case("a")])
        self.assertEqual(caught.exception.code, "invalid_record")

    def test_missing_ranker_example_is_never_silent(self):
        with self.assertRaises(TraceFailure) as caught:
            self.paired([case("a"), case("b")], [case("a"), case("c")])
        self.assertEqual(caught.exception.code, "invalid_record")

    def test_invalid_binary_outcome_is_rejected(self):
        for bad in (2, -1, .5, True, None, "1"):
            with self.subTest(bad=bad), self.assertRaises(TraceFailure) as caught:
                self.paired([case("a", bad)], [case("a", 1)])
            self.assertEqual(caught.exception.code, "invalid_record")

    def test_missing_scored_metric_is_not_assumed_to_be_failure(self):
        with self.assertRaises(TraceFailure) as caught:
            self.paired([{"id": "a"}], [case("a")])
        self.assertEqual(caught.exception.code, "invalid_record")

    def test_unrecognized_metric_name_is_rejected(self):
        with self.assertRaises(TraceFailure) as caught:
            self.paired([case("a")], [case("a")], "gold_prefix_fraction")
        self.assertEqual(caught.exception.code, "invalid_record")

    def test_compared_dimensions_remain_separate(self):
        left = [case("x", 1, 1, 0)]
        right = [case("x", 0, 1, 1)]
        self.assertEqual(self.paired(left, right, "extraction_success")["heuristic_only"], 1)
        self.assertEqual(self.paired(left, right, "navigation_success")["both"], 1)
        self.assertEqual(self.paired(left, right, "sequence_success")["ranker_only"], 1)

    def test_frozen_60_fixture_report_partitions_have_complete_paired_counts(self):
        report = baselines.run_bench(baselines.projected_partitions())
        self.assertEqual(report["schema"], "bk08.heldout-node-baselines/v5")
        self.assertEqual(set(report["paired_outcomes"]), {"train", "dev", "test"})
        for split, amount in (("train", 24), ("dev", 24), ("test", 12)):
            matrix = report["paired_outcomes"][split]
            self.assertEqual(matrix["samples"], amount)
            for metric in METRICS:
                self.assertEqual(set(matrix[metric]), set(BUCKETS))
                self.assertEqual(sum(matrix[metric].values()), amount)
                heuristic = (matrix[metric]["both"] + matrix[metric]["heuristic_only"]) / amount
                ranker = (matrix[metric]["both"] + matrix[metric]["ranker_only"]) / amount
                self.assertAlmostEqual(heuristic, report["baselines"]["static_heuristic"][split]["metrics"][metric])
                self.assertAlmostEqual(ranker, report["baselines"]["train_only_node_ranker"][split]["metrics"][metric])

    def test_dev_extraction_is_heuristic_only_rather_than_mean_only(self):
        report = baselines.run_bench(baselines.projected_partitions())
        self.assertEqual(report["paired_outcomes"]["dev"]["extraction_success"],
                         {"both": 0, "heuristic_only": 24, "ranker_only": 0, "neither": 0})

    def test_split_leakage_rejects_before_joint_outcome_scoring(self):
        data = baselines.projected_partitions()
        bad = copy.deepcopy(data["train"][0])
        bad["id"], bad["family"] = "unique_but_cloned", "separate_family"
        data["test"][0] = bad
        with self.assertRaises(TraceFailure) as caught:
            baselines.run_bench(data)
        self.assertEqual(caught.exception.code, "split_leakage")

    def test_full_report_is_byte_stable_for_reordered_fixture_records(self):
        before = baselines.projected_partitions()
        after = {key: list(reversed(value)) for key, value in before.items()}
        first = json.dumps(baselines.run_bench(before), sort_keys=True)
        second = json.dumps(baselines.run_bench(after), sort_keys=True)
        self.assertEqual(first, second)

    def test_real_jsonl_cli_contains_identical_joint_outcomes(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            data = baselines.projected_partitions()
            for split in ("train", "dev", "test"):
                p = Path(folder, split + ".jsonl")
                p.write_text("\n".join(json.dumps(x, sort_keys=True) for x in data[split]) + "\n", encoding="utf-8")
                paths.extend(["--" + split, str(p)])
            command = [sys.executable, str(Path(baselines.__file__)), *paths]
            out = subprocess.run(command, capture_output=True, check=True, text=True)
            self.assertEqual(json.loads(out.stdout)["report"]["paired_outcomes"],
                             baselines.run_bench(data)["paired_outcomes"])


if __name__ == "__main__":
    unittest.main()
