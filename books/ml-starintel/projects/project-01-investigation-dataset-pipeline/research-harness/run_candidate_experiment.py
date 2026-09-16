#!/usr/bin/env python3
"""Execute the pass-12 Tier C scalable near-duplicate candidate experiment."""

from __future__ import annotations

import json
from pathlib import Path

from near_duplicate_candidates import DEFAULT_CONFIG, evaluate_candidate_contract
from run_leakage_experiments import generate_duplicate_fixture


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "artifacts" / "candidate-generation-tier-c.json"


def main() -> None:
    rows = generate_duplicate_fixture()
    result = evaluate_candidate_contract(rows, config=DEFAULT_CONFIG)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))

    required = {
        "component_equality": True,
        "qualifying_pair_recall": 1.0,
        "input_permutation_equal": True,
    }
    for key, expected in required.items():
        if result[key] != expected:
            raise SystemExit(f"candidate contract failed: {key}={result[key]!r}, expected {expected!r}")
    if result["candidate_pair_count"] >= result["all_pair_count"]:
        raise SystemExit("candidate generation did not reduce the Tier C comparison set")


if __name__ == "__main__":
    main()
