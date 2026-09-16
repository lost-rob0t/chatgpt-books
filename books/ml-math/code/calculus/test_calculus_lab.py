import math
import unittest

import numpy as np

from calculus_lab import (
    affine_mse,
    affine_mse_gradient,
    central_difference,
    directional_derivative_from_gradient,
    forward_difference,
    numerical_gradient,
    partial_difference,
    point,
)


class CalculusLabTests(unittest.TestCase):
    def test_scalar_derivative_matches_square_slope(self):
        square = lambda x: x * x
        self.assertAlmostEqual(forward_difference(square, 3.0, step=1e-6), 6.000001, places=5)
        self.assertAlmostEqual(central_difference(square, 3.0, step=1e-5), 6.0, places=9)

    def test_central_difference_matches_cosine_for_sine(self):
        estimate = central_difference(math.sin, 1.0, step=1e-5)
        self.assertAlmostEqual(estimate, math.cos(1.0), places=9)

    def test_partial_and_gradient_match_quadratic_bowl(self):
        bowl = lambda p: (p[0] - 2.0) ** 2 + 3.0 * (p[1] + 1.0) ** 2
        at = (5.0, 2.0)
        self.assertAlmostEqual(partial_difference(bowl, at, 0), 6.0, places=8)
        gradient = numerical_gradient(bowl, at)
        self.assertAlmostEqual(gradient[0], 6.0, places=8)
        self.assertAlmostEqual(gradient[1], 18.0, places=8)

    def test_directional_derivative_uses_unit_direction(self):
        value = directional_derivative_from_gradient((6.0, 18.0), (3.0, 4.0))
        self.assertAlmostEqual(value, 18.0, places=12)

    def test_zero_direction_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "non-zero"):
            directional_derivative_from_gradient((1.0, 2.0), (0.0, 0.0))

    def test_invalid_step_and_nonfinite_input_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            central_difference(lambda x: x, 1.0, step=0.0)
        with self.assertRaisesRegex(ValueError, "finite"):
            central_difference(lambda x: x, math.inf)

    def test_too_small_step_is_rejected_instead_of_silently_returning_zero(self):
        with self.assertRaisesRegex(ValueError, "too small"):
            central_difference(lambda x: x * x, 1e16, step=1e-16)

    def test_displaced_sample_overflow_is_rejected_before_function_evaluation(self):
        with self.assertRaisesRegex(ValueError, "sample x must be finite"):
            central_difference(lambda x: 0.0, 1e308, step=1e308)
        with self.assertRaisesRegex(ValueError, "displaced x must be finite"):
            forward_difference(lambda x: 0.0, 1e308, step=1e308)
        with self.assertRaisesRegex(ValueError, "sample component must be finite"):
            partial_difference(lambda p: 0.0, (1e308,), 0, step=1e308)

    def test_numerical_estimate_is_not_proof_that_a_derivative_exists(self):
        self.assertEqual(central_difference(abs, 0.0, step=1e-4), 0.0)

    def test_affine_mse_and_analytic_gradient(self):
        features = (0.0, 1.0, 2.0)
        targets = (1.0, 3.0, 5.0)
        params = (1.0, 0.0)
        self.assertAlmostEqual(affine_mse(params, features, targets), 14.0 / 3.0)
        gradient = affine_mse_gradient(params, features, targets)
        self.assertAlmostEqual(gradient[0], -16.0 / 3.0)
        self.assertAlmostEqual(gradient[1], -4.0)

    def test_affine_mse_gradient_matches_independent_finite_difference(self):
        features = (0.0, 1.0, 2.0, 4.0)
        targets = (1.0, 2.5, 5.0, 8.5)
        params = (0.8, -0.2)
        analytic = affine_mse_gradient(params, features, targets)
        numeric = numerical_gradient(
            lambda p: affine_mse(p, features, targets),
            params,
            step=1e-5,
        )
        for actual, expected in zip(analytic, numeric, strict=True):
            self.assertAlmostEqual(actual, expected, places=8)

    def test_numpy_2_5_sampled_gradient_agrees_for_quadratic_grid(self):
        xs = np.linspace(-2.0, 2.0, 9)
        ys = xs ** 2
        oracle = np.gradient(ys, xs, edge_order=2)
        ours = np.array([central_difference(lambda x: x * x, float(x), step=1e-5) for x in xs])
        np.testing.assert_allclose(ours, oracle, rtol=1e-10, atol=1e-10)

    def test_point_contract_rejects_empty_boolean_and_nonfinite(self):
        with self.assertRaisesRegex(ValueError, "at least one"):
            point(())
        with self.assertRaises(TypeError):
            point((True,))
        with self.assertRaisesRegex(ValueError, "finite"):
            point((math.nan,))

    def test_huge_finite_direction_that_overflows_norm_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "magnitude must be finite"):
            directional_derivative_from_gradient((1.0, 1.0), (1.79e308, 1.79e308))

    def test_affine_mse_rejects_nonfinite_intermediate(self):
        with self.assertRaisesRegex(ValueError, "squared residual"):
            affine_mse((1e154, 0.0), (2.0,), (0.0,))

    def test_enormous_integer_input_is_rejected_as_unrepresentable(self):
        with self.assertRaisesRegex(ValueError, "finite float"):
            point((10**400,))

    def test_feature_target_dimension_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "same length"):
            affine_mse((1.0, 0.0), (1.0, 2.0), (1.0,))


if __name__ == "__main__":
    unittest.main()
