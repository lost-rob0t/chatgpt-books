#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from composite_split_planner import ConstraintEdge, SplitInfeasible, plan_strict_cutoff

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "gleif-live-2026-08-17"
OUT = HERE / "artifacts" / "composite-planner-gleif.json"
CUTOFF = "2026-07-01T00:00:00Z"


def load_lei(name: str) -> dict:
    payload = json.loads((FIXTURE / name).read_text())
    data = payload["data"]
    observed = data["attributes"]["registration"]["lastUpdateDate"]
    return {
        "record_id": data["id"],
        "entity_id": data["id"],
        "observed_at": observed,
        "prediction_at": observed,
        "features": [],
    }


def main() -> None:
    rows = [
        load_lei("feeder-lei-record.json"),
        load_lei("master-fund-lei-record.json"),
        load_lei("fund-manager-lei-record.json"),
    ]
    clean = plan_strict_cutoff(rows, [], CUTOFF, hard_rule_fields=("entity_id",))
    feeder, master, manager = [row["record_id"] for row in rows]
    graph_edges = [
        ConstraintEdge(feeder, master, "selected_gleif_fund_relation"),
        ConstraintEdge(feeder, manager, "selected_gleif_fund_relation"),
    ]
    try:
        plan_strict_cutoff(
            rows, graph_edges, CUTOFF, hard_rule_fields=("entity_id",)
        )
        graph = {"status": "unexpectedly_feasible"}
    except SplitInfeasible as exc:
        graph = {
            "status": "infeasible_as_expected",
            "diagnostics": exc.diagnostics,
        }

    result = {
        "experiment": "composite-planner-factual-diagnostic-v1",
        "fixture": "gleif-live-2026-08-17",
        "cutoff": CUTOFF,
        "claim_scope": "contamination diagnostics only; no model-performance claim",
        "default_policy": {
            "status": "TESTED",
            "train_ids": clean["train_ids"],
            "test_ids": clean["test_ids"],
            "diagnostics": clean["diagnostics"],
        },
        "opt_in_graph_grouping": graph,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
