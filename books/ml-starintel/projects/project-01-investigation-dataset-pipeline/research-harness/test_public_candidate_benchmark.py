#!/usr/bin/env python3
"""Network-free regressions for the predeclared public candidate benchmark."""

from __future__ import annotations

import unittest

from public_candidate_benchmark import (
    NUM_PERM_GRID,
    THRESHOLD,
    PublicCorpusPolicy,
    evaluate_grid,
    exact_oracle_pairs,
    select_public_rows,
)


def fixture_text(index: int) -> str:
    shared = "investigation public source record evidence observation relationship"
    unique = " ".join(f"token{index:02d}{suffix}" for suffix in "abcdefghijklmnop")
    return f"{shared} {unique}"


class PublicCandidateBenchmarkTests(unittest.TestCase):
    def test_selection_is_content_defined_not_input_order(self) -> None:
        texts = [fixture_text(index) for index in range(12)]
        policy = PublicCorpusPolicy(
            original_count=8,
            controlled_variant_count=3,
            min_token_count=10,
        )
        forward = select_public_rows(texts, policy=policy)
        reverse = select_public_rows(list(reversed(texts)), policy=policy)
        self.assertEqual(forward, reverse)
        self.assertEqual(len(forward), 11)
        self.assertEqual(
            sum(row["kind"] == "controlled-near-duplicate" for row in forward),
            3,
        )

    def test_controlled_variants_are_above_frozen_threshold(self) -> None:
        rows = select_public_rows(
            [fixture_text(index) for index in range(8)],
            policy=PublicCorpusPolicy(
                original_count=6,
                controlled_variant_count=2,
                min_token_count=10,
            ),
        )
        variants = [row for row in rows if row["kind"] == "controlled-near-duplicate"]
        self.assertEqual(len(variants), 2)
        for row in variants:
            self.assertGreaterEqual(row["control_jaccard"], THRESHOLD)

    def test_exact_oracle_finds_controlled_pairs(self) -> None:
        rows = select_public_rows(
            [fixture_text(index) for index in range(8)],
            policy=PublicCorpusPolicy(
                original_count=6,
                controlled_variant_count=2,
                min_token_count=10,
            ),
        )
        qualifying = set(exact_oracle_pairs(rows))
        for row in rows:
            if row["kind"] != "controlled-near-duplicate":
                continue
            pair = tuple(sorted((row["record_id"], row["derived_from"])))
            self.assertIn(pair, qualifying)

    def test_grid_is_frozen_before_measurement(self) -> None:
        rows = select_public_rows(
            [fixture_text(index) for index in range(8)],
            policy=PublicCorpusPolicy(
                original_count=6,
                controlled_variant_count=2,
                min_token_count=10,
            ),
        )
        with self.assertRaisesRegex(ValueError, "grid is frozen"):
            evaluate_grid(rows, num_perm_grid=(32,))
        self.assertEqual(NUM_PERM_GRID, (64, 128, 256))

    def test_small_grid_preserves_exact_components(self) -> None:
        rows = select_public_rows(
            [fixture_text(index) for index in range(10)],
            policy=PublicCorpusPolicy(
                original_count=8,
                controlled_variant_count=3,
                min_token_count=10,
            ),
        )
        result = evaluate_grid(rows)
        self.assertEqual(result["status"], "TESTED")
        self.assertEqual([entry["num_perm"] for entry in result["grid"]], [64, 128, 256])
        for entry in result["grid"]:
            self.assertTrue(entry["component_equality"])
            self.assertEqual(entry["qualifying_pair_recall"], 1.0)
            self.assertGreaterEqual(entry["minhash_lsh_qualifying_pair_recall"], 0.0)
            self.assertLessEqual(entry["minhash_lsh_qualifying_pair_recall"], 1.0)


if __name__ == "__main__":
    unittest.main()
