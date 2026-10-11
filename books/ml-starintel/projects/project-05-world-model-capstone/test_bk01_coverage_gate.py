"""BK10-only tests: pure frozen-inventory checks plus optional native BK01."""
from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

import bk01_coverage_gate as g


def native_provider():
    target = os.getenv("BK10_BK01_PROVIDER_PATH")
    if not target:
        fallback = Path(__file__).resolve().parents[2] / "code/world-models-01/world_models.py"
        if fallback.is_file():
            target = str(fallback)
    if not target:
        return None
    spec = importlib.util.spec_from_file_location("bk01_native_pinned", target)
    if spec is None or spec.loader is None:
        raise RuntimeError("BK01 provider module is not loadable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


class FrozenCoverageContract(unittest.TestCase):
    def setUp(self):
        self.raw = g.frozen_fixture()

    def rejects(self, value):
        with self.assertRaises(g.CoverageError):
            g.validate_envelope(value)

    def test_frozen_source_and_receipt(self):
        events, seals = g.validate_envelope(self.raw)
        self.assertEqual([len(s["source_ids"]) for s in seals], [0, 2, 3])
        self.assertEqual(len(events), 5)
        self.assertEqual(g.json_sha256(g._inventory(events)), g.RECEIPT_SHA256)

    def test_event_order_is_not_provenance(self):
        raw = copy.deepcopy(self.raw)
        raw["events"].reverse()
        raw["events_sha256"] = g.json_sha256(raw["events"])
        self.assertEqual(g.validate_envelope(raw)[0], raw["events"])

    def test_missing_event_even_if_caller_rewrites_every_mutable_receipt(self):
        self.rejects(g.corrupt_self_consistently(self.raw))

    def test_delete_event_without_digest_update(self):
        raw = copy.deepcopy(self.raw)
        raw["events"].pop()
        self.rejects(raw)

    def test_rename_event_and_reseal(self):
        raw = copy.deepcopy(self.raw)
        raw["events"][0]["id"] = "synthetic:event:replacement"
        raw["events_sha256"] = g.json_sha256(raw["events"])
        raw["seals"][1]["source_ids"] = sorted([raw["events"][0]["id"], raw["events"][1]["id"]])
        self.rejects(raw)

    def test_shift_timestamp_into_other_window(self):
        raw = copy.deepcopy(self.raw)
        raw["events"][0]["observedAt"] += 60
        raw["events_sha256"] = g.json_sha256(raw["events"])
        self.rejects(raw)

    def test_duplicate_event_identity(self):
        raw = copy.deepcopy(self.raw)
        raw["events"][0]["id"] = raw["events"][1]["id"]
        raw["events_sha256"] = g.json_sha256(raw["events"])
        self.rejects(raw)

    def test_unknown_event_field(self):
        raw = copy.deepcopy(self.raw)
        raw["events"][0]["future_truth"] = 7
        raw["events_sha256"] = g.json_sha256(raw["events"])
        self.rejects(raw)

    def test_unknown_envelope_field_truth_leakage(self):
        raw = copy.deepcopy(self.raw)
        raw["heldout"] = {"count": 1}
        self.rejects(raw)

    def test_bad_event_dtype(self):
        raw = copy.deepcopy(self.raw)
        raw["events"][0]["dtype"] = "person"
        raw["events_sha256"] = g.json_sha256(raw["events"])
        self.rejects(raw)

    def test_bad_version(self):
        raw = copy.deepcopy(self.raw)
        raw["events"][0]["schemaVersion"] = "0.9.0"
        raw["events_sha256"] = g.json_sha256(raw["events"])
        self.rejects(raw)

    def test_non_integer_observed_at(self):
        raw = copy.deepcopy(self.raw)
        raw["events"][0]["observedAt"] = True
        raw["events_sha256"] = g.json_sha256(raw["events"])
        self.rejects(raw)

    def test_timestamp_outside_window(self):
        raw = copy.deepcopy(self.raw)
        raw["events"][0]["observedAt"] = g.START + 180
        raw["events_sha256"] = g.json_sha256(raw["events"])
        self.rejects(raw)

    def test_negative_timestamp(self):
        raw = copy.deepcopy(self.raw)
        raw["start"] = -1
        self.rejects(raw)

    def test_boolean_window_length(self):
        raw = copy.deepcopy(self.raw)
        raw["window_seconds"] = True
        self.rejects(raw)

    def test_wrong_window_length(self):
        raw = copy.deepcopy(self.raw)
        raw["window_seconds"] = 1
        self.rejects(raw)

    def test_seal_missing_window(self):
        raw = copy.deepcopy(self.raw)
        raw["seals"].pop()
        self.rejects(raw)

    def test_seal_unconfirmed_window(self):
        raw = copy.deepcopy(self.raw)
        raw["seals"][0]["complete"] = False
        self.rejects(raw)

    def test_seal_time_gap(self):
        raw = copy.deepcopy(self.raw)
        raw["seals"][1]["start"] += 60
        self.rejects(raw)

    def test_seal_source_mismatch(self):
        raw = copy.deepcopy(self.raw)
        raw["seals"][1]["source_ids"].pop()
        self.rejects(raw)

    def test_noncanonical_seal_ids(self):
        raw = copy.deepcopy(self.raw)
        raw["seals"][2]["source_ids"].reverse()
        self.rejects(raw)

    def test_forged_receipt_digest(self):
        raw = copy.deepcopy(self.raw)
        raw["inventory_receipt_sha256"] = "0" * 64
        self.rejects(raw)

    def test_empty_event_inventory(self):
        raw = copy.deepcopy(self.raw)
        raw["events"] = []
        raw["events_sha256"] = g.json_sha256(raw["events"])
        self.rejects(raw)

    def test_wrong_contract(self):
        raw = copy.deepcopy(self.raw)
        raw["contract"] = "bk10.other.v0"
        self.rejects(raw)

    def test_receipt_order_changed(self):
        raw = copy.deepcopy(self.raw)
        raw["inventory_receipt"].reverse()
        self.rejects(raw)


class NativeBK01Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider = native_provider()
        if cls.provider is None:
            raise unittest.SkipTest("BK01 candidate source unavailable; set BK10_BK01_PROVIDER_PATH")

    def test_exact_provider_blob(self):
        g.verify_provider(self.provider)
        self.assertEqual(g.git_blob_sha(Path(self.provider.__file__).read_bytes()),g.PROVIDER_BLOB)

    def test_generated_fixture_matches_frozen_snapshot(self):
        self.assertEqual(g.make_fixture(self.provider),g.frozen_fixture())

    def test_native_forecast_before_truth(self):
        result = g.forecast(g.frozen_fixture(),self.provider)
        self.assertEqual(result["observations"],[0,2,3])
        self.assertFalse(result["truth_used"])
        self.assertAlmostEqual(result["p_high_uncalibrated"],0.5059188644380984,places=14)

    def test_purported_zero_from_capture_loss_changes_native_forecast(self):
        bad = g.corrupt_self_consistently(g.frozen_fixture())
        with self.assertRaises(g.CoverageError):
            g.forecast(bad,self.provider)
        windows = self.provider.aggregate_synthetic_events(bad["events"],start=g.START,windows=g.WINDOWS)
        self.assertEqual([w.count for w in windows],[0,2,0])
        naive = self.provider.BinaryWorldModel().filter(windows)[-1].next_high_probability
        self.assertAlmostEqual(naive,0.3541110514301061,places=14)

    def test_provider_source_tamper_rejected(self):
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".py") as f:
            f.write(Path(self.provider.__file__).read_bytes() + b"\n# tampered\n")
            f.flush()
            impostor = SimpleNamespace(
                VERSION="0.10.1", DATASET="world-model-synthetic",
                WINDOW_SECONDS=60, BUCKETS=("low", "high"), __file__=f.name,
                aggregate_synthetic_events=self.provider.aggregate_synthetic_events,
                BinaryWorldModel=self.provider.BinaryWorldModel,
            )
            with self.assertRaisesRegex(g.CoverageError, "Git blob mismatch"):
                g.verify_provider(impostor)


if __name__ == "__main__":
    unittest.main()
