"""BK10 v0 frozen-fixture integration boundary.

Pure Python standard library. This is a deterministic heuristic *witness*, not a
trained world model or a StarIntel network/runtime adapter.
"""

from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from typing import Any

CONTRACT = "bk10.capstone.v0"
MAX_OBSERVATIONS = 256
MAX_HTML_BYTES = 16 * 1024
MAX_COUNT = 1_000_000


class ContractError(ValueError):
    """Raised when data or a component crosses an undeclared boundary."""


def _require_keys(value: Any, expected: set[str], context: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ContractError(f"{context}: expected exactly {sorted(expected)}")
    return value


def _int(value: Any, context: str, minimum: int, maximum: int) -> int:
    # bool is an int subclass; accepting it silently would poison evaluation.
    if type(value) is not int or not minimum <= value <= maximum:
        raise ContractError(f"{context}: expected integer in [{minimum}, {maximum}]")
    return value


def _asset(root: Path, name: str, manifest: dict[str, Any]) -> bytes:
    if name not in {"observations.json", "truth.json", "status.html"}:
        raise ContractError("asset: not allowlisted")
    expected = manifest["assets"][name]
    if not isinstance(expected, str) or len(expected) != 64:
        raise ContractError("asset: bad digest declaration")
    contents = (root / "fixtures" / name).read_bytes()
    if hashlib.sha256(contents).hexdigest() != expected:
        raise ContractError(f"asset: frozen digest mismatch: {name}")
    return contents


def read_manifest(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / "fixtures" / "manifest.json").read_text(encoding="utf-8"))
    _require_keys(manifest, {"version", "source", "assets"}, "manifest")
    if manifest["version"] != "bk10.fixture-manifest.v0":
        raise ContractError("manifest: incompatible version")
    _require_keys(manifest["assets"], {"observations.json", "status.html", "truth.json"}, "manifest.assets")
    return manifest


def validate_observations(raw: Any) -> list[dict[str, Any]]:
    _require_keys(raw, {"version", "records"}, "observations")
    if raw["version"] != "bk10.observations.v0":
        raise ContractError("observations: incompatible version")
    records = raw["records"]
    if not isinstance(records, list) or not 2 <= len(records) <= MAX_OBSERVATIONS:
        raise ContractError("observations: expected 2..256 records")
    last_time = -1
    seen_ids: set[str] = set()
    for record in records:
        _require_keys(record, {"document_id", "t", "source", "kind", "count"}, "record")
        if not isinstance(record["document_id"], str) or not record["document_id"].startswith("synthetic:"):
            raise ContractError("record: only synthetic identities are supported")
        if record["document_id"] in seen_ids:
            raise ContractError("record: duplicate document_id")
        seen_ids.add(record["document_id"])
        t = _int(record["t"], "record.t", 0, MAX_OBSERVATIONS)
        if t <= last_time:
            raise ContractError("record: timestamps must be strictly increasing")
        last_time = t
        if record["source"] != "synthetic-counter" or record["kind"] != "count":
            raise ContractError("record: unsupported source/kind")
        _int(record["count"], "record.count", 0, MAX_COUNT)
    return records


def encode_state(records: list[dict[str, Any]], *, observation_digest: str) -> dict[str, Any]:
    # Explicitly no learned parameters, prior future observations, or fitted state.
    latest, previous = records[-1], records[-2]
    return {
        "contract": CONTRACT,
        "estimator": "deterministic-last-two-difference-baseline",
        "as_of": latest["t"],
        "observed_count": latest["count"],
        "delta": latest["count"] - previous["count"],
        "observation_digest": observation_digest,
        "n_observations": len(records),
    }


