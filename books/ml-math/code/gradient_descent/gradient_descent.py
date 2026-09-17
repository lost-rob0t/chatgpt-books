"""From-first-principles fixed-step gradient descent for the ML-Math book.

This module intentionally studies positive-curvature scalar and axis-aligned
quadratic objectives. Those objectives are simple enough that every update can
be checked against an exact recurrence before the book introduces general
Hessians, eigenvalues, line searches, or adaptive optimizers.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Real


@dataclass(frozen=True)
class Quadratic1D:
    curvature: float
    center: float = 0.0
    minimum: float = 0.0


@dataclass(frozen=True)
class TracePoint1D:
    step: int
    parameter: float
    error: float
    loss: float
    gradient: float


@dataclass(frozen=True)
class Quadratic2D:
    curvature_x: float
    curvature_y: float
    center_x: float = 0.0
    center_y: float = 0.0
    minimum: float = 0.0


@dataclass(frozen=True)
class TracePoint2D:
    step: int
    x: float
    y: float
    error_x: float
    error_y: float
    loss: float
    gradient_x: float
    gradient_y: float


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


def _positive_curvature(value: Real, *, name: str) -> float:
    result = _finite_real(value, name=name)
    if result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result


def _positive_rate(value: Real) -> float:
    result = _finite_real(value, name="learning rate")
    if result <= 0.0:
        raise ValueError("learning rate must be positive")
    return result


def _step_count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("steps must be an integer")
    if value < 0:
        raise ValueError("steps must be non-negative")
    return value


def _finite_result(value: float, *, name: str) -> float:
    if not isfinite(value):
        raise ValueError(f"{name} became non-finite")
    return value


def _quadratic1d_values(objective: Quadratic1D) -> tuple[float, float, float]:
    return (
        _positive_curvature(objective.curvature, name="curvature"),
        _finite_real(objective.center, name="center"),
        _finite_real(objective.minimum, name="minimum"),
    )


def quadratic_value(objective: Quadratic1D, parameter: Real) -> float:
    curvature, center, minimum = _quadratic1d_values(objective)
    theta = _finite_real(parameter, name="parameter")
    error = _finite_result(theta - center, name="parameter error")
    square = _finite_result(error * error, name="squared parameter error")
    return _finite_result(
        minimum + 0.5 * curvature * square,
        name="quadratic value",
    )


def quadratic_gradient(objective: Quadratic1D, parameter: Real) -> float:
    curvature, center, _ = _quadratic1d_values(objective)
    theta = _finite_real(parameter, name="parameter")
    error = _finite_result(theta - center, name="parameter error")
    return _finite_result(curvature * error, name="quadratic gradient")


def error_multiplier(curvature: Real, learning_rate: Real) -> float:
    a = _positive_curvature(curvature, name="curvature")
    rate = _positive_rate(learning_rate)
    return _finite_result(1.0 - rate * a, name="error multiplier")


def classify_scalar_step(curvature: Real, learning_rate: Real) -> str:
    """Classify the exact recurrence for a positive-curvature scalar quadratic."""

    multiplier = error_multiplier(curvature, learning_rate)
    if multiplier == 0.0:
        return "one-step"
    if 0.0 < multiplier < 1.0:
        return "monotone-convergent"
    if -1.0 < multiplier < 0.0:
        return "oscillatory-convergent"
    if abs(multiplier) == 1.0:
        return "neutral"
    return "divergent"


def closed_form_parameter(
    objective: Quadratic1D,
    initial_parameter: Real,
    learning_rate: Real,
    step: int,
) -> float:
    """Return theta_k from the exact scalar error recurrence."""

    _, center, _ = _quadratic1d_values(objective)
    theta0 = _finite_real(initial_parameter, name="initial parameter")
    k = _step_count(step)
    multiplier = error_multiplier(objective.curvature, learning_rate)
    initial_error = _finite_result(theta0 - center, name="initial parameter error")
    error = _finite_result(
        (multiplier**k) * initial_error,
        name="closed-form parameter error",
    )
    return _finite_result(center + error, name="closed-form parameter")


def trace_quadratic_1d(
    objective: Quadratic1D,
    *,
    initial_parameter: Real,
    learning_rate: Real,
    steps: int,
) -> tuple[TracePoint1D, ...]:
    """Run fixed-step gradient descent and retain every scalar state."""

    _, center, _ = _quadratic1d_values(objective)
    parameter = _finite_real(initial_parameter, name="initial parameter")
    rate = _positive_rate(learning_rate)
    count = _step_count(steps)
    trace: list[TracePoint1D] = []

    for step in range(count + 1):
        error = _finite_result(parameter - center, name="parameter error")
        gradient = quadratic_gradient(objective, parameter)
        loss = quadratic_value(objective, parameter)
        trace.append(
            TracePoint1D(
                step=step,
                parameter=parameter,
                error=error,
                loss=loss,
                gradient=gradient,
            )
        )
        if step == count:
            break
        parameter = _finite_result(
            parameter - rate * gradient,
            name="updated parameter",
        )

    return tuple(trace)


def _quadratic2d_values(
    objective: Quadratic2D,
) -> tuple[float, float, float, float, float]:
    return (
        _positive_curvature(objective.curvature_x, name="x curvature"),
        _positive_curvature(objective.curvature_y, name="y curvature"),
        _finite_real(objective.center_x, name="x center"),
        _finite_real(objective.center_y, name="y center"),
        _finite_real(objective.minimum, name="minimum"),
    )


def quadratic2d_value(objective: Quadratic2D, x: Real, y: Real) -> float:
    ax, ay, cx, cy, minimum = _quadratic2d_values(objective)
    px = _finite_real(x, name="x")
    py = _finite_real(y, name="y")
    ex = _finite_result(px - cx, name="x error")
    ey = _finite_result(py - cy, name="y error")
    x_square = _finite_result(ex * ex, name="squared x error")
    y_square = _finite_result(ey * ey, name="squared y error")
    return _finite_result(
        minimum + 0.5 * ax * x_square + 0.5 * ay * y_square,
        name="quadratic value",
    )


def quadratic2d_gradient(
    objective: Quadratic2D,
    x: Real,
    y: Real,
) -> tuple[float, float]:
    ax, ay, cx, cy, _ = _quadratic2d_values(objective)
    px = _finite_real(x, name="x")
    py = _finite_real(y, name="y")
    return (
        _finite_result(ax * (px - cx), name="x gradient"),
        _finite_result(ay * (py - cy), name="y gradient"),
    )


def trace_quadratic_2d(
    objective: Quadratic2D,
    *,
    initial_x: Real,
    initial_y: Real,
    learning_rate: Real,
    steps: int,
) -> tuple[TracePoint2D, ...]:
    """Run fixed-step gradient descent on an axis-aligned quadratic bowl."""

    _, _, cx, cy, _ = _quadratic2d_values(objective)
    x = _finite_real(initial_x, name="initial x")
    y = _finite_real(initial_y, name="initial y")
    rate = _positive_rate(learning_rate)
    count = _step_count(steps)
    trace: list[TracePoint2D] = []

    for step in range(count + 1):
        ex = _finite_result(x - cx, name="x error")
        ey = _finite_result(y - cy, name="y error")
        gx, gy = quadratic2d_gradient(objective, x, y)
        loss = quadratic2d_value(objective, x, y)
        trace.append(
            TracePoint2D(
                step=step,
                x=x,
                y=y,
                error_x=ex,
                error_y=ey,
                loss=loss,
                gradient_x=gx,
                gradient_y=gy,
            )
        )
        if step == count:
            break
        x = _finite_result(x - rate * gx, name="updated x")
        y = _finite_result(y - rate * gy, name="updated y")

    return tuple(trace)
