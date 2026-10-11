"""Offline BK10/BK01 capture-loss witness. Requires an exact upstream source file."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import platform
import statistics
import sys
import time

from bk01_coverage_gate import (START, WINDOWS, CoverageError, corrupt_self_consistently,
                               forecast, frozen_fixture, json_sha256, verify_provider)


def load_native(path: Path):
    spec = importlib.util.spec_from_file_location("bk01_coverage_native", path)
    if spec is None or spec.loader is None:
        raise ValueError("could not load explicit BK01 provider path")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolves the module during execution
    try:
        spec.loader.exec_module(module)
        verify_provider(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


def median_us(operation, repetitions: int = 400) -> float:
    for _ in range(40):
        operation()
    samples = []
    for _ in range(repetitions):
        start = time.perf_counter_ns()
        operation()
        samples.append((time.perf_counter_ns() - start) / 1_000)
    return statistics.median(samples)


def run(provider):
    clean = frozen_fixture()
    counterfeit = corrupt_self_consistently(clean)
    accepted = forecast(clean, provider)
    try:
        forecast(counterfeit, provider)
        raise AssertionError("loss scenario unexpectedly authorized")
    except CoverageError as error:
        rejection = str(error)
    naive_windows = provider.aggregate_synthetic_events(counterfeit["events"],
                                                         start=START, windows=WINDOWS)
    naive_high = provider.BinaryWorldModel().filter(naive_windows)[-1].next_high_probability
    truth_bucket = provider.aggregate_synthetic_events(provider.synthetic_documents()[5:],
                        start=START + 180, windows=1)[0].bucket
    if truth_bucket != "low":
        raise AssertionError("changed held-out synthetic fixture")
    p_clean = accepted["p_high_uncalibrated"]
    return {
        "version": "bk10.bk01.capture-loss-witness.v0",
        "scope": "one invented synthetic fixture; not live completeness or calibration",
        "model": "native BK01 fixed probability tables; no training",
        "clean": accepted,
        "counterfactual": {
            "label": "illegitimate omission re-sealed as apparent zero",
            "counts": [w.count for w in naive_windows],
            "naive_p_high_uncalibrated": naive_high,
            "rejected_by_bk10": True,
            "reason": rejection,
        },
        "forecast_probability_difference": p_clean - naive_high,
        "heldout_one_window": {
            "truth_bucket": truth_bucket,
            "clean_brier": p_clean * p_clean,
            "naive_brier": naive_high * naive_high,
            "interpretation": "one-case score cannot validate a forged observation inventory",
        },
        "receipt_sha256": clean["inventory_receipt_sha256"],
        "input_sha256": json_sha256(clean),
        "cpu": {
            "python": platform.python_version(),
            "machine": platform.machine(),
            "platform": platform.platform(),
            "repetitions": 400,
            "no_training": True,
            "native_aggregation_filter_median_us": median_us(
                lambda: provider.BinaryWorldModel().filter(
                    provider.aggregate_synthetic_events(clean["events"],start=START,windows=WINDOWS))),
            "bk10_validation_native_filter_median_us": median_us(lambda: forecast(clean,provider)),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run(load_native(args.provider))
    encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
