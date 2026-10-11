"""BK08: verify audited train-only predictions against real static HTML."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from html_heldout_baselines import (
    BENCHMARK_FAMILY_SPLITS, TrainOnlyNodeRanker, _predict, observation,
    projected_partitions, run_bench,
)
from html_template_split_audit import audit_and_evaluate
from html_trace_perturbations import FAMILY_SPLITS, derived_records
from offline_html_trace_executor import TraceFailure, evaluate, run_trace


class HeldoutBaselineTests(unittest.TestCase):
    def specimen(self):
        return projected_partitions()

    def test_generator_declared_split_is_actually_leaky(self):
        """Real RED: pagination/detail share the same anchor DOM skeleton."""
        naive = {part: [] for part in ("train", "dev", "test")}
        for record in derived_records():
            naive[FAMILY_SPLITS[record["family"]]].append({
                key: copy.deepcopy(record[key])
                for key in ("id", "family", "pages", "start", "gold_trace", "candidate_trace",
                            "gold_extractions", "gold_visited")
            })
        with self.assertRaises(TraceFailure) as caught:
            audit_and_evaluate(naive)
        self.assertEqual(caught.exception.code, "split_leakage")

    def test_heldout_plan_closes_template_components(self):
        rows = self.specimen()
        self.assertEqual([len(rows[key]) for key in ("train", "dev", "test")], [24, 24, 12])
        owners = {}
        for split, group in rows.items():
            for row in group:
                self.assertEqual(BENCHMARK_FAMILY_SPLITS[row["family"]], split)
                self.assertEqual(set(row), {"id", "family", "pages", "start", "gold_trace", "candidate_trace",
                                             "gold_extractions", "gold_visited"})
                self.assertNotIn(row["family"], owners) if row["family"] in owners and owners[row["family"]] != split else None
                owners[row["family"]] = split
        self.assertEqual(audit_and_evaluate(rows)["samples"], 60)

    def test_heldout_projection_preserves_gold_execution(self):
        for group in self.specimen().values():
            for row in group:
                actual = run_trace(row["pages"], row["start"], row["gold_trace"])
                self.assertEqual(actual["extractions"], row["gold_extractions"])
                self.assertEqual(actual["visited"], row["gold_visited"])

    def test_unlabeled_view_excludes_all_reference_fields(self):
        heldout = self.specimen()["dev"][0]
        view = observation(heldout)
        self.assertEqual(set(view), {"id", "family", "pages", "start"})
        self.assertNotIn("gold_trace", view)
        self.assertNotIn("candidate_trace", view)
        view["pages"][view["start"]] = "<p>altered</p>"
        self.assertNotEqual(view["pages"], heldout["pages"])

    def test_predictor_rejects_reference_fields(self):
        rows = self.specimen()
        ranker = TrainOnlyNodeRanker(rows["train"])
        with self.assertRaises(TraceFailure) as raised:
            ranker.predict(rows["dev"][0])
        self.assertEqual(raised.exception.code, "invalid_record")

    def test_heldout_gold_changes_cannot_change_predictions(self):
        rows = self.specimen()
        original = rows["test"][0]
        mutated = copy.deepcopy(original)
        mutated["gold_trace"] = [{"op": "select", "selector": "#fake"}]
        mutated["gold_extractions"] = {"name": "secret_gold"}
        ranker = TrainOnlyNodeRanker(rows["train"])
        for predict in (ranker.predict, lambda x: _predict(x, "name", None, follow_links=True)):
            self.assertEqual(predict(observation(original)), predict(observation(mutated)))

    def test_only_training_examples_fit_node_ranker(self):
        rows = self.specimen()
        learner = TrainOnlyNodeRanker(rows["train"])
        self.assertEqual(learner.trained_examples, 24)
        self.assertEqual(learner.trained_families, ["cards", "tables"])
        self.assertTrue(learner.weights)
        changed_heldout = copy.deepcopy(rows["dev"])
        changed_heldout[0]["gold_trace"] = []
        self.assertEqual(learner.weights, TrainOnlyNodeRanker(rows["train"]).weights)

    def test_training_row_permutation_does_not_change_fit(self):
        rows = self.specimen()
        self.assertEqual(TrainOnlyNodeRanker(rows["train"]).weights,
                         TrainOnlyNodeRanker(list(reversed(rows["train"]))).weights)

    def test_static_baseline_follows_heldout_navigation(self):
        rows = self.specimen()
        report = run_bench(rows)
        heuristic = report["baselines"]["static_heuristic"]
        self.assertEqual(heuristic["dev"]["samples"], 24)
        self.assertEqual(heuristic["dev"]["metrics"]["extraction_success"], 1.0)
        self.assertEqual(heuristic["dev"]["metrics"]["navigation_success"], 1.0)
        self.assertEqual(heuristic["dev"]["metrics"]["sequence_success"], 0.0)

    def test_ranker_reports_real_unseen_navigation_failures(self):
        report = run_bench(self.specimen())
        dev = report["baselines"]["train_only_node_ranker"]["dev"]
        self.assertEqual(dev["metrics"]["extraction_success"], 0.0)
        self.assertEqual(dev["failure_counts"], {"extraction_mismatch": 24})

    def test_extraction_success_not_misrepresented_as_sequence_accuracy(self):
        result = run_bench(self.specimen())
        table = result["baselines"]["static_heuristic"]["test"]["metrics"]
        self.assertEqual(table["extraction_success"], 1.0)
        self.assertEqual(table["sequence_success"], 0.0)
        self.assertLess(table["argument_accuracy"], 1.0)

    def test_all_scored_failures_sum_and_metric_bounds(self):
        report = run_bench(self.specimen())
        for method in report["baselines"].values():
            for value in method.values():
                self.assertEqual(sum(value["failure_counts"].values()), value["samples"])
                self.assertTrue(all(0.0 <= x <= 1.0 for x in value["metrics"].values()))

    def test_adversarial_template_clone_fails_before_scoring(self):
        rows = self.specimen()
        clone = copy.deepcopy(rows["train"][0])
        clone["id"] = "independent_but_cloned"
        clone["family"] = "pretend_new_family"
        rows["test"][0] = clone
        with self.assertRaises(TraceFailure) as raised:
            run_bench(rows)
        self.assertEqual(raised.exception.code, "split_leakage")

    def test_repeated_report_is_byte_identical(self):
        first = json.dumps(run_bench(self.specimen()), sort_keys=True)
        second = json.dumps(run_bench(self.specimen()), sort_keys=True)
        self.assertEqual(first, second)

    def test_one_command_demo_repeats_exact_bytes(self):
        script = str(Path(__file__).with_name("html_heldout_baselines.py"))
        args = [sys.executable, script, "--demo"]
        first = subprocess.run(args, capture_output=True, check=True).stdout
        second = subprocess.run(args, capture_output=True, check=True).stdout
        self.assertEqual(first, second)
        data = json.loads(first)
        self.assertTrue(data["passed"])
        self.assertEqual(data["report"]["audit"]["samples"], 60)

    def test_cli_accepts_actual_three_split_jsonl_files(self):
        with tempfile.TemporaryDirectory() as td:
            cli = [sys.executable, str(Path(__file__).with_name("html_heldout_baselines.py"))]
            for name, rows in self.specimen().items():
                path = Path(td, name + ".jsonl")
                path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")
                cli.extend(["--" + name, str(path)])
            result = subprocess.run(cli, capture_output=True, check=True, text=True)
            self.assertEqual(json.loads(result.stdout)["report"], run_bench(self.specimen()))

    def test_cli_rejects_contaminated_jsonl_with_typed_failure(self):
        rows = self.specimen()
        clone = copy.deepcopy(rows["train"][0])
        clone["id"] = "a_different_id"
        clone["family"] = "another_family"
        rows["dev"][0] = clone
        with tempfile.TemporaryDirectory() as td:
            cli = [sys.executable, str(Path(__file__).with_name("html_heldout_baselines.py"))]
            for name, cases in rows.items():
                path = Path(td, name + ".jsonl")
                path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in cases) + "\n", encoding="utf8")
                cli.extend(["--" + name, str(path)])
            result = subprocess.run(cli, capture_output=True, check=False, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["failure"], "split_leakage")

    def test_offline_run_does_not_use_network(self):
        import socket
        with patch.object(socket, "create_connection", side_effect=AssertionError("network call")):
            self.assertEqual(run_bench(self.specimen())["audit"]["samples"], 60)


if __name__ == "__main__":
    unittest.main()
