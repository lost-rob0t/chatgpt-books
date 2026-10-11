"""CPU-only regression tests for the BK06 Tier-C diffusion laboratory."""
import unittest
from dataclasses import replace

import numpy as np

from trajectory_diffusion import (
    ARBaseline, ConditionalDiffusion, Episode, HORIZON, energy_score, evaluate,
    observed_trend, split_episodes, synthetic_events,
)


class SyntheticStreamTests(unittest.TestCase):
    def setUp(self):
        self.episodes = synthetic_events(96, seed=148)
        self.training, self.heldout = split_episodes(self.episodes, 72)

    def test_deterministic_public_synthetic_envelope(self):
        self.assertEqual(self.episodes, synthetic_events(96, seed=148))
        self.assertEqual(len(self.episodes[0].events), 10)
        self.assertEqual(self.episodes[0].events[0]["provenance_tier"], "C-synthetic")
        self.assertTrue(all(event["episode_id"] == self.episodes[0].episode_id
                            for event in self.episodes[0].events))

    def test_group_split_and_no_future_inference_input(self):
        self.assertFalse({x.episode_id for x in self.training} &
                         {x.episode_id for x in self.heldout})
        model = ConditionalDiffusion.fit(self.training)
        old = self.heldout[0]
        changed = replace(old, future=tuple(x + 100 for x in old.future))
        self.assertTrue(np.array_equal(model.forecast(old.history, 6, 9),
                                       model.forecast(changed.history, 6, 9)))

    def test_reproducible_conditional_multimodal_samples(self):
        model = ConditionalDiffusion.fit(self.training)
        a = model.forecast(self.heldout[0].history, 128, 111)
        b = model.forecast(self.heldout[0].history, 128, 111)
        self.assertTrue(np.array_equal(a, b))
        self.assertEqual(a.shape, (128, HORIZON))
        deviation = a[:, -1] - observed_trend(self.heldout[0].history)[-1]
        self.assertTrue((deviation > 1).any())
        self.assertTrue((deviation < -1).any())

    def test_denoiser_shapes_and_invalid_history(self):
        model = ConditionalDiffusion.fit(self.training)
        result = model.denoise_x0(np.zeros((2, HORIZON)), 0)
        self.assertEqual(result.shape, (2, HORIZON))
        for bad in [(1.0,), (float("nan"),) * 4]:
            with self.assertRaises(ValueError):
                model.forecast(bad, 4, 1)
        with self.assertRaises(ValueError):
            model.forecast(self.heldout[0].history, 0, 1)
        with self.assertRaises(ValueError):
            model.denoise_x0(np.zeros((2, 3)), 0)

    def test_energy_score_deterministic_reference(self):
        truth = np.zeros(HORIZON)
        forecast = np.ones((1, HORIZON))
        self.assertAlmostEqual(energy_score(forecast, truth), np.sqrt(HORIZON))
        self.assertAlmostEqual(energy_score(np.zeros((3, HORIZON)), truth), 0.0)

    def test_ar_baseline_and_training_contract(self):
        model = ARBaseline.fit(self.training)
        self.assertEqual(model.forecast(self.heldout[0].history).shape, (HORIZON,))
        with self.assertRaises(ValueError):
            split_episodes(self.episodes, len(self.episodes))
        with self.assertRaises(ValueError):
            evaluate(self.training, self.training[:1])

    def test_evaluation_reports_reproducible_bounded_metrics(self):
        a = evaluate(self.training, self.heldout, seed=19, draws=12)
        b = evaluate(self.training, self.heldout, seed=19, draws=12)
        self.assertEqual(a, b)
        self.assertEqual(a["n_test"], 24)
        self.assertGreater(a["diffusion_endpoint_pairwise_abs"], 0)
        self.assertGreaterEqual(a["diffusion_endpoint_coverage_0p5"], 0)
        self.assertLessEqual(a["diffusion_endpoint_coverage_0p5"], 1)
        self.assertLessEqual(a["diffusion_oracle_minade_at_k"], a["diffusion_one_draw_ade"])
        for k in ["ar_ade", "diffusion_mean_ade", "diffusion_energy", "ar_energy"]:
            self.assertTrue(np.isfinite(a[k]))


if __name__ == "__main__":
    unittest.main()
