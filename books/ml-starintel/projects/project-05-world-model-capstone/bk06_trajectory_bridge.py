"""BK10-owned, BK06-pinned synthetic continuous-trajectory integration seam.

No conversion of BK10 count/ticks into BK06 continuous measurements is offered.
No StarIntel wire, event-store, network, person, or live incident is involved.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

PROVIDER_COMMIT = "151ed124852be96aea45d3c26d37d1ec27452885"
PROVIDER_BLOB = "5be4412b67bb43a8bc4bff84f62c987ba9651a55"
HISTORY = 4
HORIZON = 6
INPUT = "bk10.bk06.synthetic-history.v1"
OUTPUT = "bk10.bk06.candidate-futures.v1"
TIMEBASE = "bk06.synthetic.unit-tick.v1"
KIND = "synthetic_numeric_observation"
TIER = "C-synthetic"
MAX_SAMPLES = 64


class BridgeError(ValueError):
    """Reject ambiguous unit, provenance, pin or shape conversions."""


def _keys(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise BridgeError(f"{where}: required keys {sorted(keys)}")
    return value


def _number(value: Any, where: str) -> float:
    if type(value) not in (float, int) or not math.isfinite(value):
        raise BridgeError(f"{where}: finite real number required")
    return float(value)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def load_pinned_provider(path: Path) -> ModuleType:
    """Execute only exact verified Git blob bytes; never fetch provider code."""
    data = path.read_bytes()
    if git_blob_sha(data) != PROVIDER_BLOB:
        raise BridgeError("BK06 provider Git blob mismatch")
    name = "_bk10_verified_bk06_provider"
    if name in sys.modules:
        raise BridgeError("provider module-name collision")
    module = ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module  # dataclass uses sys.modules for annotations
    try:
        exec(compile(data, str(path), "exec"), module.__dict__)
        if (module.HISTORY, module.HORIZON) != (HISTORY, HORIZON):
            raise BridgeError("provider time dimensions changed")
        return module
    finally:
        del sys.modules[name]


def history_from_events(episode_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    """Only four already observed samples enter the inference boundary."""
    if not isinstance(episode_id, str) or not episode_id.startswith("synthetic-episode-"):
        raise BridgeError("only BK06 synthetic episode IDs are allowed")
    if type(events) is not list or len(events) != HISTORY:
        raise BridgeError("exactly four history events required")
    values: list[float] = []
    ids: set[str] = set()
    for tick, item in enumerate(events):
        _keys(item, {"event_id", "episode_id", "time_index", "kind", "measurement",
                     "provenance_tier"}, "event")
        event_id = f"{episode_id}-tick-{tick:02d}"
        if item["event_id"] != event_id or item["event_id"] in ids:
            raise BridgeError("event identity mismatch or duplication")
        ids.add(item["event_id"])
        if (item["episode_id"] != episode_id or type(item["time_index"]) is not int
                or item["time_index"] != tick):
            raise BridgeError("episode membership/timebase mismatch")
        if item["kind"] != KIND or item["provenance_tier"] != TIER:
            raise BridgeError("measurement kind/provenance mismatch")
        values.append(_number(item["measurement"], "history measurement"))
    return {"contract": INPUT, "episode_id": episode_id, "timebase": TIMEBASE,
            "units": "BK06 synthetic signed continuous measurement (not a count)",
            "as_of": HISTORY - 1, "observations": values,
            "history_digest": _digest(events)}


def validate_history(history: Any) -> tuple[float, ...]:
    _keys(history, {"contract", "episode_id", "timebase", "units", "as_of",
                    "observations", "history_digest"}, "history")
    if history["contract"] != INPUT or history["timebase"] != TIMEBASE:
        raise BridgeError("history contract/timebase mismatch")
    if history["units"] != "BK06 synthetic signed continuous measurement (not a count)":
        raise BridgeError("measurement units mismatch")
    if (not isinstance(history["episode_id"], str) or
            not history["episode_id"].startswith("synthetic-episode-") or
            type(history["as_of"]) is not int or history["as_of"] != HISTORY - 1):
        raise BridgeError("history identity/as-of mismatch")
    values = history["observations"]
    if type(values) is not list or len(values) != HISTORY:
        raise BridgeError("history must contain four observations")
    if (not isinstance(history["history_digest"], str)
            or len(history["history_digest"]) != 64
            or any(x not in "0123456789abcdef" for x in history["history_digest"])):
        raise BridgeError("bad history provenance digest")
    decoded = tuple(_number(x, "history value") for x in values)
    rebuilt = [{"event_id": f"{history['episode_id']}-tick-{j:02d}",
                "episode_id": history["episode_id"], "time_index": j,
                "kind": KIND, "measurement": value, "provenance_tier": TIER}
               for j, value in enumerate(decoded)]
    if _digest(rebuilt) != history["history_digest"]:
        raise BridgeError("history digest disagrees with measurements")
    return decoded


def predict(model: Any, history: dict[str, Any], *, samples: int, seed: int) -> dict[str, Any]:
    """Provider sees only a four-float tuple; truth is not a parameter."""
    values = validate_history(history)
    if type(samples) is not int or not 1 <= samples <= MAX_SAMPLES:
        raise BridgeError("sample budget must be 1..64")
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise BridgeError("seed must be a bounded integer")
    forecasts = model.forecast(values, samples, seed)
    if not hasattr(forecasts, "tolist"):
        raise BridgeError("provider result is not an array")
    result = forecasts.tolist()
    if type(result) is not list or len(result) != samples:
        raise BridgeError("provider sample dimension mismatch")
    trajectories: list[dict[str, Any]] = []
    for number, row in enumerate(result):
        if type(row) is not list or len(row) != HORIZON:
            raise BridgeError("provider horizon mismatch")
        trajectories.append({"sample_id": number,
                             "measurements": [_number(v, "predicted measurement") for v in row]})
    output = {"contract": OUTPUT, "source_commit": PROVIDER_COMMIT,
            "source_blob": PROVIDER_BLOB, "episode_id": history["episode_id"],
            "timebase": TIMEBASE, "as_of": HISTORY - 1,
            "forecast_ticks": list(range(HISTORY, HISTORY + HORIZON)),
            "history_digest": history["history_digest"], "seed": seed,
            "samples": trajectories, "probability_weights": None}
    validate_forecast(output)
    return output


def validate_forecast(forecast: Any) -> None:
    _keys(forecast, {"contract", "source_commit", "source_blob", "episode_id", "timebase",
                     "as_of", "forecast_ticks", "history_digest", "seed", "samples",
                     "probability_weights"}, "forecast")
    if (forecast["contract"] != OUTPUT or forecast["timebase"] != TIMEBASE or
            forecast["source_commit"] != PROVIDER_COMMIT or forecast["source_blob"] != PROVIDER_BLOB or
            type(forecast["as_of"]) is not int or forecast["as_of"] != HISTORY - 1 or
            forecast["forecast_ticks"] != list(range(HISTORY, HISTORY + HORIZON)) or
            forecast["probability_weights"] is not None):
        raise BridgeError("forecast provenance, shape or unsupported weights")
    if not isinstance(forecast["episode_id"], str) or not forecast["episode_id"].startswith("synthetic-episode-"):
        raise BridgeError("forecast episode identity mismatch")
    if type(forecast["seed"]) is not int or not 0 <= forecast["seed"] <= 2**32 - 1:
        raise BridgeError("forecast seed invalid")
    if not isinstance(forecast["history_digest"], str) or len(forecast["history_digest"]) != 64:
        raise BridgeError("forecast history digest invalid")
    rows = forecast["samples"]
    if type(rows) is not list or not 1 <= len(rows) <= MAX_SAMPLES:
        raise BridgeError("forecast sample count invalid")
    for j, row in enumerate(rows):
        _keys(row, {"sample_id", "measurements"}, "forecast row")
        if type(row["sample_id"]) is not int or row["sample_id"] != j:
            raise BridgeError("sample index mismatch")
        vals = row["measurements"]
        if type(vals) is not list or len(vals) != HORIZON:
            raise BridgeError("forecast trajectory length mismatch")
        for v in vals:
            _number(v, "forecast measurement")


def score_after_forecast(forecast: dict[str, Any], future: list[dict[str, Any]]) -> dict[str, Any]:
    """Only after predict: score held-out events, without selecting the best draw."""
    validate_forecast(forecast)
    if (type(future) is not list or len(future) != HORIZON or
            forecast.get("forecast_ticks") != list(range(HISTORY, HISTORY + HORIZON))):
        raise BridgeError("six aligned future events required")
    truth = []
    for j, item in enumerate(future, start=HISTORY):
        _keys(item, {"event_id", "episode_id", "time_index", "kind", "measurement",
                     "provenance_tier"}, "future event")
        if (item["episode_id"] != forecast["episode_id"] or
                item["event_id"] != f"{forecast['episode_id']}-tick-{j:02d}" or
                type(item["time_index"]) is not int or item["time_index"] != j or
                item["kind"] != KIND or item["provenance_tier"] != TIER):
            raise BridgeError("future episode/timebase/provenance mismatch")
        truth.append(_number(item["measurement"], "held-out value"))
    rows = [x["measurements"] for x in forecast["samples"]]
    means = [sum(x[t] for x in rows) / len(rows) for t in range(HORIZON)]
    mae = sum(abs(means[t] - truth[t]) for t in range(HORIZON)) / HORIZON
    endpoint_hit = any(abs(x[-1] - truth[-1]) <= 0.5 for x in rows)
    return {"scope": "one-heldout-BK06-synthetic-episode", "n_heldout": 1,
            "mean_trajectory_mae": round(mae, 6),
            "endpoint_any_sample_within_0p5": endpoint_hit,
            "forecast_digest": _digest(forecast), "truth_digest": _digest(future)}


def native_witness(provider_path: Path, *, seed: int = 148, draws: int = 16) -> dict[str, Any]:
    bk06 = load_pinned_provider(provider_path)
    episodes = bk06.synthetic_events(96, seed)
    train, test = bk06.split_episodes(episodes, 72)
    if {x.episode_id for x in train} & {x.episode_id for x in test}:
        raise BridgeError("episode train/test leakage")
    model = bk06.ConditionalDiffusion.fit(train)
    target = test[0]
    history = history_from_events(target.episode_id, list(target.events[:HISTORY]))
    forecast = predict(model, history, samples=draws, seed=seed + 100)
    scored = score_after_forecast(forecast, list(target.events[HISTORY:]))
    baseline = bk06.ARBaseline.fit(train).forecast(tuple(history["observations"]))
    baseline_mae = sum(abs(float(x) - y) for x, y in zip(baseline, target.future)) / HORIZON
    return {"status": "TESTED_SYNTHETIC_ONLY", "upstream": PROVIDER_COMMIT,
            "provider_blob": PROVIDER_BLOB, "train_episodes": len(train),
            "heldout_episodes_available": len(test), "evaluated_episodes": 1,
            "input": history, "forecast": forecast, "score": scored,
            "baseline_mae": round(baseline_mae, 6),
            "warning": "Not a BK10 count forecast or StarIntel wire adapter"}
