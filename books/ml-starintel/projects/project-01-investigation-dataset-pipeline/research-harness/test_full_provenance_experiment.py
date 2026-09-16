#!/usr/bin/env python3
"""Tests for full offline Project 1 GLEIF provenance Experiment D."""

from __future__ import annotations

import unittest

import run_full_provenance_experiment as subject


class FullProvenanceExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = subject.load_snapshot()

    def test_frozen_canonical_source_files_match_recorded_hashes(self) -> None:
        for name, metadata in self.snapshot["manifest"]["files"].items():
            self.assertEqual(
                subject.canonical_source_sha256(self.snapshot["records"][name]),
                metadata["canonical_json_sha256"],
                name,
            )

    def test_level1_snapshot_maps_three_resolved_canonical_orgs(self) -> None:
        documents = subject.map_orgs(self.snapshot)
        self.assertEqual(len(documents), 3)
        by_lei = {document["data"]["lei"]: document for document in documents}
        self.assertEqual(
            set(by_lei),
            {
                "6354009BJOFO62XYIX17",
                "635400Z5LRZZSML7CV16",
                "635400VZ8GQJUZ3L3H12",
            },
        )
        for document in documents:
            self.assertEqual(document["schema_version"], "0.9.0")
            self.assertEqual(document["version"], 1)
            self.assertEqual(document["dtype"], "org")
            self.assertEqual(document["data"]["external_ids"][0]["scheme"], "LEI")

    def test_relationships_are_entity_closed_and_preserve_primary_predicates(self) -> None:
        orgs = subject.map_orgs(self.snapshot)
        relations = subject.map_relationships(self.snapshot, orgs)
        self.assertEqual(len(relations), 2)
        self.assertEqual(
            {document["data"]["predicate"] for document in relations},
            {"IS_FEEDER_TO", "IS_FUND-MANAGED_BY"},
        )
        for document in relations:
            data = document["data"]
            self.assertFalse(data["subject"]["unresolved"])
            self.assertFalse(data["object"]["unresolved"])
            self.assertTrue(data["active"])
            self.assertEqual(data["predicate"], data["relation_type"])
            self.assertEqual(
                data["qualifiers"]["gleif"]["registration"]["corroborationLevel"],
                "FULLY_CORROBORATED",
            )

    def test_source_provenance_retains_url_retrieval_raw_and_canonical_hashes(self) -> None:
        documents = subject.map_orgs(self.snapshot)
        source = documents[0]["sources"][0]
        self.assertTrue(source["url"].startswith("https://api.gleif.org/api/v1/"))
        self.assertTrue(source["retrieved_at"].startswith("2026-08-17T18:"))
        self.assertEqual(source["hash_algorithm"], "sha256")
        self.assertEqual(len(source["content_hash"]), 64)
        self.assertEqual(len(source["metadata"]["raw_response_sha256"]), 64)
        self.assertEqual(source["metadata"]["source_kind"], "canonical-json-snapshot")

    def test_experiment_scope_is_full_d_not_sample_shape(self) -> None:
        result = subject.run_experiment(validate=False)
        self.assertEqual(result["experiment"], "D")
        self.assertEqual(result["claim_scope"], "TIER_B_FACTUAL_AS_OF_PROVENANCE_ROUNDTRIP")
        self.assertEqual(result["document_count"], 5)
        self.assertTrue(result["checks"]["entity_closed"])
        self.assertTrue(result["checks"]["all_source_hashes_reconstructable"])
        self.assertTrue(result["checks"]["json_roundtrip_preserves_documents"])


if __name__ == "__main__":
    unittest.main()
