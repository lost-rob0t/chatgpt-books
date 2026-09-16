from __future__ import annotations

import unittest

from chapter01_constant_baseline import (
    ConstantRegressor,
    evaluate_baseline,
    fit_constant_regressor,
    mean_squared_error,
)


class ConstantBaselineTests(unittest.TestCase):
    def test_fit_learns_training_mean(self) -> None:
        model = fit_constant_regressor([1, 2, 6])
        self.assertEqual(model, ConstantRegressor(3.0))
        self.assertEqual(model.predict(3), [3.0, 3.0, 3.0])

    def test_mse_is_mean_of_squared_residuals(self) -> None:
        self.assertAlmostEqual(mean_squared_error([1, 3], [2, 2]), 1.0)

    def test_evaluation_fits_only_from_supplied_training_targets(self) -> None:
        result = evaluate_baseline([1, 3], [10, 10])
        self.assertEqual(result["fitted_constant"], 2.0)
        self.assertEqual(result["test_mse"], 64.0)

    def test_empty_training_targets_fail(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one value"):
            fit_constant_regressor([])

    def test_invalid_prediction_count_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-negative"):
            ConstantRegressor(1.0).predict(-1)


if __name__ == "__main__":
    unittest.main()
