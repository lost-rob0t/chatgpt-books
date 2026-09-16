from pathlib import Path

from vector_toolkit import project, subtract

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "assets" / "vector_geometry.svg"

u = (3.0, 1.0)
v = (1.0, 3.0)
p = project(v, u)
r = subtract(v, p)

WIDTH = 720
HEIGHT = 520
ORIGIN_X = 100
ORIGIN_Y = 430
SCALE = 100


def point(values: tuple[float, float]) -> tuple[float, float]:
    return ORIGIN_X + SCALE * values[0], ORIGIN_Y - SCALE * values[1]


def line_arrow(start: tuple[float, float], end: tuple[float, float]) -> str:
    x1, y1 = point(start)
    x2, y2 = point(end)
    return (
        f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" '
        'stroke="currentColor" stroke-width="3" marker-end="url(#arrow)" />'
    )


def label(values: tuple[float, float], text: str, dx: float, dy: float) -> str:
    x, y = point(values)
    return f'<text x="{x + dx:.3f}" y="{y + dy:.3f}" font-size="20">{text}</text>'


residual_end = (p[0] + r[0], p[1] + r[1])
residual_mid = ((p[0] + residual_end[0]) / 2, (p[1] + residual_end[1]) / 2)

svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">
  <title id="title">Vector projection geometry</title>
  <desc id="desc">Vector v is decomposed into its projection onto u and an orthogonal residual from the projection endpoint to v.</desc>
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L9,3 z" fill="currentColor" />
    </marker>
  </defs>
  <rect width="100%" height="100%" fill="white" />
  <g color="#111" font-family="sans-serif">
    <line x1="50" y1="{ORIGIN_Y}" x2="680" y2="{ORIGIN_Y}" stroke="currentColor" stroke-width="1" />
    <line x1="{ORIGIN_X}" y1="470" x2="{ORIGIN_X}" y2="50" stroke="currentColor" stroke-width="1" />
    <text x="360" y="32" text-anchor="middle" font-size="22">projection: v = proj_u(v) + residual</text>
    {line_arrow((0.0, 0.0), u)}
    {label(u, 'u', 8, -8)}
    {line_arrow((0.0, 0.0), v)}
    {label(v, 'v', -26, -8)}
    {line_arrow((0.0, 0.0), p)}
    {label(p, 'proj_u(v)', 8, 24)}
    {line_arrow(p, residual_end)}
    {label(residual_mid, 'residual', 14, -4)}
  </g>
</svg>
'''

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(svg, encoding="utf-8")
print(OUTPUT)
