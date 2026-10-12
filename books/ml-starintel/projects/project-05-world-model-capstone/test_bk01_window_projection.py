"""BK10 focused cross-contract tests, synthetic BK01 upstream source pinned."""
import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import bk01_coverage_gate as gate
from bk01_window_projection import CONTRACT, TIME_AXIS, ProjectionError, evaluate_separate_predictors, project

sys.path.insert(0, str(Path(__file__).parent / "upstream"))
import world_models as native_bk01


class StrictBK10Double:
    """Contract-shaped test double: not the independent upstream capstone."""
    CONTRACT = "bk10.capstone.v0"

    @staticmethod
    def validate_observations(raw):
        assert set(raw) == {"version", "records"}
        assert raw["version"] == "bk10.observations.v0"
        assert len(raw["records"]) == 3
        assert [r["t"] for r in raw["records"]] == [0, 1, 2]
        assert all(set(r) == {"document_id", "t", "source", "kind", "count"} for r in raw["records"])
        return raw["records"]

    @staticmethod
    def encode_state(rows, *, observation_digest):
        return {"contract": "bk10.capstone.v0", "as_of": rows[-1]["t"],
                "observed_count": rows[-1]["count"],
                "delta": rows[-1]["count"] - rows[-2]["count"],
                "observation_digest": observation_digest}

    @staticmethod
    def candidate_futures(state):
        center = state["observed_count"] + state["delta"]
        return {"forecast_t": state["as_of"] + 1,
                "contract": "bk10.capstone.v0", "candidates": [
                    {"candidate_id": label, "count": max(0, center + shift), "weight_ppm": weight}
                    for label, shift, weight in (("down", -1, 250000),
                                                 ("center", 0, 500000),
                                                 ("up", 1, 250000))]}


class SourceWindowProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = gate.make_fixture(native_bk01)
        cls.projection = project(cls.env, native_bk01)

    def test_actual_native_source_verified(self):
        gate.verify_provider(native_bk01)

    def test_output_exact_version(self):
        self.assertEqual(self.projection["contract"], CONTRACT)
        self.assertEqual(self.projection["time_axis"], TIME_AXIS)

    def test_window_counts(self):
        self.assertEqual([r["count"] for r in self.projection["observations"]["records"]], [0, 2, 3])

    def test_ticks_are_ordinals_not_unix_seconds(self):
        self.assertEqual([r["t"] for r in self.projection["observations"]["records"]], [0, 1, 2])
        self.assertEqual([p["start_unix_seconds"] for p in self.projection["lineage"]],
                         [gate.START + 60 * i for i in range(3)])

    def test_empty_window_is_sealed_not_missing(self):
        self.assertTrue(self.projection["lineage"][0]["complete"])
        self.assertEqual(self.projection["lineage"][0]["source_ids"], [])

    def test_source_ids_are_accounted_for(self):
        for row, lineage in zip(self.projection["observations"]["records"],
                                self.projection["lineage"], strict=True):
            self.assertEqual(row["count"], len(lineage["source_ids"]))

    def test_digest_matches_observation_bytes(self):
        self.assertEqual(self.projection["observation_sha256"],
                         gate.json_sha256(self.projection["observations"]))

    def test_source_digest_preserved(self):
        self.assertEqual(self.projection["source_event_sha256"], self.env["events_sha256"])
        self.assertEqual(self.projection["source_inventory_sha256"], gate.RECEIPT_SHA256)

    def test_replay_deterministic(self):
        self.assertEqual(self.projection, project(copy.deepcopy(self.env), native_bk01))

    def test_self_rehashed_event_omission_rejected(self):
        with self.assertRaises(gate.CoverageError):
            project(gate.corrupt_self_consistently(self.env), native_bk01)

    def test_unsealed_window_rejected(self):
        bad = copy.deepcopy(self.env)
        bad["seals"][1]["complete"] = False
        with self.assertRaises(gate.CoverageError):
            project(bad, native_bk01)

    def test_gap_rejected(self):
        bad = copy.deepcopy(self.env)
        bad["seals"][2]["start"] += 60
        with self.assertRaises(gate.CoverageError):
            project(bad, native_bk01)

    def test_bool_timestamp_rejected(self):
        bad = copy.deepcopy(self.env)
        bad["events"][0]["observedAt"] = True
        bad["events_sha256"] = gate.json_sha256(bad["events"])
        with self.assertRaises(gate.CoverageError):
            project(bad, native_bk01)

    def test_provider_without_source_rejected(self):
        with self.assertRaises(gate.CoverageError):
            project(self.env, SimpleNamespace())

    def test_no_truth_or_lookahead_in_projected_dto(self):
        self.assertFalse(set(self.projection) & {"truth", "gold", "future_count"})
        self.assertTrue(all("future" not in k for r in self.projection["observations"]["records"] for k in r))

    def test_both_predictions_remain_separate(self):
        result = evaluate_separate_predictors(self.env, native_bk01, StrictBK10Double)
        self.assertTrue(result["targets_are_distinct"])
        self.assertFalse(result["truth_used"])
        self.assertEqual([v["count"] for v in result["bk10_untrained_count_scenarios"]["candidates"]], [3, 4, 5])
        self.assertEqual(result["bk01_fixed_filter_next_high"]["forecast_start_unix_seconds"], gate.START + 180)

    def test_rejects_missing_bk10_implementation(self):
        with self.assertRaises(ProjectionError):
            evaluate_separate_predictors(self.env, native_bk01, SimpleNamespace(CONTRACT="bk10.capstone.v0"))

    def test_rejects_wrong_bk10_contract(self):
        with self.assertRaises(ProjectionError):
            evaluate_separate_predictors(self.env, native_bk01, SimpleNamespace(CONTRACT="different"))

    def test_rejects_horizon_shift(self):
        class WrongHorizon(StrictBK10Double):
            @staticmethod
            def candidate_futures(state):
                return {"forecast_t": 99}
        with self.assertRaises(ProjectionError):
            evaluate_separate_predictors(self.env, native_bk01, WrongHorizon)

    def test_rejects_source_digest_loss(self):
        class WrongDigest(StrictBK10Double):
            @staticmethod
            def encode_state(rows, *, observation_digest):
                return {"as_of": rows[-1]["t"], "observation_digest": "0" * 64}
        with self.assertRaises(ProjectionError):
            evaluate_separate_predictors(self.env, native_bk01, WrongDigest)

    def test_rejects_row_replacement(self):
        class WrongRows(StrictBK10Double):
            @staticmethod
            def validate_observations(raw):
                rows = copy.deepcopy(raw["records"])
                rows[-1]["count"] = 0
                return rows
        with self.assertRaises(ProjectionError):
            evaluate_separate_predictors(self.env, native_bk01, WrongRows)

if __name__ == "__main__":
    unittest.main()
