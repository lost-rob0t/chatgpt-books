"""Small educational fixtures against the real canonical SDK, not a toy schema."""
from collections import Counter
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import unittest

import starintel_canonical as sdk
from starintel_canonical.migration import canonicalize_document
from admission import read_document

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name):
    return read_document((FIXTURES / f"{name}.json").read_text()).to_dict()


class CanonicalRecordsTests(unittest.TestCase):
    def test_manifest_inventory_is_persistent_only(self):
        self.assertEqual(sdk.SPEC_VERSION, "0.10.1")
        counts = Counter(t["persistence"] for t in sdk.MANIFEST["types"]
                         if t["kind"] == "document")
        self.assertEqual(counts, {"persistent": 90, "transient": 33})
        self.assertEqual(len(sdk.schema_inventory()), 90)
        self.assertIn("org", sdk.DOCUMENT_TYPES)
        self.assertNotIn("organization", sdk.DOCUMENT_TYPES)

    def test_three_fixtures_roundtrip_without_mutation(self):
        for name in ("person", "org", "relation"):
            with self.subTest(name=name):
                value = fixture(name)
                before = deepcopy(value)
                self.assertEqual(sdk.Document.from_dict(value).to_dict(), before)
                self.assertEqual(value, before)

    def test_optional_revision_stays_absent(self):
        self.assertNotIn("rev", fixture("person"))

    def test_relation_refers_to_typed_endpoints(self):
        edge = fixture("relation")
        for field, name in (("source", "person"), ("destination", "org")):
            value = fixture(name)
            self.assertEqual(edge[field], {
                "schema": f"org.starintel/core@1/{value['dtype']}",
                "id": value["id"],
            })

    def test_missing_relation_predicate_rejected(self):
        edge = fixture("relation")
        del edge["predicate"]
        with self.assertRaises(sdk.ValidationError):
            sdk.validate_document(edge)

    def test_reference_requires_both_fields(self):
        edge = fixture("relation")
        del edge["source"]["schema"]
        with self.assertRaises(sdk.ValidationError):
            sdk.validate_document(edge)

    def test_invalid_identity_rejected(self):
        value = fixture("person")
        value["id"] = "spaces are not valid here"
        with self.assertRaises(sdk.ValidationError):
            sdk.validate_document(value)

    def test_historical_aliases_and_unknown_dtype_rejected(self):
        for field, replacement in (("_id", "person:old"),
                                    ("schema_version", "0.10.1"),
                                    ("data", {}),
                                    ("dtype", "organization")):
            with self.subTest(field=field):
                value = fixture("person")
                value[field] = replacement
                with self.assertRaises(sdk.ValidationError):
                    sdk.validate_document(value)

    def test_current_version_is_explicit(self):
        value = fixture("person")
        value["schemaVersion"] = "0.9.0"
        with self.assertRaises(sdk.UnsupportedVersion):
            sdk.validate_document(value)

    def test_datetime_format_checker_is_available_and_enforced(self):
        self.assertIn("date-time", sdk.FORMAT_CHECKER.checkers,
                      "Install jsonschema[format]; format checks must not silently disappear")
        value = {"id": "source:book-format", "dataset": "book-synthetic",
                 "dtype": "source", "schemaVersion": "0.10.1",
                 "retrievedAt": "2026-10-07T12:00:00Z"}
        sdk.validate_document(value)
        value["retrievedAt"] = "not-a-datetime"
        with self.assertRaises(sdk.ValidationError):
            sdk.validate_document(value)

    def test_confidence_is_bounded_decimal_string(self):
        value = fixture("person")
        value["confidence"] = "0.75"
        sdk.validate_document(value)
        for bad in (0.75, "1.1", "0.12345"):
            with self.subTest(bad=bad):
                value["confidence"] = bad
                with self.assertRaises(sdk.ValidationError):
                    sdk.validate_document(value)

    def test_opaque_values_and_exact_numbers_survive(self):
        text = (FIXTURES / "person.json").read_text().rstrip()
        text = text[:-1] + ', "extensions": {"book": {"n": '
        text += '0.12345678901234567890123456789, "flag": false, "missing": null}}}'
        document = read_document(text)
        opaque = document.to_dict()["extensions"]["book"]
        self.assertEqual(opaque["n"], Decimal("0.12345678901234567890123456789"))
        self.assertIs(opaque["flag"], False)
        self.assertIsNone(opaque["missing"])
        self.assertEqual(read_document(document.to_json()).to_dict(), document.to_dict())

    def test_duplicate_members_rejected_before_sdk(self):
        for text in ('{"id":"first","id":"second"}',
                     '{"extensions":{"x":{"name":1,"name":2}}}',
                     '{"id":"first","\\u0069d":"second"}'):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "duplicate"):
                read_document(text)

    def test_pinned_sdk_parser_alone_has_duplicate_member_gap(self):
        # A deliberately recorded limitation, not a successful conformance claim.
        self.assertEqual(sdk.parse_json('{"id":"first","id":"second"}'),
                         {"id": "second"})

    def test_current_input_is_identity_migration(self):
        value = fixture("person")
        before = deepcopy(value)
        self.assertEqual(canonicalize_document(value), before)
        self.assertEqual(value, before)

    def test_explicit_legacy_migration_preserves_original(self):
        old = json.loads((FIXTURES / "legacy-person.json").read_text())
        before = deepcopy(old)
        new = canonicalize_document(old)
        sdk.validate_document(new)
        self.assertEqual(new["id"], old["_id"])
        self.assertEqual(new["schemaVersion"], "0.10.1")
        self.assertEqual(new["fname"], "Alex")
        self.assertEqual(new["extensions"]["legacy"]["original"]["data"], old["data"])
        self.assertNotIn("private_note", new)
        self.assertEqual(old, before)

    def test_dangling_reference_is_not_a_schema_error(self):
        edge = fixture("relation")
        edge["destination"]["id"] = "org:not-in-this-fixture"
        sdk.validate_document(edge)
        # This success establishes that shape validation does not query storage.
        self.assertNotEqual(edge["destination"]["id"], fixture("org")["id"])


if __name__ == "__main__":
    unittest.main()
