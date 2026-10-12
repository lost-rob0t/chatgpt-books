"""BK08: exclude noncontent DOM subtrees from unlabeled node baselines."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from html_heldout_baselines import (
    TrainOnlyNodeRanker, _predict, _visible_candidates, observation,
    projected_partitions, run_bench,
)
from offline_html_trace_executor import run_trace


class StaticHiddenCandidateTests(unittest.TestCase):
    def view(self, html: str) -> dict:
        return {"id": "static_visibility", "family": "synthetic", "pages": {"/index.html": html},
                "start": "/index.html"}

    def selectors(self, html: str) -> list[str]:
        return [node.attrs.get("id", "") for node in _visible_candidates(html)]

    def test_head_metadata_never_becomes_a_ranked_record(self):
        html = "<head><title id='wrong'>Metadata</title></head><main><span id='actual'>Ada</span></main>"
        self.assertEqual(self.selectors(html), ["actual"])

    def test_template_descendants_are_not_record_candidates(self):
        html = "<template><article><span id='wrong'>Fake</span></article></template><b id='actual'>Ada</b>"
        self.assertEqual(self.selectors(html), ["actual"])

    def test_script_style_and_template_subtrees_are_pruned(self):
        html = "<script>discard</script><style>discard</style><template><b id='wrong'>Fake</b></template><b id='actual'>Ada</b>"
        self.assertEqual(self.selectors(html), ["actual"])

    def test_boolean_hidden_attribute_skips_whole_subtree(self):
        html = "<div hidden><b id='wrong'>Fake</b></div><b id='actual'>Ada</b>"
        self.assertEqual(self.selectors(html), ["actual"])

    def test_boolean_hidden_false_string_still_means_hidden(self):
        html = "<div hidden='false'><b id='wrong'>Fake</b></div><b id='actual'>Ada</b>"
        self.assertEqual(self.selectors(html), ["actual"])

    def test_aria_hidden_true_skips_whole_subtree(self):
        html = "<div aria-hidden=' TRUE '><b id='wrong'>Fake</b></div><b id='actual'>Ada</b>"
        self.assertEqual(self.selectors(html), ["actual"])

    def test_aria_hidden_false_is_not_hidden(self):
        html = "<div aria-hidden='false'><b id='visible'>Visible</b></div><b id='actual'>Ada</b>"
        self.assertEqual(self.selectors(html), ["visible", "actual"])

    def test_static_heuristic_does_not_select_metadata_decoy(self):
        html = "<head><title id='wrong'>Fake</title></head><main><span id='actual'>Ada</span></main>"
        view = self.view(html)
        trace = _predict(view, "name", None, follow_links=True)
        self.assertEqual(trace, [{"op": "select", "selector": "#actual"},
                                 {"op": "extract", "field": "name"}])
        self.assertEqual(run_trace(view["pages"], view["start"], trace)["extractions"], {"name": "Ada"})

    def test_ranker_weights_not_polluted_by_hidden_training_decoys(self):
        train = projected_partitions()["train"]
        original = TrainOnlyNodeRanker(train)
        poisoned = copy.deepcopy(train)
        for row in poisoned:
            start = row["start"]
            row["pages"][start] = ("<template><span id='unseen-decoy'>Bad</span></template>"
                                   + row["pages"][start])
        learner = TrainOnlyNodeRanker(poisoned)
        self.assertEqual(learner.weights, original.weights)
        self.assertEqual(learner.field, original.field)

    def test_predicted_heldout_trace_ignores_unscored_hidden_decoy(self):
        rows = projected_partitions()
        ranker = TrainOnlyNodeRanker(rows["train"])
        original = observation(rows["test"][0])
        mutated = copy.deepcopy(original)
        path = mutated["start"]
        mutated["pages"][path] = ("<template><span id='unseen-decoy'>Bogus</span></template>"
                                  + mutated["pages"][path])
        self.assertEqual(ranker.predict(mutated), ranker.predict(original))

    def test_existing_heldout_report_still_evaluates_all_families(self):
        report = run_bench(projected_partitions())
        self.assertEqual(report["audit"]["samples"], 60)
        self.assertEqual(report["schema"], "bk08.heldout-node-baselines/v2")
        for method in report["baselines"].values():
            self.assertEqual(sum(report_row["samples"] for report_row in method.values()), 60)

    def test_native_cli_is_deterministic_for_new_contract(self):
        script = Path(__file__).with_name("html_heldout_baselines.py")
        command = [sys.executable, str(script), "--demo"]
        first = subprocess.run(command, capture_output=True, check=True).stdout
        second = subprocess.run(command, capture_output=True, check=True).stdout
        self.assertEqual(first, second)
        self.assertEqual(json.loads(first)["report"]["schema"], "bk08.heldout-node-baselines/v2")


if __name__ == "__main__":
    unittest.main()
