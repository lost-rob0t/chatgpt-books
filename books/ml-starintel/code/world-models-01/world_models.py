"""Deterministic, synthetic predictive-state exercise for World Models I.

Standard library only. Parameters are FIXED controls, not fitted estimates;
this module neither ingests real StarIntel records nor defines wire authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, log2
from typing import Mapping, Sequence


VERSION = "0.10.1"
DATASET = "world-model-synthetic"
WINDOW_SECONDS = 60
STATES = ("quiet", "busy")
BUCKETS = ("low", "high")


def _prob_row(row: Sequence[float], width: int) -> tuple[float, ...]:
    if len(row) != width:
        raise ValueError("incorrect probability row width")
    values = tuple(float(value) for value in row)
    if any(not isfinite(x) or x < 0.0 or x > 1.0 for x in values):
        raise ValueError("probabilities must be finite and within [0, 1]")
    if abs(sum(values) - 1.0) > 1e-12:
        raise ValueError("probability row must sum to one")
    return values


@dataclass(frozen=True)
class WindowObservation:
    window_start: int
    count: int
    bucket: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class FilterStep:
    window_start: int
    observation: str
    predicted_state: tuple[float, float]
    observation_probability: float
    posterior_state: tuple[float, float]
    next_high_probability: float
    posterior_entropy_bits: float


@dataclass(frozen=True)
class BinaryWorldModel:
    prior: tuple[float, float] = (0.60, 0.40)
    transition: tuple[tuple[float, float], tuple[float, float]] = (
        (0.85, 0.15),
        (0.25, 0.75),
    )
    emission: tuple[tuple[float, float], tuple[float, float]] = (
        (0.80, 0.20),
        (0.30, 0.70),
    )

    def __post_init__(self) -> None:
        _prob_row(self.prior, 2)
        for row in self.transition + self.emission:
            _prob_row(row, 2)

    def predict_state(self, posterior: Sequence[float]) -> tuple[float, float]:
        quiet, busy = _prob_row(posterior, 2)
        return (
            quiet * self.transition[0][0] + busy * self.transition[1][0],
            quiet * self.transition[0][1] + busy * self.transition[1][1],
        )

    def observation_probability(self, predicted: Sequence[float], bucket: str) -> float:
        if bucket not in BUCKETS:
            raise ValueError(f"unknown observation bucket: {bucket!r}")
        p = _prob_row(predicted, 2)
        column = BUCKETS.index(bucket)
        return sum(p[state] * self.emission[state][column] for state in range(2))

    def update(self, predicted: Sequence[float], bucket: str) -> tuple[tuple[float, float], float]:
        likelihood = self.observation_probability(predicted, bucket)
        if likelihood <= 0.0:
            raise ValueError("observation has zero likelihood under model")
        column = BUCKETS.index(bucket)
        posterior = tuple(
            float(predicted[state]) * self.emission[state][column] / likelihood
            for state in range(2)
        )
        return (posterior[0], posterior[1]), likelihood

    def next_high_probability(self, posterior: Sequence[float]) -> float:
        return self.observation_probability(self.predict_state(posterior), "high")

    def rollout_high(self, posterior: Sequence[float], horizon: int) -> tuple[float, ...]:
        if type(horizon) is not int or horizon < 0:
            raise ValueError("horizon must be a nonnegative integer")
        predicted = _prob_row(posterior, 2)
        forecast = []
        for _ in range(horizon):
            predicted = self.predict_state(predicted)
            forecast.append(self.observation_probability(predicted, "high"))
        return tuple(forecast)

    def filter(self, observations: Sequence[WindowObservation]) -> tuple[FilterStep, ...]:
        predicted = _prob_row(self.prior, 2)
        steps: list[FilterStep] = []
        previous_window = None
        for observation in observations:
            if observation.bucket not in BUCKETS:
                raise ValueError("invalid observation bucket")
            if previous_window is not None:
                if observation.window_start != previous_window + WINDOW_SECONDS:
                    raise ValueError("observations must be contiguous chronological windows")
            posterior, evidence = self.update(predicted, observation.bucket)
            steps.append(FilterStep(
                window_start=observation.window_start,
                observation=observation.bucket,
                predicted_state=(predicted[0], predicted[1]),
                observation_probability=evidence,
                posterior_state=posterior,
                next_high_probability=self.next_high_probability(posterior),
                posterior_entropy_bits=entropy_bits(posterior),
            ))
            predicted = self.predict_state(posterior)
            previous_window = observation.window_start
        return tuple(steps)


def entropy_bits(state: Sequence[float]) -> float:
    values = _prob_row(state, 2)
    return -sum(p * log2(p) for p in values if p > 0.0)


def aggregate_synthetic_events(
    documents: Sequence[Mapping[str, object]],
    *,
    start: int,
    windows: int,
    high_at: int = 2,
) -> tuple[WindowObservation, ...]:
    """Map synthetic 0.10.1-shaped event documents to sealed count windows.

    Caller explicitly asserts that every requested window is COMPLETE.
    A missing event alone is never proof of an observed zero in production.
    This is a feature adapter, not a replacement for the canonical validator.
    """
    if type(start) is not int or start % WINDOW_SECONDS:
        raise ValueError("start must be an aligned integer Unix second")
    if type(windows) is not int or windows <= 0:
        raise ValueError("windows must be a positive integer")
    if type(high_at) is not int or high_at <= 0:
        raise ValueError("high_at must be positive")
    slots: list[list[str]] = [[] for _ in range(windows)]
    seen = set()
    for document in documents:
        if not isinstance(document, Mapping):
            raise ValueError("an event must be a mapping")
        if document.get("dataset") != DATASET or document.get("schemaVersion") != VERSION:
            raise ValueError("wrong synthetic dataset or schema version")
        if document.get("dtype") != "event":
            raise ValueError("expected event document")
        identifier = document.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValueError("event id must be nonempty and unique")
        seen.add(identifier)
        timestamp = document.get("observedAt")
        if type(timestamp) is not int or not start <= timestamp < start + windows * WINDOW_SECONDS:
            raise ValueError("event observedAt outside declared sealed windows")
        slots[(timestamp - start) // WINDOW_SECONDS].append(identifier)
    return tuple(
        WindowObservation(
            window_start=start + i * WINDOW_SECONDS,
            count=len(ids),
            bucket="high" if len(ids) >= high_at else "low",
            source_ids=tuple(sorted(ids)),
        )
        for i, ids in enumerate(slots)
    )


def synthetic_documents(start: int = 1_700_000_040) -> tuple[dict[str, object], ...]:
    """Six invented events across four complete windows: [0, 2, 3, 1]."""
    document_offsets = (65, 75, 125, 135, 145, 185)
    return tuple({
        "id": f"synthetic:event:{index:03d}",
        "dataset": DATASET,
        "dtype": "event",
        "schemaVersion": VERSION,
        "observedAt": start + offset,
        "eventKind": "synthetic-signal",
    } for index, offset in enumerate(document_offsets))


def run_fixture() -> tuple[tuple[WindowObservation, ...], tuple[FilterStep, ...]]:
    observations = aggregate_synthetic_events(
        synthetic_documents(), start=1_700_000_040, windows=4
    )
    return observations, BinaryWorldModel().filter(observations)


if __name__ == "__main__":
    observations, trace = run_fixture()
    for window, step in zip(observations, trace, strict=True):
        print(f"t={window.window_start} count={window.count} y={window.bucket} "
              f"P(busy|data)={step.posterior_state[1]:.6f} "
              f"P(next_high|data)={step.next_high_probability:.6f} "
              f"H={step.posterior_entropy_bits:.6f}bits")
