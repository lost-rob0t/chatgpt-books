"""Generate a deterministic fit/residual/optimization figure for Project 2."""

from __future__ import annotations

from math import log10
from pathlib import Path

from linear_regression import (
    fit_batch_gradient_descent,
    fit_centered_closed_form,
    predict,
)

WIDTH = 920
HEIGHT = 430
LEFT_X0, LEFT_X1 = 55, 430
RIGHT_X0, RIGHT_X1 = 510, 885
TOP, BOTTOM = 45, 365

TRAIN_X = (0.0, 1.0, 2.0, 3.0, 4.0, 5.0)
TRAIN_Y = (1.1, 2.9, 5.2, 6.8, 9.1, 10.9)
EVAL_X = (6.0, 7.0, 8.0)
EVAL_Y = (13.2, 14.8, 17.1)


def left_x(x: float) -> float:
    return LEFT_X0 + (x / 8.0) * (LEFT_X1 - LEFT_X0)


def left_y(y: float) -> float:
    return BOTTOM - (y / 18.0) * (BOTTOM - TOP)


def right_x(step: int, last_step: int) -> float:
    return RIGHT_X0 + (step / last_step) * (RIGHT_X1 - RIGHT_X0)


def right_y(loss: float, min_log: float, max_log: float) -> float:
    value = log10(loss)
    return BOTTOM - ((value - min_log) / (max_log - min_log)) * (BOTTOM - TOP)


def main() -> None:
    closed = fit_centered_closed_form(TRAIN_X, TRAIN_Y)
    fitted = fit_batch_gradient_descent(
        TRAIN_X,
        TRAIN_Y,
        learning_rate=0.05,
        max_steps=2000,
        gradient_tolerance=1e-10,
    )
    if not fitted.converged:
        raise RuntimeError("expected deterministic fixture to converge")

    train_predictions = predict(fitted.model, TRAIN_X)
    fit_at_zero, fit_at_eight = predict(fitted.model, (0.0, 8.0))

    residual_lines = "\n".join(
        f'<line x1="{left_x(x):.2f}" y1="{left_y(y):.2f}" '
        f'x2="{left_x(x):.2f}" y2="{left_y(pred):.2f}" '
        f'stroke="#777" stroke-width="1.5" stroke-dasharray="4 4"/>'
        for x, y, pred in zip(TRAIN_X, TRAIN_Y, train_predictions, strict=True)
    )
    train_points = "\n".join(
        f'<circle cx="{left_x(x):.2f}" cy="{left_y(y):.2f}" r="5" fill="#111"/>'
        for x, y in zip(TRAIN_X, TRAIN_Y, strict=True)
    )
    eval_points = "\n".join(
        f'<rect x="{left_x(x)-5:.2f}" y="{left_y(y)-5:.2f}" width="10" height="10" '
        f'fill="white" stroke="#111" stroke-width="2"/>'
        for x, y in zip(EVAL_X, EVAL_Y, strict=True)
    )

    sampled = list(fitted.history[::10])
    if sampled[-1] != fitted.history[-1]:
        sampled.append(fitted.history[-1])
    losses = [item.loss for item in sampled]
    min_log = log10(min(losses))
    max_log = log10(max(losses))
    trace_points = " ".join(
        f"{right_x(item.step, fitted.steps):.2f},{right_y(item.loss, min_log, max_log):.2f}"
        for item in sampled
    )

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
<title>Project 2 affine regression fit, residuals, and optimization trace</title>
<desc>The left panel shows six training samples, three held-out evaluation samples, a fitted affine line, and dashed training residuals. The right panel shows log base ten mean squared error falling across full-batch gradient-descent steps until the fitted parameters agree closely with the independent centered closed-form solution.</desc>
<rect width="100%" height="100%" fill="white"/>
<text x="{(LEFT_X0+LEFT_X1)/2:.2f}" y="24" text-anchor="middle" font-size="17" font-weight="bold">data, fit, and residuals</text>
<line x1="{LEFT_X0}" y1="{BOTTOM}" x2="{LEFT_X1}" y2="{BOTTOM}" stroke="#111"/>
<line x1="{LEFT_X0}" y1="{TOP}" x2="{LEFT_X0}" y2="{BOTTOM}" stroke="#111"/>
<line x1="{left_x(0):.2f}" y1="{left_y(fit_at_zero):.2f}" x2="{left_x(8):.2f}" y2="{left_y(fit_at_eight):.2f}" stroke="#111" stroke-width="3"/>
{residual_lines}
{train_points}
{eval_points}
<text x="{LEFT_X0}" y="397" font-size="13">filled circle = training; open square = held-out evaluation</text>
<text x="{LEFT_X0}" y="416" font-size="13">dashed vertical segments = training residuals</text>
<text x="{(RIGHT_X0+RIGHT_X1)/2:.2f}" y="24" text-anchor="middle" font-size="17" font-weight="bold">optimization trace</text>
<line x1="{RIGHT_X0}" y1="{BOTTOM}" x2="{RIGHT_X1}" y2="{BOTTOM}" stroke="#111"/>
<line x1="{RIGHT_X0}" y1="{TOP}" x2="{RIGHT_X0}" y2="{BOTTOM}" stroke="#111"/>
<polyline points="{trace_points}" fill="none" stroke="#111" stroke-width="3"/>
<circle cx="{right_x(fitted.steps, fitted.steps):.2f}" cy="{right_y(fitted.loss, min_log, max_log):.2f}" r="5" fill="#111"/>
<text x="{RIGHT_X0}" y="397" font-size="13">x-axis: update step (0 to {fitted.steps})</text>
<text x="{RIGHT_X0}" y="416" font-size="13">y-axis: log10(MSE), higher at top</text>
<text x="{RIGHT_X0+12}" y="{TOP+18}" font-size="13">initial MSE {fitted.history[0].loss:.3f}</text>
<text x="{RIGHT_X0+12}" y="{BOTTOM-12}" font-size="13">final MSE {fitted.loss:.5f}</text>
<text x="{LEFT_X0+12}" y="{TOP+20}" font-size="13">GD: y ~= {fitted.model.weight:.3f}x + {fitted.model.bias:.3f}</text>
<text x="{LEFT_X0+12}" y="{TOP+39}" font-size="13">closed form: y ~= {closed.weight:.3f}x + {closed.bias:.3f}</text>
</svg>
'''
    out = Path(__file__).resolve().parents[2] / "assets" / "linear_regression_fit.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
