from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from vector_toolkit import project, subtract

matplotlib.rcParams["svg.hashsalt"] = "ml-math-vector-geometry-v1"

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "assets" / "vector_geometry.svg"

u = (3.0, 1.0)
v = (1.0, 3.0)
p = project(v, u)
r = subtract(v, p)

fig, ax = plt.subplots(figsize=(6.4, 4.8))


def arrow(x: float, y: float, label: str) -> None:
    ax.arrow(0, 0, x, y, length_includes_head=True, head_width=0.12)
    ax.text(x + 0.08, y + 0.08, label)


arrow(*u, "u")
arrow(*v, "v")
arrow(*p, "proj_u(v)")
ax.arrow(p[0], p[1], r[0], r[1], length_includes_head=True, head_width=0.12)
ax.text(p[0] + r[0] / 2 + 0.08, p[1] + r[1] / 2, "residual")

ax.axhline(0, linewidth=0.8)
ax.axvline(0, linewidth=0.8)
ax.set_aspect("equal", adjustable="box")
ax.set_xlim(-0.5, 3.8)
ax.set_ylim(-0.5, 3.8)
ax.set_xlabel("x component")
ax.set_ylabel("y component")
ax.set_title("Projection decomposes v into parallel + orthogonal parts")
ax.grid(True, linewidth=0.4)
fig.tight_layout()

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUTPUT, format="svg", metadata={"Date": None})
print(OUTPUT)
