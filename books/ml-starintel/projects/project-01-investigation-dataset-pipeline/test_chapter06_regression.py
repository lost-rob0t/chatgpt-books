from __future__ import annotations

import math
import unittest
from dataclasses import replace

from chapter06_regression import (
    fit_simple_ols,
    make_synthetic_workload,
    regression_metrics,
    run_regression_control,
    split_by_declared_groups,
)


class SimpleOlsTests(unittest.TestCase):
    def test_exact_line_is_recovered(self) -> None:
        line = fit_simple_ols([0, 1, 2, 3], [3, 5, 7, 9])
        self.assertAlmostEqual(line.intercept, 3.0)
        self.assertAlmostEqual(line.slope, 2.0)
        self.assertAlmostEqual(line.predict(5), 13.0)

    def test_zero_variance_feature_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "zero variance"):
            fit_simple_ols([4, 4, 4], [1, 2, 3])

    def test_metrics_keep_error_units_and_allow_negative_r2(self) -> None:
        metrics = regression_metrics([1.0, 2.0, 3.0], [3.0, 2.0, 1.0])
        self.assertAlmostEqual(metrics["mae"], 4.0 / 3.0)
        self.assertAlmostEqual(metrics["rmse"], math.sqrt(8.0 / 3.0))
        self.assertAlmostEqual(metrics["r2"], -3.0)


class RegressionControlTests(unittest.TestCase):
    def test_declared_group_split_has_no_overlap(self) -> None:
        rows = make_synthetic_workload()
        train, test = split_by_declared_groups(
            rows,
            [f"synthetic-case-{number:02d}" for number in range(8)],
        )
        self.assertEqual(len(train), 24)
        self.assertEqual(len(test), 12)
        self.assertFalse(
            {row.group_id for row in train} & {row.group_id for row in test}
        )

    def test_linear_model_beats_training_mean_on_frozen_control(self) -> None:
        report = run_regression_control()
        self.assertEqual(report["group_overlap"], [])
        self.assertLess(
            report["ols"]["test_metrics"]["rmse"],
            report["baseline"]["test_metrics"]["rmse"],
        )
        self.assertGreater(report["ols"]["test_metrics"]["r2"], 0.9)

    def test_test_target_change_cannot_change_fitted_coefficients(self) -> None:
        rows = make_synthetic_workload()
        original = run_regression_control(rows)
        changed = [
            replace(row, review_minutes=row.review_minutes + 1000.0)
            if row.group_id == "synthetic-case-11"
            else row
            for row in rows
        ]
        mutated = run_regression_control(changed)
        self.assertEqual(
            original["ols"]["coefficients"], mutated["ols"]["coefficients"]
        )
        self.assertEqual(
            original["ols"]["intercept"], mutated["ols"]["intercept"]
        )
        self.assertNotEqual(
            original["ols"]["test_metrics"]["rmse"],
            mutated["ols"]["test_metrics"]["rmse"],
        )

    def test_outlier_failure_injection_moves_rmse_more_than_mae(self) -> None:
        failure = run_regression_control()["outlier_failure_injection"]
        mae_delta = (
            failure["outlier_metrics"]["mae"]
            - failure["clean_metrics"]["mae"]
        )
        rmse_delta = (
            failure["outlier_metrics"]["rmse"]
            - failure["clean_metrics"]["rmse"]
        )
        self.assertGreater(rmse_delta, mae_delta)

    def test_extrapolation_probe_is_not_scored_without_a_label(self) -> None:
        probe = run_regression_control()["extrapolation_probe"]
        self.assertTrue(probe["outside_observed_training_range"])
        self.assertFalse(probe["label_available"])


if __name__ == "__main__":
    unittest.main()
