"""Print a machine-readable synthetic witness; never train or use held-out truth."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'upstream'))
import world_models
import bk01_coverage_gate as gate
import bk01_window_projection as bridge


def main() -> None:
    env = gate.make_fixture(world_models)
    result = bridge.project(env, world_models)
    binary = gate.forecast(env, world_models)
    print(json.dumps({
        "scope": "synthetic native BK01 / BK10 projection; BK10 actual encoder NOT RUN",
        "contract": bridge.CONTRACT,
        "native_bk01_blob": gate.PROVIDER_BLOB,
        "observations": result["observations"],
        "lineage": result["lineage"],
        "observation_sha256": result["observation_sha256"],
        "next_binary_high_uncalibrated": binary["p_high_uncalibrated"],
        "forecast_window_start_unix_seconds": binary["forecast_window_start"],
        "bk10_native_encoder": "NOT RUN",
        "truth_used": False,
    }, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
