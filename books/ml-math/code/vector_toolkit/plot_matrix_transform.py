from __future__ import annotations

from pathlib import Path

from matrix_toolkit import matvec, transform_points

WIDTH = 860
HEIGHT = 470
ORIGIN_X = 420
ORIGIN_Y = 245
SCALE = 105
TRANSFORM = ((1.0, 0.5), (0.25, 1.0))


def screen(point: tuple[float, float]) -> tuple[float, float]:
    x, y = point
    return ORIGIN_X + SCALE * x, ORIGIN_Y - SCALE * y


def line(a: tuple[float, float], b: tuple[float, float], **attrs: object) -> str:
    x1, y1 = screen(a)
    x2, y2 = screen(b)
    rendered = " ".join(
        f'{key.replace("_", "-")}="{value}"' for key, value in attrs.items()
    )
    return (
        f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" '
        f"{rendered}/>"
    )


def polygon(points: tuple[tuple[float, float], ...], **attrs: object) -> str:
    coords = " ".join(f"{x:.3f},{y:.3f}" for x, y in map(screen, points))
    rendered = " ".join(
        f'{key.replace("_", "-")}="{value}"' for key, value in attrs.items()
    )
    return f'<polygon points="{coords}" {rendered}/>'


def generate() -> str:
    unit_square = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    transformed = transform_points(TRANSFORM, unit_square)
    e1 = (1.0, 0.0)
    e2 = (0.0, 1.0)
    ae1 = matvec(TRANSFORM, e1)
    ae2 = matvec(TRANSFORM, e2)

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">',
        '<title id="title">A matrix transforms basis vectors and the unit square</title>',
        '<desc id="desc">The original unit square and basis vectors are shown with dashed outlines. Applying matrix A sends the basis to the columns of A and the square to a parallelogram, shown with solid outlines.</desc>',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="currentColor"/></marker></defs>',
        '<rect width="100%" height="100%" fill="white"/>',
        '<g color="#111" font-family="sans-serif">',
        '<text x="430" y="35" text-anchor="middle" font-size="22">A maps basis vectors to its columns</text>',
        '<text x="430" y="62" text-anchor="middle" font-size="16">A = [[1, 0.5], [0.25, 1]]</text>',
        line((-3.4, 0), (3.4, 0), stroke="currentColor", stroke_width="1"),
        line((0, -1.7), (0, 1.7), stroke="currentColor", stroke_width="1"),
        polygon(
            unit_square,
            fill="none",
            stroke="currentColor",
            stroke_width="2",
            stroke_dasharray="7 6",
        ),
        polygon(transformed, fill="none", stroke="currentColor", stroke_width="4"),
        line(
            (0, 0),
            e1,
            stroke="currentColor",
            stroke_width="2",
            stroke_dasharray="7 6",
            marker_end="url(#arrow)",
        ),
        line(
            (0, 0),
            e2,
            stroke="currentColor",
            stroke_width="2",
            stroke_dasharray="7 6",
            marker_end="url(#arrow)",
        ),
        line(
            (0, 0),
            ae1,
            stroke="currentColor",
            stroke_width="4",
            marker_end="url(#arrow)",
        ),
        line(
            (0, 0),
            ae2,
            stroke="currentColor",
            stroke_width="4",
            marker_end="url(#arrow)",
        ),
        '<text x="548" y="259" font-size="17">e₁</text>',
        '<text x="430" y="126" font-size="17">e₂</text>',
        '<text x="536" y="204" font-size="17">Ae₁ = column 1</text>',
        '<text x="493" y="120" font-size="17">Ae₂ = column 2</text>',
        '<text x="70" y="395" font-size="16">dashed: input geometry</text>',
        '<text x="70" y="420" font-size="16">solid: transformed geometry</text>',
        "</g>",
        "</svg>",
        "",
    ]
    return "\n".join(parts)


def main() -> None:
    target = Path(__file__).resolve().parents[2] / "assets" / "matrix_transform.svg"
    target.write_text(generate(), encoding="utf-8")


if __name__ == "__main__":
    main()
