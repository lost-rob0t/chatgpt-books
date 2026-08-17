#!/usr/bin/env python3
"""Tests for the narrow GLEIF sample -> StarIntel 0.9 adapter experiment."""

from __future__ import annotations

import unittest

import run_gleif_relation_experiment as subject


class GleifRelationAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = subject.load_fixture()

    def test_level1_record_maps_to_canonical_org_without_changing_spec_version(self) -> None:
        document = subject.map_level1_org(self.fixture)
        self.assertEqual(document["schema_version"], "0.9.0")
        self.assertEqual(document["version"], 1)
        self.assertEqual(document["dtype"], "org")
        self.assertEqual(document["data"]["lei"], "6354009BJOFO62XYIX17")
        self.assertEqual(document["data"]["legal_name"], "AlbaCore Partners I Feeder ICAV")
        self.assertEqual(document["data"]["org_type"], "FUND")

    def test_relationship_mapping_preserves_gleif_type_and_unresolved_endpoints(self) -> None:
        documents = subject.map_relationships(self.fixture)
        self.assertEqual(len(documents), 2)
        predicates = {document["data"]["predicate"] for document in documents}
        self.assertEqual(predicates, {"IS_FEEDER_TO", "IS_FUND-MANAGED_BY"})
        for document in documents:
            data = document["data"]
            self.assertEqual(data["subject"]["external_id"], "6354009BJOFO62XYIX17")
            self.assertFalse(data["subject"]["unresolved"])
            self.assertTrue(data["object"]["unresolved"])
            self.assertEqual(data["predicate"], data["relation_type"])
            self.assertEqual(data["start_at"], "2016-10-28T01:00:00+01:00")
            self.assertTrue(data["active"])
            self.assertEqual(data["qualifiers"]["gleif"]["registration_status"], "PUBLISHED")
            self.assertEqual(data["qualifiers"]["gleif"]["validation_sources"], "FULLY_CORROBORATED")
            self.assertEqual(data["qualifiers"]["gleif"]["validation_documents"], "REGULATORY_FILING")

    def test_fixture_explicitly_records_missing_level1_endpoint_closure(self) -> None:
        observed = set(subject.relationship_end_leis(self.fixture))
        declared_missing = set(self.fixture["known_absent_level1_endpoint_leis"])
        self.assertEqual(observed, declared_missing)
        self.assertNotIn("6354009BJOFO62XYIX17", declared_missing)

    def test_mapping_preserves_member_and_archive_hash_lineage(self) -> None:
        document = subject.map_relationships(self.fixture)[0]
        source = document["sources"][0]
        provenance = document["provenance"]
        self.assertEqual(
            source["content_hash"],
            "978e3181c04fecd628654b7ae0e9d9c0cb07450de14480dd6587b4e455aa7882",
        )
        self.assertEqual(
            source["metadata"]["archive_sha256"],
            "7b49ee2c8fbe8e2a10f60165dd12ab3bf212eb95418c229218ea24d425b15237",
        )
        self.assertEqual(provenance["original_schema_version"], "RR-CDF-2.1")
        self.assertEqual(provenance["original_path"], "JSON/GoldenCopy_rr.json")

    def test_illustrative_fixture_is_not_promoted_to_full_public_observation(self) -> None:
        self.assertEqual(self.fixture["fixture_tier"], "A-illustrative-format")
        result = subject.run_experiment(validate=False)
        self.assertEqual(result["claim_scope"], "TIER_A_ADAPTER_SHAPE")
        self.assertEqual(result["full_experiment_d"], "UNTESTED")


if __name__ == "__main__":
    unittest.main()
