from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import project1


class Project1ReaderCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = project1.build_report(offline=True)

    def test_reader_report_is_green_for_frozen_checkpoint(self) -> None:
        self.assertEqual(self.report["status"], "TESTED")
        self.assertTrue(all(self.report["invariants"].values()))

    def test_provenance_summary_does_not_embed_source_documents(self) -> None:
        provenance = self.report["provenance"]
        self.assertEqual(provenance["document_count"], 5)
        self.assertEqual(provenance["org_count"], 3)
        self.assertEqual(provenance["relation_count"], 2)
        self.assertNotIn("documents", provenance)
        self.assertTrue(provenance["all_validation_records_valid"])

    def test_split_report_keeps_group_and_time_contracts_explicit(self) -> None:
        split = self.report["split"]
        self.assertTrue(split["default_policy_clean"])
        self.assertEqual(
            split["opt_in_graph_grouping"]["status"],
            "infeasible_as_expected",
        )
        self.assertGreater(
            split["opt_in_graph_grouping"]["diagnostics"]["straddling_component_count"],
            0,
        )

    def test_candidate_generation_is_not_duplicate_truth(self) -> None:
        duplicate = self.report["duplicate_candidates"]
        self.assertEqual(duplicate["qualifying_pair_recall"], 1.0)
        self.assertTrue(duplicate["component_equality"])
        self.assertTrue(duplicate["input_permutation_equal"])
        self.assertGreater(duplicate["false_positive_candidate_count"], 0)
        self.assertIn("exact normalized-token Jaccard", duplicate["claim_scope"])

    def test_report_write_is_deterministic_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            project1.write_report(self.report, first)
            project1.write_report(self.report, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            loaded = json.loads(first.read_text(encoding="utf-8"))
            self.assertEqual(loaded, self.report)


if __name__ == "__main__":
    unittest.main()
