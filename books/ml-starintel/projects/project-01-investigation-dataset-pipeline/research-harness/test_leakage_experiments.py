#!/usr/bin/env python3
"""Protocol tests for Tier C leakage Experiments A--C.

These tests assert the predeclared experimental invariants. They intentionally do
not assert that a hypothesis must win by a particular score margin.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import run_leakage_experiments as subject


class LeakageExperimentProtocolTests(unittest.TestCase):
    def test_entity_fixture_is_deterministic_balanced_and_repeated(self) -> None:
        first = subject.generate_entity_fixture()
        second = subject.generate_entity_fixture()
        self.assertEqual(first, second)
        self.assertEqual(len(first), 160 * 4)
        self.assertEqual(sum(row["label"] for row in first), len(first) // 2)
        counts: dict[str, int] = {}
        for row in first:
            counts[row["entity_id"]] = counts.get(row["entity_id"], 0) + 1
        self.assertEqual(set(counts.values()), {4})

    def test_entity_group_split_has_no_entity_overlap(self) -> None:
        rows = subject.generate_entity_fixture()
        train, test = subject.entity_group_split(rows)
        train_entities = {rows[index]["entity_id"] for index in train}
        test_entities = {rows[index]["entity_id"] for index in test}
        self.assertTrue(train_entities)
        self.assertTrue(test_entities)
        self.assertFalse(train_entities & test_entities)

    def test_row_random_entity_split_is_deterministic(self) -> None:
        rows = subject.generate_entity_fixture()
        self.assertEqual(subject.row_random_split(rows), subject.row_random_split(rows))

    def test_temporal_fixture_is_deterministic_and_balanced(self) -> None:
        rows = subject.generate_temporal_fixture()
        self.assertEqual(rows, subject.generate_temporal_fixture())
        self.assertEqual(len(rows), 24 * 24)
        self.assertEqual(sum(row["label"] for row in rows), len(rows) // 2)

    def test_temporal_split_orders_all_training_observations_before_test(self) -> None:
        rows = subject.generate_temporal_fixture()
        train, test = subject.temporal_split(rows)
        self.assertLess(
            max(rows[index]["observed_at"] for index in train),
            min(rows[index]["observed_at"] for index in test),
        )
        self.assertEqual({rows[index]["month"] for index in train}, set(range(1, 19)))
        self.assertEqual({rows[index]["month"] for index in test}, set(range(19, 25)))

    def test_point_in_time_features_exclude_future_resolution(self) -> None:
        row = subject.generate_temporal_fixture()[0]
        leaked = subject.temporal_text(row, point_in_time=False)
        clean = subject.temporal_text(row, point_in_time=True)
        self.assertIn("future_resolution_", leaked)
        self.assertNotIn("future_resolution_", clean)
        self.assertGreater(row["future_resolution_available_at"], row["observed_at"])

    def test_normalization_and_exact_hash_are_stable(self) -> None:
        left = "ACME,   Holdings!  Report\nALPHA"
        right = "acme holdings report alpha"
        self.assertEqual(subject.normalize_text(left), subject.normalize_text(right))
        self.assertEqual(subject.exact_text_hash(left), subject.exact_text_hash(right))

    def test_jaccard_threshold_boundary_is_inclusive(self) -> None:
        # 4-token intersection / 5-token union = 0.80 exactly.
        left = "alpha beta gamma delta"
        right = "alpha beta gamma delta epsilon"
        self.assertAlmostEqual(subject.token_jaccard(left, right), 0.8)
        self.assertTrue(subject.is_near_duplicate(left, right))
        below = "alpha beta gamma zeta eta"
        self.assertLess(subject.token_jaccard(left, below), subject.NEAR_DUPLICATE_THRESHOLD)
        self.assertFalse(subject.is_near_duplicate(left, below))

    def test_duplicate_fixture_and_components_are_deterministic(self) -> None:
        rows = subject.generate_duplicate_fixture()
        self.assertEqual(rows, subject.generate_duplicate_fixture())
        self.assertEqual(len(rows), 160 * 3)
        components = subject.near_duplicate_components(rows)
        self.assertEqual(components, subject.near_duplicate_components(rows))
        self.assertEqual(len(set(components.values())), 160)
        for base_index in range(160):
            ids = [f"dup-{base_index:03d}-{variant}" for variant in ("original", "exact", "near")]
            self.assertEqual(len({components[record_id] for record_id in ids}), 1)

    def test_duplicate_cluster_split_has_zero_exact_and_near_overlap(self) -> None:
        rows = subject.generate_duplicate_fixture()
        train, test, components = subject.duplicate_cluster_split(rows)
        contamination = subject.duplicate_contamination(rows, train, test, components)
        self.assertEqual(contamination["exact_hash_overlap_count"], 0)
        self.assertEqual(contamination["near_component_overlap_count"], 0)
        self.assertEqual(contamination["exact_test_contamination_rate"], 0.0)
        self.assertEqual(contamination["near_test_contamination_rate"], 0.0)

    def test_vectorizer_is_fit_only_on_training_texts(self) -> None:
        model = subject.fit_text_classifier(
            ["known alpha", "known beta", "known alpha", "known beta"],
            [0, 1, 0, 1],
        )
        vocabulary = model.named_steps["tfidf"].vocabulary_
        self.assertIn("known", vocabulary)
        self.assertNotIn("test_only_token", vocabulary)
        # Prediction must not mutate/further-fit the vocabulary.
        before = dict(vocabulary)
        model.predict(["test_only_token alpha"])
        self.assertEqual(before, model.named_steps["tfidf"].vocabulary_)

    def test_run_all_has_stable_schema_and_plot_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            result = subject.run_all(output, render_plots=False)
            self.assertEqual(result["protocol_version"], "leakage-v1")
            self.assertEqual(set(result["experiments"]), {"A", "B", "C"})
            for name in ("A", "B", "C"):
                self.assertEqual(result["experiments"][name]["status"], "TESTED")
            self.assertEqual(
                result["plot_paths"],
                {
                    "A": "leakage-a-entity-split.svg",
                    "B": "leakage-b-temporal-availability.svg",
                    "C": "leakage-c-duplicates.svg",
                },
            )


if __name__ == "__main__":
    unittest.main()
