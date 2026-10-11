"""BK10 synthetic capture-inventory boundary for native BK01 prediction.

The hard-coded digest anchors ONE invented teaching fixture, not external trust.
It is not a StarIntel schema, real-source coverage attestation, or trained model.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CONTRACT = "bk10.bk01.fixed-inventory-coverage.v0"
PROVIDER_BLOB = "b12863b2792dc3961ef05343fe455667605251c7"
START = 1_700_000_040
WINDOW_SECONDS = 60
WINDOWS = 3
MAX_EVENTS = 32
# Independently frozen receipt for five observations, not computed from input.
# The digest was fixed before evaluating any event-loss perturbations.
RECEIPT_SHA256 = "ee9d63ba24cc5e9c4dee8ec857de2dfb30d62094a672faeafe1321fb43d9c292"


class CoverageError(ValueError):
    """Unsealed, changed, or unsupported observation input."""


def json_sha256(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def _exact(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise CoverageError(f"{where}: exact keys required")
    return value


def verify_provider(provider: Any) -> None:
    if any(getattr(provider, name, None) != value for name, value in (
        ("VERSION", "0.10.1"), ("DATASET", "world-model-synthetic"),
        ("WINDOW_SECONDS", WINDOW_SECONDS), ("BUCKETS", ("low", "high"))
    )):
        raise CoverageError("provider: incompatible constants")
    try:
        data = Path(provider.__file__).resolve(strict=True).read_bytes()
    except (OSError, TypeError, AttributeError) as exc:
        raise CoverageError("provider: source file unavailable") from exc
    if len(data) > 64 * 1024 or git_blob_sha(data) != PROVIDER_BLOB:
        raise CoverageError("provider: exact Git blob mismatch")
    if not callable(getattr(provider, "BinaryWorldModel", None)) or not callable(
        getattr(provider, "aggregate_synthetic_events", None)
    ):
        raise CoverageError("provider: executable interface absent")


def _inventory(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(({"id": e["id"], "observedAt": e["observedAt"]}
                   for e in events), key=lambda e: e["id"])


def make_fixture(provider: Any) -> dict[str, Any]:
    """Generate a known invented BK01 event inventory; never real records."""
    verify_provider(provider)
    events = list(provider.synthetic_documents()[:5])
    windows = provider.aggregate_synthetic_events(events, start=START, windows=WINDOWS)
    return {
        "contract": CONTRACT,
        "start": START,
        "window_seconds": WINDOW_SECONDS,
        "events": events,
        "events_sha256": json_sha256(events),
        "inventory_receipt": _inventory(events),
        "inventory_receipt_sha256": json_sha256(_inventory(events)),
        "seals": [{"start": w.window_start,
                   "end": w.window_start + WINDOW_SECONDS,
                   "complete": True,
                   "source_ids": list(w.source_ids)} for w in windows],
    }


def validate_envelope(raw: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Pure evidence validation, independent of candidate provider availability."""
    env = _exact(raw, {"contract", "start", "window_seconds", "events",
                       "events_sha256", "inventory_receipt",
                       "inventory_receipt_sha256", "seals"}, "envelope")
    if env["contract"] != CONTRACT or type(env["start"]) is not int or env["start"] != START:
        raise CoverageError("envelope: incompatible contract or start")
    if type(env["window_seconds"]) is not int or env["window_seconds"] != WINDOW_SECONDS:
        raise CoverageError("envelope: expected 60-second windows")
    events = env["events"]
    if not isinstance(events, list) or not 0 < len(events) <= MAX_EVENTS:
        raise CoverageError("events: bounded nonempty list required")
    if json_sha256(events) != env["events_sha256"]:
        raise CoverageError("events: content digest mismatch")
    seen: set[str] = set()
    for event in events:
        _exact(event, {"id", "dataset", "dtype", "schemaVersion", "observedAt",
                       "eventKind"}, "event")
        ident = event["id"]
        ts = event["observedAt"]
        if (not isinstance(ident, str) or not ident.startswith("synthetic:event:")
                or len(ident) > 96 or ident in seen):
            raise CoverageError("event: duplicate or non-synthetic identity")
        seen.add(ident)
        if (event["dataset"] != "world-model-synthetic" or event["dtype"] != "event"
                or event["schemaVersion"] != "0.10.1"
                or event["eventKind"] != "synthetic-signal"
                or type(ts) is not int or not START <= ts < START + WINDOWS * 60):
            raise CoverageError("event: unsupported fields or timestamp")
    receipt = env["inventory_receipt"]
    if not isinstance(receipt, list) or len(receipt) > MAX_EVENTS:
        raise CoverageError("receipt: malformed inventory")
    for entry in receipt:
        _exact(entry, {"id", "observedAt"}, "receipt item")
    if (json_sha256(receipt) != RECEIPT_SHA256
            or env["inventory_receipt_sha256"] != RECEIPT_SHA256):
        raise CoverageError("receipt: not the independently frozen teaching inventory")
    if _inventory(events) != receipt:
        raise CoverageError("receipt: observed events differ from frozen inventory")
    seals = env["seals"]
    if not isinstance(seals, list) or len(seals) != WINDOWS:
        raise CoverageError("seals: exactly three windows required")
    for i, seal in enumerate(seals):
        _exact(seal, {"start", "end", "complete", "source_ids"}, "seal")
        if (type(seal["start"]) is not int or seal["start"] != START + i * 60
                or type(seal["end"]) is not int or seal["end"] != START + (i + 1) * 60
                or seal["complete"] is not True):
            raise CoverageError("seal: unsealed or noncontiguous window")
        ids = seal["source_ids"]
        if (not isinstance(ids, list) or not all(isinstance(s, str) for s in ids)
                or ids != sorted(set(ids))):
            raise CoverageError("seal: sorted unique source IDs required")
    buckets = [[] for _ in range(WINDOWS)]
    for event in events:
        buckets[(event["observedAt"] - START) // WINDOW_SECONDS].append(event["id"])
    if any(seal["source_ids"] != sorted(buckets[i]) for i, seal in enumerate(seals)):
        raise CoverageError("seal: window event inventory mismatch")
    return events, seals


def validated_windows(raw: Any, provider: Any) -> tuple[Any, ...]:
    """Require exact source and frozen receipt before calling upstream BK01."""
    verify_provider(provider)
    events, seals = validate_envelope(raw)
    windows = provider.aggregate_synthetic_events(events, start=START, windows=WINDOWS)
    if any(seal["source_ids"] != list(w.source_ids)
           for seal, w in zip(seals, windows, strict=True)):
        raise CoverageError("provider: output differs from checked sealed inventory")
    return windows


def forecast(raw: Any, provider: Any) -> dict[str, Any]:
    windows = validated_windows(raw, provider)
    last = provider.BinaryWorldModel().filter(windows)[-1]
    return {
        "contract": CONTRACT,
        "provider_git_blob": PROVIDER_BLOB,
        "kind": "fixed-probability-binary-filter-not-trained",
        "observations": [w.count for w in windows],
        "forecast_window_start": last.window_start + WINDOW_SECONDS,
        "p_high_uncalibrated": last.next_high_probability,
        "truth_used": False,
    }


def corrupt_self_consistently(raw: dict[str, Any]) -> dict[str, Any]:
    """NEGATIVE CONTROL ONLY: omit last window while rewriting *all mutable* receipts."""
    env = json.loads(json.dumps(raw))
    env["events"] = [e for e in env["events"] if e["observedAt"] < START + 120]
    env["events_sha256"] = json_sha256(env["events"])
    env["inventory_receipt"] = _inventory(env["events"])
    env["inventory_receipt_sha256"] = json_sha256(env["inventory_receipt"])
    env["seals"][-1]["source_ids"] = []
    return env


def frozen_fixture() -> dict[str, Any]:
    """Hardcoded synthetic source snapshot for provider-absent tests."""
    events = [{
        "id": f"synthetic:event:{i:03d}",
        "dataset": "world-model-synthetic", "dtype": "event",
        "schemaVersion": "0.10.1", "observedAt": START + offset,
        "eventKind": "synthetic-signal",
    } for i, offset in enumerate((65, 75, 125, 135, 145))]
    buckets = [[] for _ in range(WINDOWS)]
    for e in events:
        buckets[(e["observedAt"] - START) // 60].append(e["id"])
    return {
        "contract": CONTRACT, "start": START,
        "window_seconds": WINDOW_SECONDS, "events": events,
        "events_sha256": json_sha256(events),
        "inventory_receipt": _inventory(events),
        "inventory_receipt_sha256": RECEIPT_SHA256,
        "seals": [{"start": START + i * 60, "end": START + (i + 1) * 60,
                   "complete": True, "source_ids": sorted(bucket)}
                  for i, bucket in enumerate(buckets)],
    }