def candidate_futures(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("contract") != CONTRACT or state.get("estimator") != "deterministic-last-two-difference-baseline":
        raise ContractError("forecast: incompatible encoder state")
    last = _int(state.get("observed_count"), "state.count", 0, MAX_COUNT)
    delta = _int(state.get("delta"), "state.delta", -MAX_COUNT, MAX_COUNT)
    center = min(MAX_COUNT, max(0, last + delta))
    # Hand-specified toy branching weights, not calibrated probabilities.
    candidates = [
        {"candidate_id": "down", "count": max(0, center - 1), "weight_ppm": 250_000},
        {"candidate_id": "center", "count": center, "weight_ppm": 500_000},
        {"candidate_id": "up", "count": min(MAX_COUNT, center + 1), "weight_ppm": 250_000},
    ]
    if sum(x["weight_ppm"] for x in candidates) != 1_000_000:
        raise ContractError("forecast: weights must sum to one million")
    return {
        "contract": CONTRACT,
        "kind": "untrained-heuristic-scenarios",
        "forecast_t": state["as_of"] + 1,
        "candidates": candidates,
        "point_candidate_id": "center",
    }


def request_offline_tool(forecast: dict[str, Any]) -> dict[str, str]:
    if forecast.get("contract") != CONTRACT:
        raise ContractError("policy: forecast contract mismatch")
    # This is a deterministic *policy demonstration*, not an LLM tool call.
    return {
        "contract": CONTRACT,
        "action": "extract_field",
        "page_id": "frozen-status-note",
        "field": "status",
    }


class _FieldParser(HTMLParser):
    def __init__(self, field: str) -> None:
        super().__init__(convert_charrefs=True)
        self.field = field
        self.in_field = False
        self.items: list[str] = []
        self.current: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.in_field:
            raise ContractError("tool: nested HTML inside field")
        if tag == "span" and dict(attrs).get("data-field") == self.field:
            self.in_field = True
            self.current = []

    def handle_data(self, data: str) -> None:
        if self.in_field:
            self.current.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.in_field and tag == "span":
            self.items.append("".join(self.current).strip())
            self.in_field = False


def execute_offline_tool(call: dict[str, str], page: bytes) -> dict[str, str]:
    _require_keys(call, {"contract", "action", "page_id", "field"}, "tool.call")
    if call != {"contract": CONTRACT, "action": "extract_field", "page_id": "frozen-status-note", "field": "status"}:
        raise ContractError("tool: unauthorized operation/page/field")
    if len(page) > MAX_HTML_BYTES:
        raise ContractError("tool: HTML page too large")
    try:
        p = _FieldParser(call["field"])
        p.feed(page.decode("utf-8", errors="strict"))
        p.close()
    except UnicodeError as exc:
        raise ContractError("tool: invalid UTF-8") from exc
    if p.in_field or len(p.items) != 1 or not p.items[0] or len(p.items[0]) > 128:
        raise ContractError("tool: expected exactly one bounded field")
    return {"contract": CONTRACT, "page_id": call["page_id"], "field": call["field"], "value": p.items[0]}


def require_component(components: dict[str, dict[str, Any]], name: str) -> str:
    """An optional model is never replaced silently by the heuristic witness."""
    component = components.get(name)
    if not isinstance(component, dict) or component.get("state") != "tested" or not component.get("commit_sha"):
        raise ContractError(f"component {name}: unavailable (no tested pinned implementation)")
    if component.get("contract") != CONTRACT:
        raise ContractError(f"component {name}: unsupported contract")
    return component["commit_sha"]


def evaluate(forecast: dict[str, Any], truth: Any) -> dict[str, Any]:
    _require_keys(truth, {"version", "t", "count"}, "heldout")
    if truth["version"] != "bk10.heldout.v0":
        raise ContractError("heldout: incompatible version")
    if _int(truth["t"], "heldout.t", 0, MAX_OBSERVATIONS + 1) != forecast["forecast_t"]:
        raise ContractError("heldout: wrong forecast horizon")
    answer = _int(truth["count"], "heldout.count", 0, MAX_COUNT)
    predicted = next(c["count"] for c in forecast["candidates"] if c["candidate_id"] == "center")
    return {
        "scope": "single-synthetic-heldout-example-not-generalization",
        "absolute_error": abs(predicted - answer),
        "candidate_support_contains_truth": answer in {c["count"] for c in forecast["candidates"]},
        "n_heldout": 1,
    }


def run(root: Path) -> dict[str, Any]:
    manifest = read_manifest(root)
    observations_raw = _asset(root, "observations.json", manifest)
    records = validate_observations(json.loads(observations_raw))
    state = encode_state(records, observation_digest=manifest["assets"]["observations.json"])
    forecast = candidate_futures(state)
    tool_call = request_offline_tool(forecast)
    tool_result = execute_offline_tool(tool_call, _asset(root, "status.html", manifest))
    # Truth is touched only after both the forecast and action are frozen.
    ground_truth = json.loads(_asset(root, "truth.json", manifest))
    metrics = evaluate(forecast, ground_truth)
    return {
        "contract": CONTRACT,
        "run_kind": "deterministic-untrained-frozen-synthetic-witness",
        "fixture_sha256": dict(manifest["assets"]),
        "state": state,
        "forecast": forecast,
        "tool_call": tool_call,
        "tool_result": tool_result,
        "metrics": metrics,
        "optional_components_used": [],
    }


def stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
