"""The real pinned SDK validates these fixtures; no toy schema or skip path."""
from copy import deepcopy
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import unittest

import starintel_canonical as sdk

from fixture_data import CALIBRATION, CART, RECEIVERS, REGISTRY, frame
from lab import analyze_frames, fit

FIXTURES = Path(__file__).parent / "fixtures"


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON member: {key!r}")
        result[key] = value
    return result


def document(name):
    text = (FIXTURES / name).read_text(encoding="utf-8")
    # Admission guard only. The SDK owns the schema and exact JSON semantics.
    json.loads(text, object_pairs_hook=unique_object, parse_int=str, parse_float=str)
    return sdk.Document.from_json(text)


class CanonicalFixtureTests(unittest.TestCase):
    def test_all_fixtures_validate_roundtrip_and_close_references(self):
        self.assertEqual(sdk.SPEC_VERSION, "0.10.1")
        self.assertEqual(version("jsonschema"), "4.26.0")
        self.assertIn("date-time", sdk.FORMAT_CHECKER.checkers)
        documents = [document(path.name) for path in sorted(FIXTURES.glob("*.json"))]
        self.assertEqual(len(documents), 6)
        for value in documents:
            with self.subTest(id=value.to_dict()["id"]):
                self.assertEqual(sdk.Document.from_json(value.to_json()).to_dict(), value.to_dict())
        by_id = {value.to_dict()["id"]: value.to_dict() for value in documents}
        observation = by_id["observation:owned-lab-west-100"]
        self.assertEqual(by_id[observation["observerId"]]["dtype"], "asset")
        self.assertEqual(by_id[observation["subjectId"]]["dtype"], "asset")
        self.assertNotEqual(observation["observerId"], observation["subjectId"])
        analysis = by_id["analysis:owned-lab-single-receiver"]
        self.assertTrue(all(identifier in by_id for identifier in analysis["inputIds"]))
        location = by_id["location:owned-lab-schema-only"]
        geometry = by_id[location["geometry"]["id"]]
        self.assertEqual(location["geometry"]["schema"], "org.starintel/core@1/geo-point")
        self.assertEqual(geometry["geometryType"], "point")

    def test_strict_schema_rejects_bad_fields_coordinates_dates_and_refs(self):
        changes = [
            ("observation.json", "schema_version", "0.10.1"),
            ("observation.json", "observedAt", -1),
            ("observation.json", "payloadObservedAt", "not-a-date"),
            ("observation.json", "receiverXMetres", 0),
            ("point-schema-only.json", "latitude", "91"),
            ("point-schema-only.json", "longitude", 0.0),
            ("location-schema-only.json", "geometry", {"id": "geo-point:owned-lab-schema-only"}),
        ]
        for name, key, bad_value in changes:
            with self.subTest(name=name, key=key):
                value = deepcopy(document(name).to_dict())
                value[key] = bad_value
                with self.assertRaises(sdk.ValidationError):
                    sdk.validate_document(value)
        with self.assertRaises(ValueError):
            json.loads('{"id":"one","id":"two"}', object_pairs_hook=unique_object)
        with self.assertRaises(sdk.ValidationError):
            sdk.validate_document(frame(100))  # course DTO is not canonical

    def test_canonical_example_matches_single_receiver_lab_inputs_and_policy(self):
        observation = document("observation.json").to_dict()
        analysis = document("analysis.json").to_dict()
        batch = analyze_frames([frame(100, [("r-west", -41)])], REGISTRY, RECEIVERS, fit(CALIBRATION))
        row = batch["observations"][0]
        result = next(r for r in batch["results"] if r["asset_id"] == CART)
        self.assertEqual(observation["rawValue"]["receiverSampleId"], row["sample_id"])
        self.assertEqual(observation["rawValue"]["receiverTimeS"], row["receiver_time_s"])
        self.assertEqual(observation["rawValue"]["radioAlias"], row["radio_alias"])
        self.assertEqual(observation["value"]["rssiDbm"], row["rssi_dbm"])
        epoch = observation["extensions"]["course"]["simulationEpochUnix"]
        self.assertEqual(observation["observedAt"], epoch + row["observed_s"])
        self.assertEqual(observation["collectedAt"], epoch + row["received_s"])
        iso_time = datetime.fromtimestamp(observation["observedAt"], timezone.utc).isoformat()
        self.assertEqual(observation["payloadObservedAt"], iso_time.replace("+00:00", "Z"))
        self.assertEqual(result["state"], analysis["extensions"]["course"]["expectedState"])
        self.assertEqual(result["zone"], analysis["extensions"]["course"]["expectedZone"])
        self.assertEqual(analysis["extensions"]["course"]["minimumDistinctReceivers"], 2)


if __name__ == "__main__":
    unittest.main()
