"""Generate the deterministic secant-to-tangent teaching figure."""

from __future__ import annotations

from pathlib import Path

from calculus_lab import forward_difference

WIDTH = 760
HEIGHT = 460
PAD = 55
X_MIN, X_MAX = -0.25, 2.25
Y_MIN, Y_MAX = -0.25, 5.25


def sx(x: float) -> float:
    return PAD + (x - X_MIN) / (X_MAX - X_MIN) * (WIDTH - 2 * PAD)


def sy(y: float) -> float:
    return HEIGHT - PAD - (y - Y_MIN) / (Y_MAX - Y_MIN) * (HEIGHT - 2 * PAD)


def polyline(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in points)


def line_for_slope(x0: float, y0: float, slope: float) -> tuple[tuple[float, float], tuple[float, float]]:
    left = X_MIN
    right = X_MAX
    return ((left, y0 + slope * (left - x0)), (right, y0 + slope * (right - x0)))


def main() -> None:
    square = lambda x: x * x
    anchor_x = 1.0
    anchor_y = square(anchor_x)
    hs = (1.0, 0.5, 0.25)
    secants = [(h, forward_difference(square, anchor_x, step=h)) for h in hs]
    tangent = 2.0

    curve = []
    for i in range(161):
        x = X_MIN + i * (X_MAX - X_MIN) / 160.0
        curve.append((x, square(x)))

    rows = []
    for idx, (h, slope) in enumerate(secants):
        dash = ("10 7", "4 6", "2 5")[idx]
        (x1, y1), (x2, y2) = line_for_slope(anchor_x, anchor_y, slope)
        rows.append(
            f'<line x1="{sx(x1):.2f}" y1="{sy(y1):.2f}" x2="{sx(x2):.2f}" y2="{sy(y2):.2f}" '
            f'stroke="#555" stroke-width="2" stroke-dasharray="{dash}"/>'
        )
        sample_x = anchor_x + h
        rows.append(
            f'<circle cx="{sx(sample_x):.2f}" cy="{sy(square(sample_x)):.2f}" r="5" fill="white" stroke="#111" stroke-width="2"/>'
        )

    (tx1, ty1), (tx2, ty2) = line_for_slope(anchor_x, anchor_y, tangent)

    legend = []
    for idx, (h, slope) in enumerate(secants):
        legend.append(
            f'<text x="500" y="{70 + idx * 24}" font-size="15">h={h:g}, secant slope={slope:.2f}</text>'
        )
    legend.append('<text x="500" y="142" font-size="15" font-weight="bold">limit slope = 2.00</text>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
<title>Secants approach the tangent of y equals x squared at x equals one</title>
<desc>Three differently dashed secant lines through x equals one use h values one, one half, and one quarter. Their slopes approach the solid tangent slope two.</desc>
<rect width="100%" height="100%" fill="white"/>
<line x1="{sx(0):.2f}" y1="{sy(Y_MIN):.2f}" x2="{sx(0):.2f}" y2="{sy(Y_MAX):.2f}" stroke="#777"/>
<line x1="{sx(X_MIN):.2f}" y1="{sy(0):.2f}" x2="{sx(X_MAX):.2f}" y2="{sy(0):.2f}" stroke="#777"/>
<polyline points="{polyline(curve)}" fill="none" stroke="#111" stroke-width="3"/>
{''.join(rows)}
<line x1="{sx(tx1):.2f}" y1="{sy(ty1):.2f}" x2="{sx(tx2):.2f}" y2="{sy(ty2):.2f}" stroke="#111" stroke-width="3"/>
<circle cx="{sx(anchor_x):.2f}" cy="{sy(anchor_y):.2f}" r="6" fill="#111"/>
<text x="{sx(anchor_x)+9:.2f}" y="{sy(anchor_y)-9:.2f}" font-size="15">(1, 1)</text>
<text x="{sx(1.55):.2f}" y="{sy(3.1):.2f}" font-size="16" font-weight="bold">y = x^2</text>
{''.join(legend)}
<text x="380" y="438" text-anchor="middle" font-size="14">As h shrinks, the secant quotient 2+h approaches the tangent slope 2.</text>
</svg>
'''
    out = Path(__file__).resolve().parents[2] / "assets" / "calculus_secants.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
