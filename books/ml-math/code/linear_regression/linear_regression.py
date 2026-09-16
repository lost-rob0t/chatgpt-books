"""From-first-principles simple affine regression for the ML-Math book.

The implementation deliberately covers one real-valued feature and one real-valued
target. It exists to make the objective, gradient, update rule, stopping condition,
and evaluation boundary inspectable before the book moves to more general models.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import fsum, hypot, isfinite
from numbers import Real
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Model:
    weight: float
    bias: float


@dataclass(frozen=True)
class FitStep:
    step: int
    weight: float
    bias: float
    loss: float
    gradient_norm: float


@dataclass(frozen=True)
class FitResult:
    model: Model
    loss: float
    steps: int
    converged: bool
    history: tuple[FitStep, ...]


def _finite_real(value: Real, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError(f"{name} must fit a finite float") from error
    if not isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _series(values: Iterable[Real], *, name: str) -> tuple[float, ...]:
    result = tuple(_finite_real(value, name=f"{name} value") for value in values)
    if not result:
        raise ValueError(f"{name} must contain at least one value")
    return result


def _data(
    features: Sequence[Real], targets: Sequence[Real]
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    xs = _series(features, name="features")
    ys = _series(targets, name="targets")
    if len(xs) != len(ys):
        raise ValueError("features and targets must have the same length")
    return xs, ys


def _finite_result(value: float, *, name: str) -> float:
    if not isfinite(value):
        raise ValueError(f"{name} became non-finite")
    return value


def predict(model: Model, features: Sequence[Real]) -> tuple[float, ...]:
    weight = _finite_real(model.weight, name="model weight")
    bias = _finite_real(model.bias, name="model bias")
    xs = _series(features, name="features")
    return tuple(
        _finite_result(weight * x + bias, name="prediction")
        for x in xs
    )


def residuals(
    model: Model, features: Sequence[Real], targets: Sequence[Real]
) -> tuple[float, ...]:
    xs, ys = _data(features, targets)
    predictions = predict(model, xs)
    return tuple(
        _finite_result(prediction - target, name="residual")
        for prediction, target in zip(predictions, ys, strict=True)
    )


def mean_squared_error(
    model: Model, features: Sequence[Real], targets: Sequence[Real]
) -> float:
    errors = residuals(model, features, targets)
    squares = tuple(
        _finite_result(error * error, name="squared residual")
        for error in errors
    )
    return _finite_result(fsum(squares) / len(squares), name="mean squared error")


def mse_gradient(
    model: Model, features: Sequence[Real], targets: Sequence[Real]
) -> tuple[float, float]:
    xs, ys = _data(features, targets)
    errors = residuals(model, xs, ys)
    scale = 2.0 / len(xs)
    d_weight = scale * fsum(error * x for error, x in zip(errors, xs, strict=True))
    d_bias = scale * fsum(errors)
    return (
        _finite_result(d_weight, name="weight derivative"),
        _finite_result(d_bias, name="bias derivative"),
    )


def fit_centered_closed_form(
    features: Sequence[Real], targets: Sequence[Real]
) -> Model:
    """Return the unique simple affine least-squares fit when feature spread is non-zero."""

    xs, ys = _data(features, targets)
    if len(xs) < 2:
        raise ValueError("closed-form affine fitting requires at least two samples")
    x_mean = _finite_result(fsum(xs) / len(xs), name="feature mean")
    y_mean = _finite_result(fsum(ys) / len(ys), name="target mean")
    centered_x = tuple(x - x_mean for x in xs)
    centered_y = tuple(y - y_mean for y in ys)
    denominator = _finite_result(
        fsum(dx * dx for dx in centered_x), name="centered feature square sum"
    )
    if denominator == 0.0:
        raise ValueError("features must not all be identical")
    numerator = _finite_result(
        fsum(dx * dy for dx, dy in zip(centered_x, centered_y, strict=True)),
        name="centered feature-target product sum",
    )
    weight = _finite_result(numerator / denominator, name="closed-form weight")
    bias = _finite_result(y_mean - weight * x_mean, name="closed-form bias")
    return Model(weight=weight, bias=bias)


def fit_batch_gradient_descent(
    features: Sequence[Real],
    targets: Sequence[Real],
    *,
    learning_rate: Real,
    max_steps: int = 1000,
    gradient_tolerance: Real = 1e-9,
    initial_model: Model = Model(0.0, 0.0),
) -> FitResult:
    """Fit by full-batch gradient descent and retain an auditable optimization trace."""

    xs, ys = _data(features, targets)
    rate = _finite_real(learning_rate, name="learning rate")
    if rate <= 0.0:
        raise ValueError("learning rate must be positive")
    tolerance = _finite_real(gradient_tolerance, name="gradient tolerance")
    if tolerance < 0.0:
        raise ValueError("gradient tolerance must be non-negative")
    if isinstance(max_steps, bool) or not isinstance(max_steps, int):
        raise TypeError("max_steps must be an integer")
    if max_steps < 0:
        raise ValueError("max_steps must be non-negative")

    model = Model(
        _finite_real(initial_model.weight, name="initial weight"),
        _finite_real(initial_model.bias, name="initial bias"),
    )
    history: list[FitStep] = []

    for step in range(max_steps + 1):
        loss = mean_squared_error(model, xs, ys)
        d_weight, d_bias = mse_gradient(model, xs, ys)
        gradient_norm = _finite_result(
            hypot(d_weight, d_bias), name="gradient norm"
        )
        history.append(
            FitStep(
                step=step,
                weight=model.weight,
                bias=model.bias,
                loss=loss,
                gradient_norm=gradient_norm,
            )
        )
        if gradient_norm <= tolerance:
            return FitResult(
                model=model,
                loss=loss,
                steps=step,
                converged=True,
                history=tuple(history),
            )
        if step == max_steps:
            break
        model = Model(
            _finite_result(
                model.weight - rate * d_weight, name="updated weight"
            ),
            _finite_result(model.bias - rate * d_bias, name="updated bias"),
        )

    return FitResult(
        model=model,
        loss=history[-1].loss,
        steps=max_steps,
        converged=False,
        history=tuple(history),
    )
