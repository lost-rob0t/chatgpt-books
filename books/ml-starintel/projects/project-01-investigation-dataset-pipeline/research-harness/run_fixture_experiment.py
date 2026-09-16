#!/usr/bin/env python3
"""Experiment D1: frozen public-source provenance round trip for Project 1."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import run_experiments as base

HERE = Path(__file__).resolve().parent
RAW_PATH = HERE / "fixtures" / "gleif-public-self-record-v1.raw.json"
NORMALIZED_PATH = HERE / "fixtures" / "gleif-public-self-record-v1.starintel.json"
RAW_SHA256 = "3785689e0d5e768d0adfa4838540646b815b5df4e32c2619abc51b1419584c4f"
NORMALIZED_SHA256 = "0e433da6b856a48378b011786dd49f4edc1d771eddca936d681bae703ebf85b2"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    schema, schema_source = base.materialize_schema(
        HERE / ".cache" / "starintel-doc-v0.9.0.schema.json",
        offline=False,
    )
    raw = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    normalized = json.loads(NORMALIZED_PATH.read_text(encoding="utf-8"))

    raw_hash = sha256(RAW_PATH)
    normalized_hash = sha256(NORMALIZED_PATH)
    valid, category, message = base.validate_document(normalized, schema)

    source = normalized["sources"][0]
    extension = normalized["extensions"]["ml_starintel"]
    reconstructable = all(
        [
            raw["record"]["lei"] == normalized["data"]["lei"],
            raw["record"]["legal_name"] == normalized["data"]["legal_name"],
            raw["source"]["url"] == source["url"],
            raw["source"]["license"] == source["license"],
            source["content_hash"] == raw_hash,
            source["hash_algorithm"] == "sha256",
            extension["raw_sha256"] == raw_hash,
            extension["fixture_id"] == raw["fixture_id"],
        ]
    )

    checks = {
        "raw_sha256_matches_frozen_value": raw_hash == RAW_SHA256,
        "normalized_sha256_matches_frozen_value": normalized_hash == NORMALIZED_SHA256,
        "normalized_starintel_record_valid": valid,
        "source_and_transform_provenance_reconstructable": reconstructable,
        "fixture_lei_matches_official_source_extract": raw["record"]["lei"] == "506700GE1G29325QX363",
    }
    passed = all(checks.values())
    result = {
        "experiment": "D1",
        "status": "TESTED" if passed else "FAILED",
        "description": "Frozen public GLEIF self-record source extract -> normalized StarIntel org -> provenance reconstruction",
        "schema_source": schema_source,
        "raw_sha256": raw_hash,
        "normalized_sha256": normalized_hash,
        "validation_category": category,
        "validation_message": message,
        "checks": checks,
        "limitations": [
            "This is a frozen official GLEIF contact-page extract, not yet the final Level 1/Level 2 API fixture.",
            "No live upstream lookup is required to rerun the fixture test.",
            "Experiments A-C remain separate and untested here.",
        ],
    }
    output = HERE / "artifacts" / "fixture-experiment.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
