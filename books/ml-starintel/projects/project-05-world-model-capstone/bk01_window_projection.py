"""BK10: provenance-preserving bridge from *sealed BK01 windows* to unit ticks.

This project-local, synthetic-only mapping is NOT a StarIntel wire schema.
Time index t is the ordinal position of a complete BK01 60-second window;
there is no implicit conversion between clock time and a model time unit.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

import bk01_coverage_gate as gate

CONTRACT = "bk10.bk01.sealed-window-projection.v1"
OBSERVATION_VERSION = "bk10.observations.v0"
TIME_AXIS = "ordinal-index-of-complete-60-second-synthetic-window"
MAX_WINDOWS = 256


class ProjectionError(ValueError):
    """The candidate does not satisfy this narrow synthetic interface."""


def _strict_number(value: Any) -> bool:
    return type(value) is int or type(value) is float


def project(envelope: dict[str, Any], provider: Any) -> dict[str, Any]:
    """Verify original BK01 source and a frozen inventory BEFORE copying counts."""
    windows = gate.validated_windows(envelope, provider)
    if not 2 <= len(windows) <= MAX_WINDOWS:
        raise ProjectionError("expected 2..256 verified complete source windows")
    if any(type(w.count) is not int or w.count < 0 or w.count > 1_000_000 for w in windows):
        raise ProjectionError("source count outside BK10 integer range")

    rows: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    for t, window in enumerate(windows):
        expected_start = gate.START + t * gate.WINDOW_SECONDS
        if type(window.window_start) is not int or window.window_start != expected_start:
            raise ProjectionError("source window does not match the sealed clock range")
        ids = tuple(window.source_ids)
        if len(ids) != window.count or not all(isinstance(i, str) for i in ids):
            raise ProjectionError("source identities do not match count")
        if len(ids) != len(set(ids)) or ids != tuple(sorted(ids)):
            raise ProjectionError("source identities must be sorted and unique")
        rows.append({
            "document_id": f"synthetic:bk01-window:{t:03d}",
            "t": t, "source": "synthetic-counter", "kind": "count",
            "count": window.count,
        })
        provenance.append({
            "t": t, "start_unix_seconds": window.window_start,
            "end_exclusive_unix_seconds": window.window_start + gate.WINDOW_SECONDS,
            "source_ids": list(ids), "complete": True,
        })
    observations = {"version": OBSERVATION_VERSION, "records": rows}
    return {
        "contract": CONTRACT,
        "source_kind": "independently-frozen-invented-inventory-not-live-capture",
        "provider_git_blob": gate.PROVIDER_BLOB,
        "time_axis": TIME_AXIS,
        "window_seconds": gate.WINDOW_SECONDS,
        "source_event_sha256": envelope["events_sha256"],
        "source_inventory_sha256": gate.RECEIPT_SHA256,
        "observation_sha256": gate.json_sha256(observations),
        "observations": observations,
        "lineage": provenance,
    }


def evaluate_separate_predictors(
    envelope: dict[str, Any], provider: Any, capstone: Any
) -> dict[str, Any]:
    """Native BK01 next-high probability vs BK10 count scenarios, never pooled.

    The capstone argument is an explicit dependency. It MUST implement the
    exact BK10 v0 API; absence or schema disagreement is a hard failure.
    """
    projected = project(envelope, provider)
    if getattr(capstone, "CONTRACT", None) != "bk10.capstone.v0":
        raise ProjectionError("incompatible BK10 capstone contract")
    for name in ("validate_observations", "encode_state", "candidate_futures"):
        if not callable(getattr(capstone, name, None)):
            raise ProjectionError(f"missing BK10 method: {name}")
    verified = capstone.validate_observations(deepcopy(projected["observations"]))
    if verified != projected["observations"]["records"]:
        raise ProjectionError("BK10 validation changed or substituted observation rows")
    state = capstone.encode_state(verified, observation_digest=projected["observation_sha256"])
    if not isinstance(state, dict) or state.get("observation_digest") != projected["observation_sha256"]:
        raise ProjectionError("BK10 state lost source digest")
    if state.get("as_of") != len(projected["lineage"]) - 1:
        raise ProjectionError("BK10 state used a different unit-tick origin")
    count_futures = capstone.candidate_futures(state)
    if not isinstance(count_futures, dict) or count_futures.get("forecast_t") != len(projected["lineage"]):
        raise ProjectionError("BK10 count forecast misaligned with future window")
    binary = gate.forecast(envelope, provider)
    next_window_start = gate.START + len(projected["lineage"]) * gate.WINDOW_SECONDS
    if binary["forecast_window_start"] != next_window_start:
        raise ProjectionError("BK01 probability forecast used another clock horizon")
    p_high = binary["p_high_uncalibrated"]
    if not _strict_number(p_high) or not 0.0 <= p_high <= 1.0:
        raise ProjectionError("BK01 probability must be a finite 0..1 number")
    return {
        "contract": CONTRACT,
        "projection": projected,
        "bk10_untrained_count_scenarios": count_futures,
        "bk01_fixed_filter_next_high": {
            "kind": "fixed-probability-binary-filter-not-trained",
            "p_high_uncalibrated": p_high,
            "forecast_start_unix_seconds": next_window_start,
        },
        "targets_are_distinct": True,
        "truth_used": False,
    }
