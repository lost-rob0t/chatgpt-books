from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from starintel_doc.v090 import (
    SPEC_VERSION,
    UnsupportedVersion,
    ValidationError,
    roundtrip_document,
    validate_document,
)

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class StarIntelRecordTests(unittest.TestCase):
    def test_person_fixture_validates(self) -> None:
        document = load_fixture("person.json")
        self.assertEqual("0.9.0", SPEC_VERSION)
        self.assertIs(document, validate_document(document))

    def test_roundtrip_preserves_extension_payload(self) -> None:
        document = load_fixture("person.json")
        result = roundtrip_document(document)
        self.assertEqual(document, result)
        self.assertEqual(
            {"exercise": "project-1-a", "synthetic": True},
            result["extensions"]["book.example"],
        )

    def test_operation_is_valid_under_v090_wire_contract(self) -> None:
        document = load_fixture("operation.json")
        self.assertEqual("operation", document["dtype"])
        self.assertEqual(SPEC_VERSION, document["schema_version"])
        self.assertEqual(document, roundtrip_document(document))

    def test_missing_required_id_is_typed_failure(self) -> None:
        document = load_fixture("person.json")
        del document["_id"]
        with self.assertRaises(ValidationError) as context:
            validate_document(document)
        self.assertEqual("missing_required_field", context.exception.category)

    def test_rejected_dtype_alias_is_not_silently_normalized(self) -> None:
        document = load_fixture("person.json")
        document["dtype"] = "organization"
        with self.assertRaises(ValidationError) as context:
            validate_document(document)
        self.assertEqual("invalid_enum", context.exception.category)

    def test_datetime_without_zone_is_rejected(self) -> None:
        document = load_fixture("person.json")
        document["date_added"] = "2026-09-16T12:00:00"
        with self.assertRaises(ValidationError) as context:
            validate_document(document)
        self.assertEqual("invalid_datetime", context.exception.category)

    def test_unsupported_wire_version_is_distinct(self) -> None:
        document = deepcopy(load_fixture("person.json"))
        document["schema_version"] = "0.8.0"
        with self.assertRaises(UnsupportedVersion) as context:
            validate_document(document)
        self.assertEqual("unsupported_spec_version", context.exception.category)


if __name__ == "__main__":
    unittest.main(verbosity=2)
