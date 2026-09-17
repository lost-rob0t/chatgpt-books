"""Generate the deterministic Project 3 gradient-descent regimes figure."""

from __future__ import annotations

from math import sqrt
from pathlib import Path

from gradient_descent import (
    Quadratic1D,
    Quadratic2D,
    trace_quadratic_1d,
    trace_quadratic_2d,
)

WIDTH = 980
HEIGHT = 500

LEFT_X0, LEFT_X1 = 70.0, 450.0
RIGHT_X0, RIGHT_X1 = 545.0, 930.0
TOP, BOTTOM = 55.0, 390.0


def scalar_x(step: int, total_steps: int) -> float:
    return LEFT_X0 + (step / total_steps) * (LEFT_X1 - LEFT_X0)


def scalar_y(error: float) -> float:
    return BOTTOM - ((error + 5.0) / 10.0) * (BOTTOM - TOP)


def plane_x(x: float) -> float:
    return RIGHT_X0 + ((x + 5.0) / 10.0) * (RIGHT_X1 - RIGHT_X0)


def plane_y(y: float) -> float:
    return BOTTOM - ((y + 9.0) / 18.0) * (BOTTOM - TOP)


def polyline(points: list[tuple[float, float]], *, dash: str = "") -> str:
    coords = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<polyline points="{coords}" fill="none" stroke="#111" '
        f'stroke-width="2.5"{dash_attr}/>'
    )


def scalar_markers(trace, *, shape: str) -> str:
    items = []
    for point in trace:
        x = scalar_x(point.step, trace[-1].step)
        y = scalar_y(point.error)
        if shape == "circle":
            items.append(
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.8" fill="#111"/>'
            )
        elif shape == "square":
            items.append(
                f'<rect x="{x-3.8:.2f}" y="{y-3.8:.2f}" width="7.6" '
                f'height="7.6" fill="white" stroke="#111" stroke-width="1.7"/>'
            )
        else:
            items.append(
                f'<path d="M {x:.2f} {y-4.5:.2f} L {x+4.5:.2f} {y+4.5:.2f} '
                f'M {x+4.5:.2f} {y-4.5:.2f} L {x-4.5:.2f} {y+4.5:.2f}" '
                f'stroke="#111" stroke-width="1.7"/>'
            )
    return "\n".join(items)


def ellipse(cx: float, cy: float, radius: float, *, dash: str) -> str:
    rx = plane_x(radius) - plane_x(0.0)
    ry = plane_y(0.0) - plane_y(radius / sqrt(10.0))
    return (
        f'<ellipse cx="{cx:.2f}" cy="{cy:.2f}" rx="{rx:.2f}" ry="{ry:.2f}" '
        f'fill="none" stroke="#999" stroke-width="1.2" stroke-dasharray="{dash}"/>'
    )


def main() -> None:
    scalar_objective = Quadratic1D(curvature=2.0)
    scalar_runs = (
        (0.25, "", "circle"),
        (0.75, "9 5", "square"),
        (1.10, "2 5", "cross"),
    )
    scalar_fragments: list[str] = []
    for rate, dash, shape in scalar_runs:
        trace = trace_quadratic_1d(
            scalar_objective,
            initial_parameter=1.0,
            learning_rate=rate,
            steps=8,
        )
        points = [(scalar_x(point.step, 8), scalar_y(point.error)) for point in trace]
        scalar_fragments.append(polyline(points, dash=dash))
        scalar_fragments.append(scalar_markers(trace, shape=shape))

    bowl = Quadratic2D(curvature_x=1.0, curvature_y=10.0)
    stable = trace_quadratic_2d(
        bowl,
        initial_x=4.0,
        initial_y=4.0,
        learning_rate=0.18,
        steps=12,
    )
    unstable = trace_quadratic_2d(
        bowl,
        initial_x=4.0,
        initial_y=4.0,
        learning_rate=0.22,
        steps=4,
    )
    stable_points = [(plane_x(point.x), plane_y(point.y)) for point in stable]
    unstable_points = [(plane_x(point.x), plane_y(point.y)) for point in unstable]

    cx = plane_x(0.0)
    cy = plane_y(0.0)
    contours = "\n".join(
        (
            ellipse(cx, cy, 1.4, dash="2 4"),
            ellipse(cx, cy, 2.6, dash="5 4"),
            ellipse(cx, cy, 4.2, dash="9 5"),
        )
    )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
