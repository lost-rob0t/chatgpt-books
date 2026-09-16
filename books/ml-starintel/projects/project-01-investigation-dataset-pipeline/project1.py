#!/usr/bin/env python3
"""Reader-facing Project 1 checkpoint for Machine Learning for StarIntel.

This module composes the tested research mechanisms into one deliberate,
offline-capable report.  It does not implement StarIntel server/runtime logic
and it does not promote approximate candidate generation into duplicate truth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
HARNESS = HERE / "research-harness"
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import run_experiments as schema_harness
import run_full_provenance_experiment as provenance_harness
from composite_split_planner import ConstraintEdge, SplitInfeasible, plan_strict_cutoff
from near_duplicate_candidates import DEFAULT_CONFIG, evaluate_candidate_contract
from run_composite_planner_diagnostic import CUTOFF, load_lei
from run_leakage_experiments import generate_duplicate_fixture
from verify_dependency_lock import (
    DIRECT_REQUIREMENTS,
    LOCK_REQUIREMENTS,
    installed_pins,
    parse_pins,
    verify_contract,
)

REPORT_VERSION = "project-01-reader-checkpoint-v1"
DEFAULT_OUTPUT = HERE / "artifacts" / "project-01-reader-report.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_pinned_schema(*, offline: bool) -> dict[str, Any]:
    """Materialize and verify the exact pinned StarIntel schema."""
    cache = HARNESS / ".cache" / "starintel-doc-v0.9.0.schema.json"
    _schema, source = schema_harness.materialize_schema(cache, offline=offline)
    return {
        "status": "TESTED",
        "schema_version": schema_harness.SPEC_VERSION,
        "repository": schema_harness.SCHEMA_REPOSITORY,
        "commit": schema_harness.SCHEMA_COMMIT,
        "path": schema_harness.SCHEMA_PATH,
        "git_blob_sha1": schema_harness.SCHEMA_GIT_BLOB_SHA,
        "materialization_source": source,
    }


def build_environment_report() -> dict[str, Any]:
    """Verify that the live Python environment exactly matches Project 1's lock."""
    direct = parse_pins(DIRECT_REQUIREMENTS)
    locked = parse_pins(LOCK_REQUIREMENTS)
    installed = installed_pins()
    verify_contract(direct, locked, installed)
    return {
        "status": "TESTED",
        "python_version": platform.python_version(),
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
        },
        "direct_pin_count": len(direct),
        "locked_distribution_count": len(locked),
        "installed_distribution_count": len(installed),
        "requirements_lock_sha256": _sha256(LOCK_REQUIREMENTS),
        "claim_scope": (
            "Exact version-lock equality for the live environment only; this is "
            "not a cross-platform or byte-identical artifact claim."
        ),
    }


def build_provenance_report() -> dict[str, Any]:
    """Run the frozen factual GLEIF -> canonical StarIntel provenance checkpoint."""
    result = provenance_harness.run_experiment(validate=True)
    documents = result["documents"]
    validation = result["validation"]
    return {
        "status": result["status"],
        "claim_scope": result["claim_scope"],
        "fixture_id": result["fixture_id"],
        "fixture_tier": result["fixture_tier"],
        "schema_source": result["schema_source"],
        "document_count": result["document_count"],
        "org_count": result["org_count"],
        "relation_count": result["relation_count"],
        "document_ids": sorted(document["_id"] for document in documents),
        "document_types": sorted(document["dtype"] for document in documents),
        "checks": result["checks"],
        "validation_count": len(validation),
        "all_validation_records_valid": all(item["valid"] for item in validation),
        "limitations": result["limitations"],
    }


