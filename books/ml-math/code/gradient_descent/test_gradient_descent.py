from __future__ import annotations

import unittest

from gradient_descent import (
    Quadratic1D,
    Quadratic2D,
    classify_scalar_step,
    closed_form_parameter,
    error_multiplier,
    quadratic2d_gradient,
    quadratic2d_value,
    quadratic_gradient,
    quadratic_value,
    trace_quadratic_1d,
    trace_quadratic_2d,
)


class GradientDescentRegimeTests(unittest.TestCase):
    def test_scalar_value_and_gradient(self) -> None:
        objective = Quadratic1D(curvature=2.0, center=3.0, minimum=7.0)
        self.assertEqual(quadratic_value(objective, 5.0), 11.0)
        self.assertEqual(quadratic_gradient(objective, 5.0), 4.0)

    def test_iterative_trace_matches_exact_error_recurrence(self) -> None:
        objective = Quadratic1D(curvature=2.0, center=1.5)
        trace = trace_quadratic_1d(
            objective,
            initial_parameter=5.5,
            learning_rate=0.25,
            steps=8,
        )
        self.assertEqual(error_multiplier(2.0, 0.25), 0.5)
        for point in trace:
            expected = closed_form_parameter(
                objective,
                5.5,
                0.25,
                point.step,
            )
            self.assertAlmostEqual(point.parameter, expected, places=14)

    def test_scalar_regime_classification(self) -> None:
        curvature = 2.0
        self.assertEqual(classify_scalar_step(curvature, 0.25), "monotone-convergent")
        self.assertEqual(classify_scalar_step(curvature, 0.50), "one-step")
        self.assertEqual(
            classify_scalar_step(curvature, 0.75),
            "oscillatory-convergent",
        )
        self.assertEqual(classify_scalar_step(curvature, 1.00), "neutral")
        self.assertEqual(classify_scalar_step(curvature, 1.10), "divergent")

    def test_monotone_regime_keeps_error_sign_and_shrinks_magnitude(self) -> None:
        trace = trace_quadratic_1d(
            Quadratic1D(2.0),
            initial_parameter=4.0,
            learning_rate=0.25,
            steps=6,
        )
        errors = [point.error for point in trace]
        self.assertTrue(all(error > 0.0 for error in errors))
        self.assertTrue(
            all(abs(after) < abs(before) for before, after in zip(errors, errors[1:]))
        )

    def test_oscillatory_regime_flips_sign_while_shrinking(self) -> None:
        trace = trace_quadratic_1d(
            Quadratic1D(2.0),
            initial_parameter=4.0,
            learning_rate=0.75,
            steps=6,
        )
        errors = [point.error for point in trace]
        self.assertTrue(
            all(before * after < 0.0 for before, after in zip(errors, errors[1:]))
        )
        self.assertTrue(
            all(abs(after) < abs(before) for before, after in zip(errors, errors[1:]))
        )

    def test_neutral_boundary_forms_two_cycle_with_constant_loss(self) -> None:
        trace = trace_quadratic_1d(
            Quadratic1D(2.0),
            initial_parameter=4.0,
            learning_rate=1.0,
            steps=6,
        )
        self.assertEqual(
            tuple(point.parameter for point in trace[:4]),
            (4.0, -4.0, 4.0, -4.0),
        )
        self.assertTrue(all(point.loss == trace[0].loss for point in trace))

    def test_divergent_regime_grows_error_and_loss(self) -> None:
        trace = trace_quadratic_1d(
            Quadratic1D(2.0),
            initial_parameter=1.0,
            learning_rate=1.1,
            steps=5,
        )
        self.assertGreater(abs(trace[-1].error), abs(trace[0].error))
        self.assertGreater(trace[-1].loss, trace[0].loss)

    def test_one_step_rate_lands_at_the_minimum(self) -> None:
        objective = Quadratic1D(curvature=4.0, center=-2.0, minimum=3.0)
        trace = trace_quadratic_1d(
            objective,
            initial_parameter=6.0,
            learning_rate=0.25,
            steps=2,
        )
        self.assertEqual(trace[1].parameter, -2.0)
        self.assertEqual(trace[1].gradient, 0.0)
        self.assertEqual(trace[1].loss, 3.0)
        self.assertEqual(trace[2].parameter, -2.0)
        self.assertEqual(trace[2].loss, 3.0)

    def test_axis_aligned_gradient_and_value(self) -> None:
        objective = Quadratic2D(
            curvature_x=1.0,
            curvature_y=10.0,
            center_x=1.0,
            center_y=-1.0,
            minimum=2.0,
        )
        self.assertEqual(quadratic2d_gradient(objective, 3.0, 1.0), (2.0, 20.0))
        self.assertEqual(quadratic2d_value(objective, 3.0, 1.0), 24.0)

    def test_axis_aligned_components_obey_independent_recurrences(self) -> None:
        objective = Quadratic2D(curvature_x=1.0, curvature_y=10.0)
        trace = trace_quadratic_2d(
            objective,
            initial_x=4.0,
            initial_y=4.0,
            learning_rate=0.18,
            steps=6,
        )
        for point in trace:
            self.assertAlmostEqual(point.x, 4.0 * (0.82**point.step), places=13)
            self.assertAlmostEqual(point.y, 4.0 * ((-0.8) ** point.step), places=13)

    def test_stiff_axis_zigzags_while_loss_falls(self) -> None:
        trace = trace_quadratic_2d(
            Quadratic2D(curvature_x=1.0, curvature_y=10.0),
            initial_x=4.0,
            initial_y=4.0,
            learning_rate=0.18,
            steps=8,
        )
        self.assertTrue(
            all(
                before.error_y * after.error_y < 0.0
                for before, after in zip(trace, trace[1:])
            )
        )
        self.assertTrue(
            all(after.loss < before.loss for before, after in zip(trace, trace[1:]))
        )

    def test_rate_can_stabilize_one_axis_and_diverge_on_another(self) -> None:
        trace = trace_quadratic_2d(
            Quadratic2D(curvature_x=1.0, curvature_y=10.0),
            initial_x=4.0,
            initial_y=4.0,
            learning_rate=0.22,
            steps=8,
        )
        self.assertLess(abs(trace[-1].error_x), abs(trace[0].error_x))
        self.assertGreater(abs(trace[-1].error_y), abs(trace[0].error_y))
        self.assertGreater(trace[-1].loss, trace[0].loss)

    def test_invalid_and_non_finite_inputs_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "curvature must be positive"):
            trace_quadratic_1d(
                Quadratic1D(0.0),
                initial_parameter=1.0,
                learning_rate=0.1,
                steps=1,
            )
        with self.assertRaisesRegex(ValueError, "learning rate must be positive"):
            trace_quadratic_1d(
                Quadratic1D(1.0),
                initial_parameter=1.0,
                learning_rate=0.0,
                steps=1,
            )
        with self.assertRaisesRegex(TypeError, "steps must be an integer"):
            trace_quadratic_1d(
                Quadratic1D(1.0),
                initial_parameter=1.0,
                learning_rate=0.1,
                steps=True,
            )
        with self.assertRaisesRegex(ValueError, "became non-finite"):
            trace_quadratic_1d(
                Quadratic1D(1e200),
                initial_parameter=1e100,
                learning_rate=1e100,
                steps=1,
            )


if __name__ == "__main__":
    unittest.main()