<title>Gradient descent stability regimes on scalar and axis-aligned quadratic objectives</title>
<desc>The left panel plots normalized scalar parameter error for three fixed learning rates on the same positive-curvature quadratic. A solid line with filled circles approaches zero without crossing it, a long-dashed line with open squares crosses zero while shrinking, and a short-dashed line with cross markers grows while alternating. The right panel shows elliptical level curves of an axis-aligned quadratic. A solid path zigzags toward the minimum when both coordinate multipliers have magnitude below one, while a dashed path grows away because the high-curvature coordinate multiplier has magnitude above one.</desc>
<rect width="100%" height="100%" fill="white"/>

<text x="{(LEFT_X0+LEFT_X1)/2:.2f}" y="27" text-anchor="middle" font-size="18" font-weight="bold">one-dimensional error recurrence</text>
<line x1="{LEFT_X0}" y1="{scalar_y(0.0):.2f}" x2="{LEFT_X1}" y2="{scalar_y(0.0):.2f}" stroke="#777" stroke-width="1"/>
<line x1="{LEFT_X0}" y1="{TOP}" x2="{LEFT_X0}" y2="{BOTTOM}" stroke="#111"/>
<line x1="{LEFT_X0}" y1="{BOTTOM}" x2="{LEFT_X1}" y2="{BOTTOM}" stroke="#111"/>
{"".join(scalar_fragments)}
<text x="{LEFT_X0}" y="414" font-size="13">solid + circles: eta*a=0.5, monotone convergence</text>
<text x="{LEFT_X0}" y="433" font-size="13">long dash + squares: eta*a=1.5, oscillatory convergence</text>
<text x="{LEFT_X0}" y="452" font-size="13">short dash + crosses: eta*a=2.2, divergence</text>
<text x="{LEFT_X0}" y="477" font-size="12">horizontal axis: update step 0-8; vertical center line: error = 0</text>

<text x="{(RIGHT_X0+RIGHT_X1)/2:.2f}" y="27" text-anchor="middle" font-size="18" font-weight="bold">different curvature, different coordinate behavior</text>
<line x1="{RIGHT_X0}" y1="{plane_y(0.0):.2f}" x2="{RIGHT_X1}" y2="{plane_y(0.0):.2f}" stroke="#aaa" stroke-width="1"/>
<line x1="{plane_x(0.0):.2f}" y1="{TOP}" x2="{plane_x(0.0):.2f}" y2="{BOTTOM}" stroke="#aaa" stroke-width="1"/>
{contours}
{polyline(stable_points)}
{polyline(unstable_points, dash="8 5")}
<circle cx="{stable_points[0][0]:.2f}" cy="{stable_points[0][1]:.2f}" r="5" fill="white" stroke="#111" stroke-width="2"/>
<circle cx="{cx:.2f}" cy="{cy:.2f}" r="4.5" fill="#111"/>
<text x="{RIGHT_X0}" y="414" font-size="13">solid: eta=0.18 =&gt; multipliers 0.82 and -0.80</text>
<text x="{RIGHT_X0}" y="433" font-size="13">dashed: eta=0.22 =&gt; multipliers 0.78 and -1.20</text>
<text x="{RIGHT_X0}" y="452" font-size="13">same update rule; the steeper y direction sets the failure</text>
<text x="{RIGHT_X0}" y="477" font-size="12">bowl: q(x,y)=0.5x^2+5y^2; filled point is the minimum</text>
</svg>
"""
    output = Path(__file__).resolve().parents[2] / "assets" / "gradient_descent_regimes.svg"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
