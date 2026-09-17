from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CALCULUS_DIR = HERE.parent / "calculus"
if CALCULUS_DIR.exists():
    sys.path.insert(0, str(CALCULUS_DIR))

from linear_regression import (
    Model,
    fit_batch_gradient_descent,
    fit_centered_closed_form,
    mean_squared_error,
    mse_gradient,
    predict,
    residuals,
)

try:
    from calculus_lab import affine_mse, numerical_gradient
except ModuleNotFoundError:  # local standalone development fixture
    affine_mse = None
    numerical_gradient = None

TRAIN_X = (0.0, 1.0, 2.0, 3.0, 4.0, 5.0)
TRAIN_Y = (1.1, 2.9, 5.2, 6.8, 9.1, 10.9)
EVAL_X = (6.0, 7.0, 8.0)
EVAL_Y = (13.2, 14.8, 17.1)


class LinearRegressionTests(unittest.TestCase):
    def test_prediction_and_residual_sign(self) -> None:
        model = Model(2.0, 1.0)
        self.assertEqual(predict(model, (0.0, 2.0)), (1.0, 5.0))
        self.assertEqual(residuals(model, (0.0, 2.0), (1.5, 4.0)), (-0.5, 1.0))

    def test_mse_matches_direct_numpy_calculation(self) -> None:
        model = Model(1.7, 0.4)
        actual = mean_squared_error(model, TRAIN_X, TRAIN_Y)
        expected = float(
            np.mean((1.7 * np.asarray(TRAIN_X) + 0.4 - np.asarray(TRAIN_Y)) ** 2)
        )
        self.assertAlmostEqual(actual, expected, places=12)

    def test_gradient_matches_finite_difference_oracle(self) -> None:
        if numerical_gradient is None or affine_mse is None:
            self.skipTest("calculus lab not present in local standalone fixture")
        model = Model(1.4, 0.3)
        analytic = mse_gradient(model, TRAIN_X, TRAIN_Y)
        numeric = numerical_gradient(
            lambda params: affine_mse(params, TRAIN_X, TRAIN_Y),
            (model.weight, model.bias),
            step=1e-5,
        )
        np.testing.assert_allclose(analytic, numeric, rtol=1e-8, atol=1e-8)

    def test_centered_closed_form_matches_numpy_lstsq(self) -> None:
        model = fit_centered_closed_form(TRAIN_X, TRAIN_Y)
        design = np.column_stack([np.asarray(TRAIN_X), np.ones(len(TRAIN_X))])
        expected, _, _, _ = np.linalg.lstsq(design, np.asarray(TRAIN_Y), rcond=None)
        np.testing.assert_allclose(
            (model.weight, model.bias), expected, rtol=1e-12, atol=1e-12
        )

    def test_gradient_descent_converges_to_closed_form_fit(self) -> None:
        closed = fit_centered_closed_form(TRAIN_X, TRAIN_Y)
        result = fit_batch_gradient_descent(
            TRAIN_X,
            TRAIN_Y,
            learning_rate=0.05,
            max_steps=2000,
            gradient_tolerance=1e-10,
        )
        self.assertTrue(result.converged)
        self.assertLess(result.steps, 1000)
        self.assertAlmostEqual(result.model.weight, closed.weight, places=8)
        self.assertAlmostEqual(result.model.bias, closed.bias, places=8)
        self.assertAlmostEqual(
            result.loss,
            mean_squared_error(closed, TRAIN_X, TRAIN_Y),
            places=12,
        )

    def test_history_starts_at_initial_model_and_records_final_model(self) -> None:
        result = fit_batch_gradient_descent(
            TRAIN_X,
            TRAIN_Y,
            learning_rate=0.05,
            max_steps=4,
            gradient_tolerance=0.0,
        )
        self.assertEqual(result.history[0].step, 0)
        self.assertEqual(result.history[0].weight, 0.0)
        self.assertEqual(result.history[-1].step, 4)
        self.assertEqual(result.steps, 4)
        self.assertFalse(result.converged)

    def test_fixed_holdout_evaluation_is_finite(self) -> None:
        model = fit_centered_closed_form(TRAIN_X, TRAIN_Y)
        train_loss = mean_squared_error(model, TRAIN_X, TRAIN_Y)
        eval_loss = mean_squared_error(model, EVAL_X, EVAL_Y)
        self.assertTrue(np.isfinite(train_loss))
        self.assertTrue(np.isfinite(eval_loss))
        self.assertGreaterEqual(train_loss, 0.0)
        self.assertGreaterEqual(eval_loss, 0.0)

    def test_constant_feature_has_no_unique_affine_slope(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not all be identical"):
            fit_centered_closed_form((2.0, 2.0, 2.0), (1.0, 2.0, 3.0))

    def test_invalid_and_non_finite_data_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "same length"):
            mean_squared_error(Model(1.0, 0.0), (1.0, 2.0), (1.0,))
        with self.assertRaisesRegex(ValueError, "finite"):
            mean_squared_error(
                Model(1.0, 0.0), (1.0, float("inf")), (1.0, 2.0)
            )
        with self.assertRaisesRegex(TypeError, "real number"):
            mean_squared_error(Model(1.0, 0.0), (1.0, True), (1.0, 2.0))

    def test_bad_learning_rate_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            fit_batch_gradient_descent(TRAIN_X, TRAIN_Y, learning_rate=0.0)
        with self.assertRaisesRegex(ValueError, "positive"):
            fit_batch_gradient_descent(TRAIN_X, TRAIN_Y, learning_rate=-0.1)

    def test_large_but_finite_learning_rate_exposes_divergence(self) -> None:
        result = fit_batch_gradient_descent(
            TRAIN_X,
            TRAIN_Y,
            learning_rate=0.2,
            max_steps=8,
            gradient_tolerance=1e-12,
        )
        self.assertFalse(result.converged)
        self.assertGreater(result.history[-1].loss, result.history[0].loss)

    def test_non_finite_update_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "became non-finite"):
            fit_batch_gradient_descent(
                (1e150, 2e150),
                (1.0, 2.0),
                learning_rate=1e150,
                max_steps=1,
            )


if __name__ == "__main__":
    unittest.main()