def build_split_report() -> dict[str, Any]:
    """Exercise the factual strict-cutoff boundary and its deliberate failure case."""
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
            rows,
            graph_edges,
            CUTOFF,
            hard_rule_fields=("entity_id",),
        )
    except SplitInfeasible as exc:
        graph = {
            "status": "infeasible_as_expected",
            "diagnostics": exc.diagnostics,
        }
    else:
        graph = {"status": "unexpectedly_feasible"}

    contamination = clean["diagnostics"]["contamination"]
    return {
        "status": "TESTED",
        "claim_scope": "Factual-fixture split diagnostics only; no model-performance claim.",
        "cutoff": CUTOFF,
        "default_policy": {
            "train_ids": clean["train_ids"],
            "test_ids": clean["test_ids"],
            "component_count": len(clean["components"]),
            "diagnostics": clean["diagnostics"],
        },
        "opt_in_graph_grouping": graph,
        "default_policy_clean": (
            contamination["record_overlap_count"] == 0
            and contamination["composite_group_overlap_count"] == 0
            and all(
                item["overlap_count"] == 0
                for item in contamination["hard_rule_overlaps"].values()
            )
        ),
    }


def build_duplicate_report() -> dict[str, Any]:
    """Evaluate candidate generation against the small exact Tier C oracle."""
    rows = generate_duplicate_fixture()
    result = evaluate_candidate_contract(rows, config=DEFAULT_CONFIG)
    return {
        **result,
        "claim_scope": (
            "Deterministic Tier C control only. Candidate generation proposes pairs; "
            "exact normalized-token Jaccard verification defines duplicate edges."
        ),
    }


def report_invariants(report: dict[str, Any]) -> dict[str, bool]:
    """Return the bounded invariants that make this reader checkpoint green."""
    provenance = report["provenance"]
    split = report["split"]
    duplicate = report["duplicate_candidates"]
    return {
        "environment_lock_verified": report["environment"]["status"] == "TESTED",
        "pinned_schema_verified": report["schema"]["status"] == "TESTED",
        "provenance_roundtrip_verified": (
            provenance["status"] == "TESTED"
            and provenance["all_validation_records_valid"]
            and all(provenance["checks"].values())
        ),
        "default_split_clean": split["default_policy_clean"],
        "graph_failure_exposed": (
            split["opt_in_graph_grouping"]["status"] == "infeasible_as_expected"
        ),
        "candidate_recall_complete_on_tier_c": (
            duplicate["qualifying_pair_recall"] == 1.0
        ),
        "candidate_components_match_exact_oracle": duplicate["component_equality"],
        "candidate_output_permutation_stable": duplicate["input_permutation_equal"],
    }


def build_report(*, offline: bool) -> dict[str, Any]:
    """Build one evidence-first reader report from the already-tested mechanisms."""
    report: dict[str, Any] = {
        "report_version": REPORT_VERSION,
        "scope": (
            "Project 1 reader checkpoint: evidence -> canonical documents -> "
            "experimental admissibility -> split diagnostics -> duplicate verification."
        ),
        "schema": ensure_pinned_schema(offline=offline),
        "environment": build_environment_report(),
        "provenance": build_provenance_report(),
        "split": build_split_report(),
        "duplicate_candidates": build_duplicate_report(),
        "claim_boundaries": [
            "No StarIntel persistence, routing, actor, search, queue, or storage behavior is implemented here.",
            "The GLEIF Tier B fixture is a frozen factual as-of observation, not timeless truth.",
            "The duplicate-candidate measurement is a deterministic Tier C control, not a production scaling result.",
            "Grouped evaluation and historical evaluation remain separate research questions.",
            "This checkpoint does not train or claim a useful production model.",
        ],
    }
    invariants = report_invariants(report)
    report["invariants"] = invariants
    report["status"] = "TESTED" if all(invariants.values()) else "FAILED"
    return report


def write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the ML-StarIntel Project 1 reader checkpoint report."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Refuse network access; requires the pinned schema cache to exist.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Report path (default: {DEFAULT_OUTPUT})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(offline=args.offline)
    write_report(report, args.output)
    print(
        json.dumps(
            {
                "status": report["status"],
                "report_version": report["report_version"],
                "output": str(args.output),
                "invariants": report["invariants"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "TESTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
