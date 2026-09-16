#!/usr/bin/env python3
"""Regression tests for the frozen pass-11 near-duplicate candidate contract.

These tests intentionally compare the scalable candidate path with the existing
small all-pairs Tier C oracle.  They do not treat approximate LSH output as
truth: exact normalized-token Jaccard remains the duplicate predicate.
"""

from __future__ import annotations

import random
import unittest

from near_duplicate_candidates import (
    DEFAULT_CONFIG,
    evaluate_candidate_contract,
    generate_candidate_pairs,
    verified_duplicate_components,
)
from run_leakage_experiments import (
    generate_duplicate_fixture,
    near_duplicate_components,
    token_jaccard,
)


class NearDuplicateCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = generate_duplicate_fixture()

    def test_candidate_output_is_canonical_and_deterministic(self) -> None:
        forward = generate_candidate_pairs(self.rows, config=DEFAULT_CONFIG)
        reversed_rows = list(reversed(self.rows))
        reverse = generate_candidate_pairs(reversed_rows, config=DEFAULT_CONFIG)

        self.assertEqual(forward["pairs"], reverse["pairs"])
        self.assertEqual(forward["pair_sources"], reverse["pair_sources"])
        self.assertEqual(forward["parameters"], reverse["parameters"])
        for left, right in forward["pairs"]:
            self.assertLess(left, right)

    def test_candidate_output_survives_seeded_input_permutation(self) -> None:
        shuffled = list(self.rows)
        random.Random(99173).shuffle(shuffled)
        baseline = generate_candidate_pairs(self.rows, config=DEFAULT_CONFIG)
        permuted = generate_candidate_pairs(shuffled, config=DEFAULT_CONFIG)
        self.assertEqual(baseline["pairs"], permuted["pairs"])
        self.assertEqual(baseline["pair_sources"], permuted["pair_sources"])

    def test_exact_hash_candidates_do_not_depend_on_lsh(self) -> None:
        result = generate_candidate_pairs(self.rows, config=DEFAULT_CONFIG)
        sources = result["pair_sources"]
        pair = ("dup-000-exact", "dup-000-original")
        self.assertIn(pair, result["pairs"])
        self.assertIn("exact-hash", sources[pair])

    def test_exact_verification_precedes_component_truth(self) -> None:
        result = generate_candidate_pairs(self.rows, config=DEFAULT_CONFIG)
        components, verified_pairs = verified_duplicate_components(
            self.rows,
            result["pairs"],
            threshold=DEFAULT_CONFIG.threshold,
        )
        by_id = {row["record_id"]: row for row in self.rows}
        for left, right in verified_pairs:
            self.assertGreaterEqual(
                token_jaccard(by_id[left]["text"], by_id[right]["text"]),
                DEFAULT_CONFIG.threshold,
            )
        self.assertEqual(components, near_duplicate_components(self.rows))

    def test_tier_c_contract_matches_all_pairs_oracle(self) -> None:
        result = evaluate_candidate_contract(self.rows, config=DEFAULT_CONFIG)
        self.assertEqual(result["status"], "TESTED")
        self.assertTrue(result["component_equality"])
        self.assertEqual(result["qualifying_pair_recall"], 1.0)
        self.assertLess(result["candidate_pair_count"], result["all_pair_count"])
        self.assertEqual(result["input_permutation_equal"], True)
        self.assertEqual(result["parameters"]["scheme"], "affine32")
        self.assertEqual(result["parameters"]["threshold"], 0.80)
        self.assertEqual(result["parameters"]["seed"], 1729)
        self.assertEqual(result["parameters"]["num_perm"], 128)


if __name__ == "__main__":
    unittest.main()
