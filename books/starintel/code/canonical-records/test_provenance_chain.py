"""Generated StarIntel 0.10.1 provenance boundary, using only fictional data.

These assertions exercise the pinned SDK; they do not emulate StarIntel
authorization, storage, RabbitMQ, an actor, or provenance truth.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest

import starintel_canonical as sdk
from admission import read_document

ROOT = Path(__file__).parent / "fixtures"
NAMES = ("provenance-source", "provenance-observation", "provenance-relation")


def load(name):
    text = (ROOT / (name + ".json")).read_text(encoding="utf-8")
    return read_document(text).to_dict()


class ProvenanceChainTests(unittest.TestCase):
    def test_all_three_concrete_document_schemas_and_roundtrips(self):
        self.assertEqual(sdk.SPEC_VERSION, "0.10.1")
        for name in NAMES:
            with self.subTest(name=name):
                text = (ROOT / (name + ".json")).read_text(encoding="utf-8")
                expected = json.loads(text)
                canonical = read_document(text).to_dict()
                self.assertEqual(canonical, expected)
                self.assertEqual(sdk.Document.from_dict(canonical).to_dict(), expected)

    def test_local_evidence_chain_resolves_by_typed_identity(self):
        source = load("provenance-source")
        observation = load("provenance-observation")
        relation = load("provenance-relation")
        self.assertEqual(observation["sources"], [{
            "schema": "org.starintel/core@1/source", "id": source["id"]}])
        self.assertEqual(relation["sources"], observation["sources"])
        self.assertEqual(relation["evidence"], [{
            "schema": "org.starintel/core@1/observation",
            "id": observation["id"]}])
        self.assertEqual(relation["source"], {
            "schema": "org.starintel/core@1/person", "id": "person:book-alex"})
        self.assertEqual(relation["destination"], {
            "schema": "org.starintel/core@1/org", "id": "org:book-example"})
        self.assertEqual(relation["predicate"], "member-of")

    def test_unix_epoch_zero_allowed_but_invalid_times_rejected(self):
        value = load("provenance-observation")
        self.assertEqual(value["observedAt"], 0)
        for bad in (-1, 0.5, "0", False):
            with self.subTest(bad=bad):
                changed = deepcopy(value)
                changed["observedAt"] = bad
                with self.assertRaises(sdk.ValidationError):
                    sdk.validate_document(changed)

    def test_missing_reference_component_rejected(self):
        value = load("provenance-observation")
        del value["sources"][0]["schema"]
        with self.assertRaises(sdk.ValidationError):
            sdk.validate_document(value)

    def test_missing_relation_predicate_rejected(self):
        value = load("provenance-relation")
        del value["predicate"]
        with self.assertRaises(sdk.ValidationError):
            sdk.validate_document(value)

    def test_well_shaped_dangling_evidence_is_not_checked_for_existence(self):
        value = load("provenance-relation")
        value["evidence"][0]["id"] = "observation:does-not-exist"
        sdk.validate_document(value)
        self.assertNotEqual(value["evidence"][0]["id"],
                            load("provenance-observation")["id"])

    def test_schema_does_not_enforce_cross_dataset_authorization(self):
        observation = load("provenance-observation")
        relation = load("provenance-relation")
        observation["dataset"] = "another-synthetic-dataset"
        sdk.validate_document(observation)
        sdk.validate_document(relation)
        self.assertNotEqual(observation["dataset"], relation["dataset"])

    def test_invalid_collection_status_rejected(self):
        value = load("provenance-source")
        value["collectionStatus"] = "made-up-verified"
        with self.assertRaises(sdk.ValidationError):
            sdk.validate_document(value)

    def test_invalid_source_iso_datetime_rejected(self):
        self.assertIn("date-time", sdk.FORMAT_CHECKER.checkers)
        value = load("provenance-source")
        value["retrievedAt"] = "not-a-datetime"
        with self.assertRaises(sdk.ValidationError):
            sdk.validate_document(value)

    def test_invalid_confidence_rejected(self):
        value = load("provenance-observation")
        self.assertEqual(value["confidence"], "0.7500")
        for bad in (1.01, "1.0001", "not-a-decimal"):
            with self.subTest(bad=bad):
                changed = deepcopy(value)
                changed["confidence"] = bad
                with self.assertRaises(sdk.ValidationError):
                    sdk.validate_document(changed)

    def test_required_canonical_envelope_rejected_when_missing(self):
        for field in ("id", "dataset"):
            with self.subTest(field=field):
                value = load("provenance-source")
                del value[field]
                with self.assertRaises(sdk.ValidationError):
                    sdk.validate_document(value)

    def test_no_observed_storage_revision_or_actor_receipt(self):
        for name in NAMES:
            value = load(name)
            for key in ("rev", "_rev", "_id", "eventReceipt", "actorReceipt"):
                self.assertNotIn(key, value)
        relation = load("provenance-relation")
        self.assertEqual(relation["causationId"], "book-action-001")
        self.assertEqual(relation["collectionStatus"], "raw")


if __name__ == "__main__":
    unittest.main()
