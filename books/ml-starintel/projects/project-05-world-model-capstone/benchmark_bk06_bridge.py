"""Measured single-host BK06 CPU costs; synthetic only; not production throughput."""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
from statistics import median
from time import perf_counter_ns

from bk06_trajectory_bridge import history_from_events, load_pinned_provider, predict


def bench(fn, repeats=30):
    times = []
    for _ in range(repeats):
        start = perf_counter_ns()
        fn()
        times.append((perf_counter_ns() - start) / 1e6)
    return {"median_ms": round(median(times), 6), "min_ms": round(min(times), 6),
            "max_ms": round(max(times), 6), "repetitions": repeats}


def main() -> None:
    source = os.environ.get("BK10_BK06_PROVIDER")
    if not source:
        raise SystemExit("BK10_BK06_PROVIDER is required: no source fallback")
    bk06 = load_pinned_provider(Path(source))
    episodes = bk06.synthetic_events(96, 148)
    train, test = bk06.split_episodes(episodes, 72)
    target = test[0]
    h = history_from_events(target.episode_id, list(target.events[:4]))
    fitted = bk06.ConditionalDiffusion.fit(train)
    measurements = {
        "fit_training_72_episodes": bench(lambda: bk06.ConditionalDiffusion.fit(train)),
        "bk06_predict_16x6x64": bench(lambda: fitted.forecast(tuple(h["observations"]), 16, 248)),
        "bk10_validated_predict_16x6x64": bench(lambda: predict(fitted, h, samples=16, seed=248)),
        "bk10_validated_predict_4x6x64": bench(lambda: predict(fitted, h, samples=4, seed=248)),
        "bk10_validated_predict_64x6x64": bench(lambda: predict(fitted, h, samples=64, seed=248)),
    }
    payload = {"system": platform.platform(), "python": platform.python_version(),
               "processor": platform.processor(), "hardware_cpu": open('/proc/cpuinfo').read().split('model name\t: ')[1].split('\n')[0] if os.path.exists('/proc/cpuinfo') and 'model name\t: ' in open('/proc/cpuinfo').read() else 'unavailable',
               "numpy": bk06.np.__version__, "evidence": "MEASURED_LOCAL_SYNTHETIC_ONLY",
               "fit_density_scalars": 16, "nontrained_schedule_scalars": 128,
               "estimation": "Python object/NumPy overhead omitted from scalar counts",
               "measurements": measurements}
    print(json.dumps(payload, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
