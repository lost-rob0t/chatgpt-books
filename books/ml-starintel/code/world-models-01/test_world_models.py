"""Focused native-stdlib regressions for the World Models I teaching fixture."""

import unittest
from math import isfinite

from world_models import (
    BinaryWorldModel,
    DATASET,
    VERSION,
    WINDOW_SECONDS,
    aggregate_synthetic_events,
    entropy_bits,
    run_fixture,
    synthetic_documents,
)


START = 1_700_000_040


class SyntheticEventMappingTests(unittest.TestCase):
    def test_all_zero_and_nonzero_sealed_windows_and_provenance(self):
        windows, steps = run_fixture()
        self.assertEqual([w.count for w in windows], [0, 2, 3, 1])
        self.assertEqual([w.bucket for w in windows], ["low", "high", "high", "low"])
        self.assertEqual([len(w.source_ids) for w in windows], [0, 2, 3, 1])
        self.assertEqual(len(steps), 4)
        self.assertEqual(windows[0].window_start, START)

    def test_permutation_does_not_change_source_order_or_prediction(self):
        original = synthetic_documents()
        forward = aggregate_synthetic_events(original, start=START, windows=4)
        backward = aggregate_synthetic_events(tuple(reversed(original)), start=START, windows=4)
        self.assertEqual(forward, backward)
        self.assertEqual(BinaryWorldModel().filter(forward), BinaryWorldModel().filter(backward))

    def test_duplicate_event_identity_rejected(self):
        events = synthetic_documents()
        with self.assertRaisesRegex(ValueError, "unique"):
            aggregate_synthetic_events(events + (events[0],), start=START, windows=4)

    def test_outside_window_rejected(self):
        event = dict(synthetic_documents()[0]); event["observedAt"] = START + 4 * WINDOW_SECONDS
        with self.assertRaisesRegex(ValueError, "outside"):
            aggregate_synthetic_events((event,), start=START, windows=4)

    def test_wrong_version_dataset_or_type_rejected(self):
        for key, value in (("schemaVersion", "0.9.0"), ("dataset", "other"), ("dtype", "person")):
            with self.subTest(field=key):
                event = dict(synthetic_documents()[0]); event[key] = value
                with self.assertRaises(ValueError):
                    aggregate_synthetic_events((event,), start=START, windows=4)

    def test_missing_timestamp_does_not_become_observed_zero(self):
        event = dict(synthetic_documents()[0]); del event["observedAt"]
        with self.assertRaises(ValueError):
            aggregate_synthetic_events((event,), start=START, windows=4)

    def test_invalid_window_definition_rejected(self):
        for kwargs in ({"start": START + 1, "windows": 4},
                       {"start": START, "windows": 0},
                       {"start": START, "windows": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                aggregate_synthetic_events((), **kwargs)


class BeliefFilteringTests(unittest.TestCase):
    def test_known_first_low_observation_bayes_posterior(self):
        _, steps = run_fixture()
        first = steps[0]
        self.assertAlmostEqual(first.observation_probability, 0.60)
        self.assertAlmostEqual(first.posterior_state[0], 0.80)
        self.assertAlmostEqual(first.posterior_state[1], 0.20)
        self.assertAlmostEqual(first.next_high_probability, 0.335)

    def test_posterior_and_emission_normalized(self):
        _, steps = run_fixture()
        for step in steps:
            with self.subTest(window=step.window_start):
                self.assertAlmostEqual(sum(step.predicted_state), 1.0)
                self.assertAlmostEqual(sum(step.posterior_state), 1.0)
                self.assertTrue(0.0 <= step.next_high_probability <= 1.0)
                self.assertTrue(isfinite(step.posterior_entropy_bits))

    def test_rollout_does_not_condition_on_imagined_measurements(self):
        model = BinaryWorldModel()
        _, steps = run_fixture()
        projected = model.rollout_high(steps[-1].posterior_state, 50)
        self.assertEqual(len(projected), 50)
        self.assertAlmostEqual(projected[0], steps[-1].next_high_probability)
        self.assertAlmostEqual(projected[-1], 0.3875, places=9)
        self.assertEqual(model.rollout_high(steps[-1].posterior_state, 0), ())

    def test_future_publication_cannot_change_past_forecast(self):
        documents = synthetic_documents()
        prefix = aggregate_synthetic_events(documents[:2], start=START, windows=2)
        entire = aggregate_synthetic_events(documents, start=START, windows=4)
        model = BinaryWorldModel()
        self.assertEqual(model.filter(prefix), model.filter(entire)[:2])

    def test_zero_likelihood_fails_closed(self):
        model = BinaryWorldModel(emission=((1.0, 0.0), (1.0, 0.0)))
        with self.assertRaisesRegex(ValueError, "zero likelihood"):
            model.update((0.6, 0.4), "high")

    def test_invalid_rows_and_horizon_rejected(self):
        with self.assertRaises(ValueError):
            BinaryWorldModel(transition=((0.9, 0.4), (0.25, 0.75)))
        with self.assertRaises(ValueError):
            BinaryWorldModel(prior=(float("nan"), 0.5))
        with self.assertRaises(ValueError):
            BinaryWorldModel().rollout_high((0.6, 0.4), -1)
        with self.assertRaises(ValueError):
            BinaryWorldModel().rollout_high((0.6, 0.4), True)
        with self.assertRaises(ValueError):
            entropy_bits((0.4, 0.7))


if __name__ == "__main__":
    unittest.main()
