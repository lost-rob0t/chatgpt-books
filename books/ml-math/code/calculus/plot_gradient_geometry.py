"""Generate a deterministic gradient geometry teaching figure."""

from __future__ import annotations

from math import cos, pi, sin
from pathlib import Path

from calculus_lab import numerical_gradient

WIDTH = 760
HEIGHT = 500
PAD = 60
X_MIN, X_MAX = -1.5, 3.5
Y_MIN, Y_MAX = -2.5, 2.5


def bowl(point: tuple[float, ...]) -> float:
    x, y = point
    return (x - 1.0) ** 2 + 2.0 * (y + 0.5) ** 2


def sx(x: float) -> float:
    return PAD + (x - X_MIN) / (X_MAX - X_MIN) * (WIDTH - 2 * PAD)


def sy(y: float) -> float:
    return HEIGHT - PAD - (y - Y_MIN) / (Y_MAX - Y_MIN) * (HEIGHT - 2 * PAD)


def ellipse_points(level: float, samples: int = 48) -> str:
    rx = level ** 0.5
    ry = (level / 2.0) ** 0.5
    points = []
    for i in range(samples + 1):
        angle = 2.0 * pi * i / samples
        x = 1.0 + rx * cos(angle)
        y = -0.5 + ry * sin(angle)
        points.append(f"{sx(x):.2f},{sy(y):.2f}")
    return " ".join(points)


def main() -> None:
    at = (2.0, 0.5)
    gx, gy = numerical_gradient(bowl, at, step=1e-5)
    scale = 0.11
    end = (at[0] + scale * gx, at[1] + scale * gy)

    contours = []
    for level, dash in ((0.5, ""), (1.5, "6 5"), (3.0, "2 5"), (5.0, "10 5")):
        contours.append(
            f'<polyline points="{ellipse_points(level)}" fill="none" stroke="#666" stroke-width="2" '
            f'stroke-dasharray="{dash}"/>'
        )

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
<title>Gradient of a quadratic bowl crossing level curves</title>
<desc>Elliptical level curves surround the minimum at one, negative one half. At point two, one half, a solid arrow shows the numerical gradient approximately two comma four, crossing the local level curve normally.</desc>
<defs>
  <marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">
    <path d="M0,0 L10,4 L0,8 Z" fill="#111"/>
  </marker>
</defs>
<rect width="100%" height="100%" fill="white"/>
<line x1="{sx(0):.2f}" y1="{sy(Y_MIN):.2f}" x2="{sx(0):.2f}" y2="{sy(Y_MAX):.2f}" stroke="#999"/>
<line x1="{sx(X_MIN):.2f}" y1="{sy(0):.2f}" x2="{sx(X_MAX):.2f}" y2="{sy(0):.2f}" stroke="#999"/>
{''.join(contours)}
<circle cx="{sx(1):.2f}" cy="{sy(-0.5):.2f}" r="5" fill="white" stroke="#111" stroke-width="2"/>
<text x="{sx(1)+8:.2f}" y="{sy(-0.5)+20:.2f}" font-size="15">minimum</text>
<circle cx="{sx(at[0]):.2f}" cy="{sy(at[1]):.2f}" r="6" fill="#111"/>
<line x1="{sx(at[0]):.2f}" y1="{sy(at[1]):.2f}" x2="{sx(end[0]):.2f}" y2="{sy(end[1]):.2f}" stroke="#111" stroke-width="4" marker-end="url(#arrow)"/>
<text x="{sx(at[0])+10:.2f}" y="{sy(at[1])-12:.2f}" font-size="15">(2, 0.5)</text>
<text x="{sx(end[0])+10:.2f}" y="{sy(end[1])-8:.2f}" font-size="15" font-weight="bold">grad f ~= ({gx:.2f}, {gy:.2f})</text>
<text x="380" y="476" text-anchor="middle" font-size="14">The gradient packages partial derivatives and points in the direction of greatest local increase.</text>
</svg>
'''
    out = Path(__file__).resolve().parents[2] / "assets" / "gradient_geometry.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
