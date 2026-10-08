"""Synthetic method tests; no web access or location collection."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

import starintel_canonical as sdk
from freshness import classify

ROOT = Path(__file__).parent
GRANT = {"active": True, "audience": "demo-coordinator", "startsAtS": 900,
         "expiresAtS": 1800, "maxAgeS": 60, "maxAccuracyM": 30}
SAMPLE = {"observedAtS": 1000, "receivedAtS": 1005, "accuracyM": 12,
          "gridEastM": 240, "gridNorthM": 100}


class EvidenceTests(unittest.TestCase):
    def state(self, sample=None, grant=None, now=1020, audience="demo-coordinator"):
        return classify(SAMPLE if sample is None else sample,
                        GRANT if grant is None else grant,
                        now_s=now, audience=audience)

    def test_fresh_and_age_boundary(self):
        self.assertEqual(self.state(), "fresh")
        self.assertEqual(self.state(now=1060), "fresh")
        self.assertEqual(self.state(now=1061), "stale")

    def test_new_receipt_does_not_refresh_old_fix(self):
        replay = {**SAMPLE, "receivedAtS": 1120}
        self.assertEqual(self.state(replay, now=1120), "stale")

    def test_revocation_and_audience_gate(self):
        self.assertEqual(self.state(grant={**GRANT, "active": False}), "blocked")
        self.assertEqual(self.state(audience="unrelated-reader"), "blocked")
        for value in (None, "", " ", 17):
            with self.subTest(audience=value):
                self.assertEqual(self.state(grant={**GRANT, "audience": value},
                                            audience=value), "blocked")

    def test_expiry_and_future_grant(self):
        self.assertEqual(self.state(now=1800), "blocked")
        self.assertEqual(self.state(now=800), "blocked")

    def test_preconsent_future_and_reversed_clocks(self):
        for sample in ({**SAMPLE, "observedAtS": 899},
                       {**SAMPLE, "observedAtS": 1021},
                       {**SAMPLE, "receivedAtS": 999}):
            with self.subTest(sample=sample):
                self.assertEqual(self.state(sample), "unknown")

    def test_coarse_uncertainty_does_not_become_precise(self):
        self.assertEqual(self.state({**SAMPLE, "accuracyM": 80}), "coarse")

    def test_invalid_values_fail_closed(self):
        for value in (None, -1, True, float("nan"), float("inf"), "12", 10**400):
            with self.subTest(value=value):
                self.assertEqual(self.state({**SAMPLE, "accuracyM": value}), "unknown")
        self.assertEqual(self.state({**SAMPLE, "observedAtS": True}), "unknown")
        self.assertEqual(self.state(now=-1), "unknown")

    def test_grant_limits_are_validated(self):
        for changed in ({"expiresAtS": 900}, {"maxAgeS": -1},
                        {"maxAccuracyM": float("nan")}, {"maxAccuracyM": 10**400},
                        {"active": "yes"}):
            with self.subTest(changed=changed):
                self.assertEqual(self.state(grant={**GRANT, **changed}), "blocked")

    def test_input_is_not_mutated(self):
        sample, grant = deepcopy(SAMPLE), deepcopy(GRANT)
        self.state(sample, grant)
        self.assertEqual(sample, SAMPLE)
        self.assertEqual(grant, GRANT)

    def test_venue_asset_has_accessible_metadata(self):
        asset = ROOT.parents[1] / "assets/fictional-venue-comparison.svg"
        image = ET.parse(asset).getroot()
        ns = {"svg": "http://www.w3.org/2000/svg"}
        self.assertIsNotNone(image.find("svg:title", ns))
        self.assertIsNotNone(image.find("svg:desc", ns))

    def test_fictional_documents_validate(self):
        packet = json.loads((ROOT / "case.json").read_text())
        self.assertTrue(packet["fictional"])
        for value in packet["documents"]:
            with self.subTest(document=value["id"]):
                self.assertEqual(sdk.Document.from_dict(value).to_dict(), value)
        self.assertEqual(len({x["id"] for x in packet["documents"]}),
                         len(packet["documents"]))

    def test_case_relation_keeps_two_people_distinct(self):
        packet = json.loads((ROOT / "case.json").read_text())
        docs = {value["id"]: value for value in packet["documents"]}
        person_ids = {key for key, value in docs.items() if value["dtype"] == "person"}
        self.assertEqual(person_ids, {"person:fiction-rivera-science",
                                      "person:fiction-rivera-design"})
        edge = docs["relation:fiction-programme-affiliation"]
        self.assertEqual(edge["source"]["id"], "person:fiction-rivera-science")
        self.assertEqual(edge["destination"]["id"], "org:fiction-delta-lab")
        self.assertEqual(edge["predicate"], "listed-as-speaker-for")
        self.assertEqual(edge["verificationStatus"], "fictional teaching assertion")
        self.assertIn("source:fiction-programme",
                      {ref["id"] for ref in edge["evidence"]})


if __name__ == "__main__":
    unittest.main()
