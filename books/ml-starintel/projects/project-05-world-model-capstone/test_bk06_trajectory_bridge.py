"""BK10-only tests: fail-closed BK06 synthetic trajectory contract and native replay."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from bk06_trajectory_bridge import (
    BridgeError, HISTORY, HORIZON, MAX_SAMPLES, PROVIDER_BLOB, TIMEBASE,
    git_blob_sha, history_from_events, load_pinned_provider, native_witness,
    predict, score_after_forecast, validate_forecast, validate_history,
)

EPISODE = "synthetic-episode-0042"


def events(start=0, end=10):
    return [{"event_id": f"{EPISODE}-tick-{t:02d}", "episode_id": EPISODE,
             "time_index": t, "kind": "synthetic_numeric_observation",
             "measurement": -1.25 + 0.2 * t, "provenance_tier": "C-synthetic"}
            for t in range(start, end)]


class Array:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


class Provider:
    def forecast(self, history, samples, seed):
        assert len(history) == HISTORY
        return Array([[float(seed % 5 + n + t) for t in range(HORIZON)]
                      for n in range(samples)])


class BadProvider:
    def __init__(self, response):
        self.response = response

    def forecast(self, history, samples, seed):
        return self.response


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.history_events = events(0, HISTORY)
        self.history = history_from_events(EPISODE, self.history_events)

    def test_valid_exact_history(self):
        self.assertEqual(validate_history(self.history), tuple(x["measurement"] for x in self.history_events))
        self.assertEqual(self.history["as_of"], 3)
        self.assertEqual(self.history["timebase"], TIMEBASE)

    def test_history_count_and_source_not_implicitly_convertible(self):
        with self.assertRaises(BridgeError):
            history_from_events(EPISODE, self.history_events[:3])
        with self.assertRaises(BridgeError):
            history_from_events(EPISODE, [{"document_id": "synthetic:obs-01", "t": 0,
                                          "source": "synthetic-counter", "kind": "count", "count": 1}]*4)

    def test_no_future_event_inference_input(self):
        with self.assertRaises(BridgeError):
            history_from_events(EPISODE, events(0, 10))

    def test_timestamps_cannot_skip_reorder_bool_or_shift(self):
        for mutated in (0, 4, True, -1):
            with self.subTest(t=mutated):
                e = copy.deepcopy(self.history_events)
                e[1]["time_index"] = mutated
                with self.assertRaises(BridgeError):
                    history_from_events(EPISODE, e)

    def test_wrong_episode_or_event_identity(self):
        for key, value in (("episode_id", "synthetic-episode-0023"),
                           ("event_id", "synthetic-episode-0042-tick-42")):
            with self.subTest(field=key):
                e = copy.deepcopy(self.history_events)
                e[0][key] = value
                with self.assertRaises(BridgeError):
                    history_from_events(EPISODE, e)

    def test_provenance_kind_and_extra_fields_rejected(self):
        for key, value in (("kind", "count"), ("provenance_tier", "A-real"),
                           ("next_measurement", 3)):
            with self.subTest(field=key):
                e = copy.deepcopy(self.history_events)
                e[0][key] = value
                with self.assertRaises(BridgeError):
                    history_from_events(EPISODE, e)

    def test_bad_measurements_rejected(self):
        for bad in (True, "1", float("inf"), float("nan"), None):
            with self.subTest(value=str(bad)):
                e = copy.deepcopy(self.history_events)
                e[2]["measurement"] = bad
                with self.assertRaises(BridgeError):
                    history_from_events(EPISODE, e)

    def test_history_tamper_disagrees_with_provenance_digest(self):
        x = copy.deepcopy(self.history)
        x["observations"][0] += 123
        with self.assertRaisesRegex(BridgeError, "digest disagrees"):
            validate_history(x)

    def test_units_or_version_mismatch_rejected(self):
        for key, bad in (("timebase", "60-second-windows"), ("contract", "bk10.capstone.v0"),
                         ("units", "integer count"), ("as_of", 4)):
            with self.subTest(field=key):
                x = copy.deepcopy(self.history)
                x[key] = bad
                with self.assertRaises(BridgeError):
                    validate_history(x)

    def test_fresh_prediction_has_typed_six_step_horizon_no_weights(self):
        out = predict(Provider(), self.history, samples=3, seed=91)
        self.assertEqual(out["forecast_ticks"], [4, 5, 6, 7, 8, 9])
        self.assertEqual(len(out["samples"]), 3)
        self.assertIsNone(out["probability_weights"])
        self.assertEqual(out["source_blob"], PROVIDER_BLOB)
        validate_forecast(out)

    def test_samples_and_seed_bounds(self):
        for count in (0, MAX_SAMPLES + 1, 1.2, True):
            with self.assertRaises(BridgeError):
                predict(Provider(), self.history, samples=count, seed=1)
        for seed in (-1, 2**32, True, 1.2):
            with self.assertRaises(BridgeError):
                predict(Provider(), self.history, samples=1, seed=seed)

    def test_provider_output_shape_nonfinite_bool(self):
        for response in (Array([[0.] * 5]), Array([[0.] * 6, [0.] * 6]),
                         Array([[float("nan")] * 6]), Array([[True] * 6]),
                         [1, 2, 3]):
            with self.subTest(response=str(response)):
                with self.assertRaises(BridgeError):
                    predict(BadProvider(response), self.history, samples=1, seed=4)

    def test_score_truth_not_part_of_predict(self):
        predicted = predict(Provider(), self.history, samples=2, seed=3)
        old = score_after_forecast(predicted, events(4, 10))
        changed = events(4, 10)
        changed[-1]["measurement"] += 100
        new = score_after_forecast(predicted, changed)
        self.assertNotEqual(old["mean_trajectory_mae"], new["mean_trajectory_mae"])
        self.assertEqual(old["forecast_digest"], new["forecast_digest"])

    def test_future_episode_alignment_rejected(self):
        for key, bad in (("time_index", 9), ("episode_id", "synthetic-episode-0099"),
                         ("provenance_tier", "real"), ("event_id", "wrong")):
            with self.subTest(key=key):
                future = events(4, 10)
                future[0][key] = bad
                with self.assertRaises(BridgeError):
                    score_after_forecast(predict(Provider(), self.history, samples=1, seed=0), future)

    def test_forged_forecast_rejected(self):
        out = predict(Provider(), self.history, samples=2, seed=3)
        for key, bad in (("source_commit", "a" * 40), ("probability_weights", [0.5, 0.5]),
                         ("forecast_ticks", [5, 6, 7, 8, 9, 10]), ("source_blob", "bad")):
            with self.subTest(field=key):
                forged = copy.deepcopy(out)
                forged[key] = bad
                with self.assertRaises(BridgeError):
                    score_after_forecast(forged, events(4, 10))

    def test_forged_sample_rejected(self):
        out = predict(Provider(), self.history, samples=2, seed=3)
        out["samples"][0]["measurements"][0] = float("inf")
        with self.assertRaises(BridgeError):
            score_after_forecast(out, events(4, 10))

    def test_corrupted_provider_fails_before_exec(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "provider.py"
            p.write_text("raise RuntimeError('should never execute')")
            with self.assertRaisesRegex(BridgeError, "blob mismatch"):
                load_pinned_provider(p)


class NativeProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get("BK10_BK06_PROVIDER")
        if not source:
            raise unittest.SkipTest("native BK06 source absent; set BK10_BK06_PROVIDER to exact pinned source")
        cls.source = Path(source)

    def test_exact_native_source_bytes(self):
        self.assertEqual(git_blob_sha(self.source.read_bytes()), PROVIDER_BLOB)
        self.assertEqual((load_pinned_provider(self.source).HISTORY, load_pinned_provider(self.source).HORIZON),
                         (4, 6))

    def test_native_training_and_forecast_replay(self):
        a = native_witness(self.source, seed=148, draws=16)
        b = native_witness(self.source, seed=148, draws=16)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertEqual((a["train_episodes"], a["heldout_episodes_available"]), (72, 24))
        self.assertEqual(a["evaluated_episodes"], 1)
        self.assertEqual(len(a["forecast"]["samples"]), 16)
        self.assertGreaterEqual(a["score"]["mean_trajectory_mae"], 0)
        self.assertTrue(a["score"]["endpoint_any_sample_within_0p5"])

    def test_native_truth_mutation_does_not_change_prediction(self):
        bk06 = load_pinned_provider(self.source)
        train, heldout = bk06.split_episodes(bk06.synthetic_events(96, 148), 72)
        model = bk06.ConditionalDiffusion.fit(train)
        target = heldout[0]
        h = history_from_events(target.episode_id, list(target.events[:4]))
        p = predict(model, h, samples=16, seed=248)
        changed = copy.deepcopy(list(target.events[4:]))
        changed[-1]["measurement"] += 30
        self.assertEqual(p["history_digest"], h["history_digest"])
        self.assertNotEqual(score_after_forecast(p, list(target.events[4:]))["mean_trajectory_mae"],
                            score_after_forecast(p, changed)["mean_trajectory_mae"])


if __name__ == "__main__":
    unittest.main()
