"""BK10 issue #152: frozen-fixture unit tick regression, no live model."""

from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import unittest

from capstone import ContractError, candidate_futures, encode_state, read_manifest, run, validate_observations

ROOT = Path(__file__).resolve().parent
ORIGINAL = json.loads((ROOT / "fixtures/observations.json").read_text())

class BoundaryRegression(unittest.TestCase):
    def test_gap_immediately_before_forecast_rejected(self):
        records = deepcopy(ORIGINAL)
        records["records"][-1]["t"] = 3
        with self.assertRaisesRegex(ContractError, "contiguous"):
            validate_observations(records)

    def test_gap_interior_rejected(self):
        records = deepcopy(ORIGINAL)
        records["records"][1]["t"] = 2
        records["records"][2]["t"] = 3
        with self.assertRaisesRegex(ContractError, "contiguous"):
            validate_observations(records)

    def test_contiguous_nonzero_origin_preserved(self):
        records = deepcopy(ORIGINAL)
        for i, row in enumerate(records["records"]):
            row["t"] = 10 + i
        result = validate_observations(records)
        state = encode_state(result, observation_digest="0" * 64)
        self.assertEqual(candidate_futures(state)["forecast_t"], 13)
        self.assertEqual(state["delta"], 1)

    def test_disorder_and_duplicate_still_rejected(self):
        for value in (0, 1):
            bad = deepcopy(ORIGINAL)
            bad["records"][-1]["t"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ContractError, "strictly increasing"):
                validate_observations(bad)

    def test_direct_encoder_cannot_skip_timestep_gate(self):
        bad = deepcopy(ORIGINAL)
        bad["records"][-1]["t"] = 5
        with self.assertRaisesRegex(ContractError, "contiguous"):
            encode_state(bad["records"], observation_digest="a" * 64)

    def test_bool_time_still_rejected(self):
        bad = deepcopy(ORIGINAL)
        bad["records"][1]["t"] = True
        with self.assertRaisesRegex(ContractError, "integer"):
            validate_observations(bad)

    def test_no_untrusted_partial_window_becomes_zero(self):
        bad = deepcopy(ORIGINAL)
        bad["records"][-1]["t"] = 4
        with self.assertRaisesRegex(ContractError, "contiguous"):
            validate_observations(bad)

    def test_frozen_witness_output_unaffected(self):
        report = run(ROOT)
        self.assertEqual(report["state"]["as_of"], 2)
        self.assertEqual(report["state"]["observed_count"], 4)
        self.assertEqual([c["count"] for c in report["forecast"]["candidates"]], [4, 5, 6])
        self.assertEqual(report["metrics"]["absolute_error"], 1)
        self.assertEqual(report["tool_result"]["value"], "scheduled")

    def test_original_frozen_assets_verified(self):
        manifest = read_manifest(ROOT)
        for filename, expected in manifest["assets"].items():
            self.assertEqual(sha256((ROOT / "fixtures" / filename).read_bytes()).hexdigest(), expected)

    def test_extra_future_label_still_rejected(self):
        bad = deepcopy(ORIGINAL)
        bad["records"][-1]["future_count"] = 6
        with self.assertRaisesRegex(ContractError, "exactly"):
            validate_observations(bad)

if __name__ == "__main__":
    unittest.main()
