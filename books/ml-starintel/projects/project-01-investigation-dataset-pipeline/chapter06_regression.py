#!/usr/bin/env python3
"""Chapter 6 regression lab for ML-StarIntel.

This is a deterministic Tier C teaching control. It does not model production
StarIntel quality, throughput, or analyst labor.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from math import fsum, sqrt
from pathlib import Path
from typing import Iterable, Sequence

import matplotlib.pyplot as plt
import numpy as np
from sklearn.linear_model import LinearRegression


FEATURE_NAMES = ("token_count", "relation_count", "source_count")


@dataclass(frozen=True)
class SimpleLine:
    intercept: float
    slope: float

    def predict(self, x: float) -> float:
        return self.intercept + self.slope * float(x)


@dataclass(frozen=True)
class WorkloadRow:
    record_id: str
    group_id: str
    token_count: int
    relation_count: int
    source_count: int
    review_minutes: float

    def features(self) -> tuple[float, float, float]:
        return (
            float(self.token_count),
            float(self.relation_count),
            float(self.source_count),
        )


def _floats(values: Iterable[float]) -> list[float]:
    result = [float(value) for value in values]
    if not result:
        raise ValueError("at least one value is required")
    return result


def fit_simple_ols(xs: Iterable[float], ys: Iterable[float]) -> SimpleLine:
    """Fit y = intercept + slope*x by the centered least-squares equations."""
    x = _floats(xs)
    y = _floats(ys)
    if len(x) != len(y):
        raise ValueError("x and y lengths must match")
    if len(x) < 2:
        raise ValueError("at least two observations are required")

    x_bar = fsum(x) / len(x)
    y_bar = fsum(y) / len(y)
    sxx = fsum((value - x_bar) ** 2 for value in x)
    if sxx == 0.0:
        raise ValueError("cannot fit a slope when x has zero variance")

    sxy = fsum(
        (x_value - x_bar) * (y_value - y_bar)
        for x_value, y_value in zip(x, y, strict=True)
    )
    slope = sxy / sxx
    return SimpleLine(intercept=y_bar - slope * x_bar, slope=slope)


def regression_metrics(
    actual: Sequence[float], predicted: Sequence[float]
) -> dict[str, float]:
    """Compute MAE, RMSE, and R^2 from their definitions."""
    if len(actual) != len(predicted):
        raise ValueError("actual and predicted lengths must match")
    if not actual:
        raise ValueError("at least one prediction is required")

    residuals = [
        float(y) - float(y_hat)
        for y, y_hat in zip(actual, predicted, strict=True)
    ]
    mae = fsum(abs(value) for value in residuals) / len(residuals)
    mse = fsum(value * value for value in residuals) / len(residuals)
    mean_actual = fsum(float(value) for value in actual) / len(actual)
    denominator = fsum((float(value) - mean_actual) ** 2 for value in actual)
    numerator = fsum(value * value for value in residuals)
    r2 = 1.0 - numerator / denominator if denominator else float("nan")
    return {"mae": mae, "rmse": sqrt(mse), "r2": r2}


def make_synthetic_workload() -> list[WorkloadRow]:
    """Create a deterministic grouped regression control with known structure."""
    noise = (-2.0, -1.0, 0.0, 1.0, 2.0)
    rows: list[WorkloadRow] = []
    for group_number in range(12):
        for within_group in range(3):
            k = group_number * 3 + within_group
            token_count = 120 + (k * 37) % 360
            relation_count = (group_number + 2 * within_group) % 7
            source_count = 1 + (group_number + within_group) % 4
            review_minutes = (
                12.0
                + 0.04 * token_count
                + 2.5 * relation_count
                + 1.75 * source_count
                + noise[k % len(noise)]
            )
            rows.append(
                WorkloadRow(
                    record_id=f"synthetic-doc-{k:02d}",
                    group_id=f"synthetic-case-{group_number:02d}",
                    token_count=token_count,
                    relation_count=relation_count,
                    source_count=source_count,
                    review_minutes=review_minutes,
                )
            )
    return rows


def split_by_declared_groups(
    rows: Sequence[WorkloadRow],
    train_groups: Sequence[str],
) -> tuple[list[WorkloadRow], list[WorkloadRow]]:
    """Apply an already-declared group boundary; do not infer grouping here."""
    train_group_set = set(train_groups)
    train = [row for row in rows if row.group_id in train_group_set]
    test = [row for row in rows if row.group_id not in train_group_set]
    if not train or not test:
        raise ValueError("split must contain both train and test rows")

    overlap = {row.group_id for row in train} & {row.group_id for row in test}
    if overlap:
        raise ValueError(f"group contamination: {sorted(overlap)}")
    return train, test


def _matrix(rows: Sequence[WorkloadRow]) -> np.ndarray:
    return np.asarray([row.features() for row in rows], dtype=float)


def _targets(rows: Sequence[WorkloadRow]) -> np.ndarray:
    return np.asarray([row.review_minutes for row in rows], dtype=float)


def _rank_deficiency_probe(
    model: LinearRegression,
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_test: np.ndarray,
) -> dict[str, object]:
    """Duplicate one predictor to expose coefficient non-identifiability.

    The duplicated feature adds no information. The diagnostic asks whether the
    dense design loses full column rank while predictions remain equivalent to
    the original fit on the same held-out rows.
    """
    duplicate_train = np.column_stack((x_train, x_train[:, 0]))
    duplicate_test = np.column_stack((x_test, x_test[:, 0]))
    duplicated_model = LinearRegression()
    duplicated_model.fit(duplicate_train, y_train)

    base_prediction = model.predict(x_test)
    duplicated_prediction = duplicated_model.predict(duplicate_test)
    prediction_delta = np.abs(base_prediction - duplicated_prediction)
    duplicate_coefficient_sum = float(
        duplicated_model.coef_[0] + duplicated_model.coef_[-1]
    )

    return {
        "claim_scope": "deterministic exact-duplicate-feature identifiability probe",
        "duplicated_feature": FEATURE_NAMES[0],
        "augmented_feature_names": [*FEATURE_NAMES, "token_count_duplicate"],
        "base_design": {
            "feature_count": int(x_train.shape[1]),
            "rank": int(model.rank_),
            "singular_values": [float(value) for value in model.singular_],
        },
        "duplicated_design": {
            "feature_count": int(duplicate_train.shape[1]),
            "rank": int(duplicated_model.rank_),
            "singular_values": [
                float(value) for value in duplicated_model.singular_
            ],
        },
        "base_token_coefficient": float(model.coef_[0]),
        "duplicated_token_coefficients": {
            "token_count": float(duplicated_model.coef_[0]),
            "token_count_duplicate": float(duplicated_model.coef_[-1]),
        },
        "duplicated_token_coefficient_sum": duplicate_coefficient_sum,
        "prediction_max_abs_delta": float(prediction_delta.max()),
        "predictions_equivalent_within_1e_10": bool(
            np.allclose(
                base_prediction,
                duplicated_prediction,
                rtol=1e-10,
                atol=1e-10,
            )
        ),
    }


def run_regression_control(
    rows: Sequence[WorkloadRow] | None = None,
) -> dict[str, object]:
    """Fit only on training groups, then evaluate a held-out synthetic control."""
    rows = list(rows if rows is not None else make_synthetic_workload())
    train_groups = [f"synthetic-case-{number:02d}" for number in range(8)]
    train, test = split_by_declared_groups(rows, train_groups)

    x_train = _matrix(train)
    y_train = _targets(train)
    x_test = _matrix(test)
    y_test = _targets(test)

    baseline_value = float(np.mean(y_train))
    baseline_prediction = np.full(
        shape=len(test), fill_value=baseline_value, dtype=float
    )

    model = LinearRegression()
    model.fit(x_train, y_train)
    prediction = model.predict(x_test)
    residuals = y_test - prediction

    outlier_targets = y_test.copy()
    outlier_targets[0] += 60.0

    train_min = x_train.min(axis=0)
    train_max = x_train.max(axis=0)
    probe = np.asarray(
        [[float(train_max[0] + 240.0), float(train_max[1]), float(train_max[2])]]
    )
    probe_outside = bool(
        np.any((probe[0] < train_min) | (probe[0] > train_max))
    )

    return {
        "evidence_scope": "deterministic Tier C synthetic regression control",
        "feature_names": list(FEATURE_NAMES),
        "train_record_ids": [row.record_id for row in train],
        "test_record_ids": [row.record_id for row in test],
        "train_group_ids": sorted({row.group_id for row in train}),
        "test_group_ids": sorted({row.group_id for row in test}),
        "group_overlap": sorted(
            {row.group_id for row in train} & {row.group_id for row in test}
        ),
        "baseline": {
            "training_mean": baseline_value,
            "test_metrics": regression_metrics(
                y_test.tolist(), baseline_prediction.tolist()
            ),
        },
        "ols": {
            "intercept": float(model.intercept_),
            "coefficients": {
                name: float(value)
                for name, value in zip(FEATURE_NAMES, model.coef_, strict=True)
            },
            "test_metrics": regression_metrics(
                y_test.tolist(), prediction.tolist()
            ),
            "predictions": prediction.tolist(),
            "actual": y_test.tolist(),
            "residuals": residuals.tolist(),
        },
        "outlier_failure_injection": {
            "added_minutes_to_first_test_target": 60.0,
            "clean_metrics": regression_metrics(
                y_test.tolist(), prediction.tolist()
            ),
            "outlier_metrics": regression_metrics(
                outlier_targets.tolist(), prediction.tolist()
            ),
        },
        "extrapolation_probe": {
            "features": {
                name: float(value)
                for name, value in zip(FEATURE_NAMES, probe[0], strict=True)
            },
            "outside_observed_training_range": probe_outside,
            "prediction": float(model.predict(probe)[0]),
            "label_available": False,
        },
        "rank_deficiency_probe": _rank_deficiency_probe(
            model,
            x_train,
            y_train,
            x_test,
        ),
    }


def write_artifacts(report: dict[str, object], output_dir: Path) -> None:
    """Write a machine-readable report and two deterministic diagnostic plots."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "chapter-06-regression-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ols = report["ols"]
    actual = np.asarray(ols["actual"], dtype=float)
    prediction = np.asarray(ols["predictions"], dtype=float)
    residuals = np.asarray(ols["residuals"], dtype=float)

    figure, axis = plt.subplots()
    axis.scatter(actual, prediction)
    low = float(min(actual.min(), prediction.min()))
    high = float(max(actual.max(), prediction.max()))
    axis.plot([low, high], [low, high])
    axis.set_xlabel("Actual review minutes (synthetic)")
    axis.set_ylabel("Predicted review minutes")
    axis.set_title("Chapter 6 synthetic regression control")
    figure.tight_layout()
    figure.savefig(output_dir / "chapter-06-predicted-vs-actual.svg")
    plt.close(figure)

    figure, axis = plt.subplots()
    axis.scatter(prediction, residuals)
    axis.axhline(0.0)
    axis.set_xlabel("Predicted review minutes")
    axis.set_ylabel("Residual: actual - predicted")
    axis.set_title("Residual audit on held-out synthetic groups")
    figure.tight_layout()
    figure.savefig(output_dir / "chapter-06-residuals.svg")
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path, default=Path("artifacts/chapter06")
    )
    args = parser.parse_args()
    report = run_regression_control()
    write_artifacts(report, args.output_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
