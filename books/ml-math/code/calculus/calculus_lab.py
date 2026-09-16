"""Small finite-difference calculus lab for the ML-Math book.

The implementation is intentionally narrow: finite real scalars, finite points,
explicit step sizes, and scalar-valued functions. It is a teaching aid, not a
general automatic-differentiation or numerical-analysis package.
"""

from __future__ import annotations

from math import fsum, hypot, isfinite
from numbers import Real
from typing import Callable, Iterable, Sequence

ScalarFunction = Callable[[float], float]
PointFunction = Callable[[tuple[float, ...]], float]


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


def point(values: Iterable[Real]) -> tuple[float, ...]:
    result = tuple(_finite_real(value, name="point component") for value in values)
    if not result:
        raise ValueError("point must contain at least one component")
    return result


def _step(value: Real) -> float:
    result = _finite_real(value, name="step")
    if result <= 0.0:
        raise ValueError("step must be positive")
    return result


def _finite_output(value: Real, *, name: str = "function output") -> float:
    return _finite_real(value, name=name)


def forward_difference(function: ScalarFunction, x: Real, *, step: Real = 1e-6) -> float:
    x0 = _finite_real(x, name="x")
    h = _step(step)
    x1 = _finite_real(x0 + h, name="displaced x")
    if x1 == x0:
        raise ValueError("step is too small to change x at this floating-point scale")
    y0 = _finite_output(function(x0))
    y1 = _finite_output(function(x1))
    return _finite_output((y1 - y0) / h, name="difference quotient")


def central_difference(function: ScalarFunction, x: Real, *, step: Real = 1e-5) -> float:
    x0 = _finite_real(x, name="x")
    h = _step(step)
    left_x = _finite_real(x0 - h, name="left sample x")
    right_x = _finite_real(x0 + h, name="right sample x")
    if left_x == x0 or right_x == x0:
        raise ValueError("step is too small to move both sample points")
    denominator = _finite_output(2.0 * h, name="central-difference denominator")
    left = _finite_output(function(left_x))
    right = _finite_output(function(right_x))
    return _finite_output((right - left) / denominator, name="central difference")


def partial_difference(
    function: PointFunction,
    at: Sequence[Real],
    axis: int,
    *,
    step: Real = 1e-5,
) -> float:
    base = point(at)
    if not isinstance(axis, int) or isinstance(axis, bool):
        raise TypeError("axis must be an integer")
    if axis < 0 or axis >= len(base):
        raise IndexError("axis is outside the point dimension")
    h = _step(step)

    left = list(base)
    right = list(base)
    left[axis] = _finite_real(left[axis] - h, name="left sample component")
    right[axis] = _finite_real(right[axis] + h, name="right sample component")
    if left[axis] == base[axis] or right[axis] == base[axis]:
        raise ValueError("step is too small to move both samples on the selected axis")
    denominator = _finite_output(2.0 * h, name="partial-difference denominator")

    left_value = _finite_output(function(tuple(left)))
    right_value = _finite_output(function(tuple(right)))
    return _finite_output(
        (right_value - left_value) / denominator,
        name="partial difference",
    )


def numerical_gradient(
    function: PointFunction,
    at: Sequence[Real],
    *,
    step: Real = 1e-5,
) -> tuple[float, ...]:
    base = point(at)
    return tuple(partial_difference(function, base, axis, step=step) for axis in range(len(base)))


def directional_derivative_from_gradient(
    gradient: Sequence[Real],
    direction: Sequence[Real],
) -> float:
    grad = point(gradient)
    direction_vector = point(direction)
    if len(grad) != len(direction_vector):
        raise ValueError("gradient and direction must have the same dimension")
    magnitude = hypot(*direction_vector)
    if not isfinite(magnitude):
        raise ValueError("direction magnitude must be finite")
    if magnitude == 0.0:
        raise ValueError("direction must be non-zero")
    unit = tuple(component / magnitude for component in direction_vector)
    return _finite_output(
        fsum(g * u for g, u in zip(grad, unit, strict=True)),
        name="directional derivative",
    )


def affine_mse(
    parameters: Sequence[Real],
    features: Sequence[Real],
    targets: Sequence[Real],
) -> float:
    params = point(parameters)
    if len(params) != 2:
        raise ValueError("parameters must be (weight, bias)")
    xs = point(features)
    ys = point(targets)
    if len(xs) != len(ys):
        raise ValueError("features and targets must have the same length")
    weight, bias = params
    residual_squares = []
    for x, y in zip(xs, ys, strict=True):
        residual = _finite_output(weight * x + bias - y, name="residual")
        residual_squares.append(_finite_output(residual * residual, name="squared residual"))
    return _finite_output(fsum(residual_squares) / len(xs), name="mean squared error")


def affine_mse_gradient(
    parameters: Sequence[Real],
    features: Sequence[Real],
    targets: Sequence[Real],
) -> tuple[float, float]:
    params = point(parameters)
    if len(params) != 2:
        raise ValueError("parameters must be (weight, bias)")
    xs = point(features)
    ys = point(targets)
    if len(xs) != len(ys):
        raise ValueError("features and targets must have the same length")
    weight, bias = params
    residuals = tuple(
        _finite_output(weight * x + bias - y, name="residual")
        for x, y in zip(xs, ys, strict=True)
    )
    scale = 2.0 / len(xs)
    weighted_residuals = tuple(
        _finite_output(residual * x, name="weighted residual")
        for residual, x in zip(residuals, xs, strict=True)
    )
    d_weight = scale * fsum(weighted_residuals)
    d_bias = scale * fsum(residuals)
    return (
        _finite_output(d_weight, name="weight derivative"),
        _finite_output(d_bias, name="bias derivative"),
    )
