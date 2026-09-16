#!/usr/bin/env python3
"""Tiny first-principles baseline used by ML-StarIntel Chapter 1.

The model has one learned parameter: the mean of the training targets.  It is
intentionally small enough that readers can derive the objective before using a
general machine-learning library.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import fsum
from typing import Iterable, Sequence


@dataclass(frozen=True)
class ConstantRegressor:
    value: float

    def predict(self, count: int) -> list[float]:
        if count < 0:
            raise ValueError("prediction count must be non-negative")
        return [self.value] * count


def _as_floats(values: Iterable[float]) -> list[float]:
    result = [float(value) for value in values]
    if not result:
        raise ValueError("at least one value is required")
    return result


def mean_squared_error(expected: Sequence[float], predicted: Sequence[float]) -> float:
    if len(expected) != len(predicted):
        raise ValueError("expected and predicted lengths must match")
    if not expected:
        raise ValueError("at least one prediction is required")
    squared_errors = [
        (float(actual) - float(estimate)) ** 2
        for actual, estimate in zip(expected, predicted, strict=True)
    ]
    return fsum(squared_errors) / len(squared_errors)


def fit_constant_regressor(training_targets: Iterable[float]) -> ConstantRegressor:
    """Fit the constant that minimizes training mean squared error."""
    targets = _as_floats(training_targets)
    return ConstantRegressor(value=fsum(targets) / len(targets))


def evaluate_baseline(
    training_targets: Iterable[float],
    test_targets: Sequence[float],
) -> dict[str, float]:
    model = fit_constant_regressor(training_targets)
    predictions = model.predict(len(test_targets))
    return {
        "fitted_constant": model.value,
        "test_mse": mean_squared_error(test_targets, predictions),
    }
