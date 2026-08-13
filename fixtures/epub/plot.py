#!/usr/bin/env python3
from pathlib import Path
import matplotlib.pyplot as plt
xs=[x/10 for x in range(-20,81)]
ys=[(x-3)**2 for x in xs]
fig=plt.figure(figsize=(7,4))
ax=fig.add_subplot(111)
ax.plot(xs,ys)
ax.set_xlabel("x")
ax.set_ylabel("f(x) = (x - 3)^2")
ax.set_title("Quadratic objective")
ax.grid(True,alpha=.25)
out=Path(__file__).parent/'build'/'objective.png'; out.parent.mkdir(parents=True,exist_ok=True)
fig.tight_layout(); fig.savefig(out,dpi=160); plt.close(fig)
