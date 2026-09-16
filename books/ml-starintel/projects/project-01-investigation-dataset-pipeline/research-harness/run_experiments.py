#!/usr/bin/env python3
"""Executable foundational experiments for Book 1 Project 1.

This harness deliberately does not implement a StarIntel server or a second schema.
It materializes the exact pinned upstream schema, verifies its Git blob identity,
and applies the same Draft 2020-12 validation model used by starintel-doc's
Python v0.9 adapter.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sys
import urllib.request
from copy import deepcopy
from datetime import datetime, timezone
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

SCHEMA_REPOSITORY = "lost-rob0t/starintel-gpt-auto-dig"
SCHEMA_COMMIT = "ff814ff63868286d68e21502122832802cd5e361"
SCHEMA_PATH = "schemas/starintel-doc-v0.9.0.schema.json"
SCHEMA_GIT_BLOB_SHA = "b26d62644c675e2d55f4ea95f8ec207cfb08ae9a"
SCHEMA_URL = (
    "https://raw.githubusercontent.com/"
    f"{SCHEMA_REPOSITORY}/{SCHEMA_COMMIT}/{SCHEMA_PATH}"
)
SPEC_VERSION = "0.9.0"
ALIASES = {
    "organization",
    "organisation",
    "investigation_target",
    "social_media_post",
    "email_message",
    "financial_observation",
    "research_pass",
    "dataset_manifest",
    "actor_manifest",
    "legal_case",
    "lobbying_filing",
    "campaign_finance",
}
RFC3339_ZONE = re.compile(r"(?:Z|[+-]\d{2}:\d{2})$")
FORMAT_CHECKER = FormatChecker()


@FORMAT_CHECKER.checks("date-time", raises=(TypeError, ValueError))
def valid_rfc3339_datetime(value: object) -> bool:
    if not isinstance(value, str) or RFC3339_ZONE.search(value) is None:
        return False
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.tzinfo is not None


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def materialize_schema(path: Path, offline: bool) -> tuple[dict[str, Any], str]:
    if path.exists():
        raw = path.read_bytes()
        source = "cache"
    else:
        if offline:
            raise RuntimeError(f"schema cache missing in offline mode: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(SCHEMA_URL, timeout=30) as response:
            raw = response.read()
        path.write_bytes(raw)
        source = "pinned-upstream"

    actual = git_blob_sha(raw)
    if actual != SCHEMA_GIT_BLOB_SHA:
        raise RuntimeError(
            "canonical schema blob mismatch: "
            f"expected {SCHEMA_GIT_BLOB_SHA}, got {actual}"
        )

    schema = json.loads(raw)
    if not isinstance(schema, dict):
        raise RuntimeError("canonical schema is not a JSON object")
    return schema, source


def dtype_schemas(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for branch in schema.get("allOf", []):
        dtype = branch.get("if", {}).get("properties", {}).get("dtype", {}).get("const")
        data = branch.get("then", {}).get("properties", {}).get("data")
        if isinstance(dtype, str) and isinstance(data, dict):
            result[dtype] = data
    return result


def category_for(error: JsonSchemaValidationError) -> str:
    if error.validator == "required":
        return "missing_required_field"
    if error.validator == "additionalProperties":
        return "undeclared_field"
    if error.validator == "format":
        return "invalid_datetime"
    if error.validator == "minimum":
        return "below_minimum"
    if error.validator == "maximum":
        return "above_maximum"
    if error.validator == "pattern":
        return "pattern_mismatch"
    if error.validator == "enum":
        return "invalid_enum"
    if error.validator == "const":
        return (
            "unsupported_spec_version"
            if list(error.absolute_path) == ["schema_version"]
            else "invalid_constant"
        )
    if error.validator in {"type", "anyOf"}:
        return "wrong_type"
    return "validation_error"


def validate_document(document: dict[str, Any], schema: dict[str, Any]) -> tuple[bool, str | None, str | None]:
    if not isinstance(document, dict):
        return False, "wrong_type", "$: expected object"
    if document.get("schema_version") != SPEC_VERSION:
        return False, "unsupported_spec_version", "unsupported spec version"

    types = dtype_schemas(schema)
    dtype = document.get("dtype")
    if isinstance(dtype, str) and dtype not in types:
        if dtype in ALIASES:
            return False, "invalid_enum", "$.dtype: alias is not canonical"
        return False, "unknown_object_type", f"$.dtype: unknown document type {dtype!r}"

    errors = sorted(
        Draft202012Validator(schema, format_checker=FORMAT_CHECKER).iter_errors(document),
        key=lambda item: (tuple(map(str, item.absolute_path)), item.message),
    )
    if not errors:
        return True, None, None

    error = errors[0]
    path = "$" + "".join(
        f"[{part}]" if isinstance(part, int) else f".{part}"
        for part in error.absolute_path
    )
    return False, category_for(error), f"{path}: {error.message}"


def base_document() -> dict[str, Any]:
    return {
        "_id": "book1-person-valid-001",
        "dataset": "book1-project1-research",
        "dtype": "person",
        "schema_version": SPEC_VERSION,
        "version": 1,
        "date_added": "2026-08-14T14:00:00Z",
        "date_updated": "2026-08-14T14:00:00Z",
        "sources": [],
        "evidence": [],
        "data": {},
        "extensions": {
            "ml_starintel": {
                "fixture_id": "person-valid-v1",
                "research_only": True,
            }
        },
    }


def experiment_e(schema: dict[str, Any]) -> dict[str, Any]:
    positive = base_document()
    extension_roundtrip = json.loads(json.dumps(positive, sort_keys=True))

    cases: list[tuple[str, dict[str, Any], bool, str | None]] = [
        ("valid_person_minimal", positive, True, None),
        ("valid_namespaced_extension", extension_roundtrip, True, None),
    ]

    missing_dataset = deepcopy(positive)
    missing_dataset.pop("dataset")
    cases.append(("missing_required_dataset", missing_dataset, False, "missing_required_field"))

    undeclared = deepcopy(positive)
    undeclared["book1_unknown_top_level"] = True
    cases.append(("undeclared_top_level", undeclared, False, "undeclared_field"))

    bad_date = deepcopy(positive)
    bad_date["date_added"] = "2026-08-14T14:00:00"
    cases.append(("datetime_without_zone", bad_date, False, "invalid_datetime"))

    alias = deepcopy(positive)
    alias["dtype"] = "organization"
    cases.append(("legacy_alias_dtype", alias, False, "invalid_enum"))

    bad_spec_version = deepcopy(positive)
    bad_spec_version["schema_version"] = "0.8.0"
    cases.append(("wrong_schema_version", bad_spec_version, False, "unsupported_spec_version"))

    bad_document_version = deepcopy(positive)
    bad_document_version["version"] = "0.9.0"
    cases.append(("wrong_document_version_type", bad_document_version, False, "wrong_type"))

    wrong_data_type = deepcopy(positive)
    wrong_data_type["data"] = []
    cases.append(("wrong_data_type", wrong_data_type, False, "wrong_type"))

    results: list[dict[str, Any]] = []
    failed = 0
    for name, document, expected_valid, expected_category in cases:
        valid, category, message = validate_document(document, schema)
        passed = valid == expected_valid and (
            expected_category is None or category == expected_category
        )
        if not passed:
            failed += 1
        results.append(
            {
                "name": name,
                "expected_valid": expected_valid,
                "expected_category": expected_category,
                "actual_valid": valid,
                "actual_category": category,
                "message": message,
                "passed": passed,
            }
        )

    roundtrip_passed = extension_roundtrip == positive
    if not roundtrip_passed:
        failed += 1

    return {
        "experiment": "E",
        "status": "TESTED" if failed == 0 else "FAILED",
        "description": "Pinned StarIntel 0.9 schema conformance smoke matrix",
        "cases": results,
        "roundtrip_preserved_document": roundtrip_passed,
        "failed_checks": failed,
    }


def experiment_d0(schema: dict[str, Any]) -> dict[str, Any]:
    """A narrow provenance-harness round trip, not the full GLEIF provenance experiment."""
    document = base_document()
    valid, category, message = validate_document(document, schema)

    manifest = {
        "record_id": document["_id"],
        "source": {
            "repository": SCHEMA_REPOSITORY,
            "commit": SCHEMA_COMMIT,
            "path": SCHEMA_PATH,
            "git_blob_sha": SCHEMA_GIT_BLOB_SHA,
        },
        "transform": {
            "name": "project1-research-minimal-person",
            "parameters": {"synthetic": True},
        },
        "schema": {"version": SPEC_VERSION, "commit": SCHEMA_COMMIT},
        "split": {"name": "research-only", "membership": "unsplit"},
    }
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    decoded = json.loads(encoded)

    required_paths = [
        ("record_id",),
        ("source", "repository"),
        ("source", "commit"),
        ("source", "git_blob_sha"),
        ("transform", "name"),
        ("schema", "version"),
        ("split", "membership"),
    ]
    missing = []
    for path in required_paths:
        value: Any = decoded
        for key in path:
            if not isinstance(value, dict) or key not in value:
                missing.append(".".join(path))
                break
            value = value[key]

    passed = valid and decoded == manifest and not missing
    return {
        "experiment": "D0",
        "status": "TESTED" if passed else "FAILED",
        "description": "Research-harness provenance manifest round trip; full Project 1 source provenance remains UNTESTED",
        "canonical_document_valid": valid,
        "validation_category": category,
        "validation_message": message,
        "manifest_roundtrip_equal": decoded == manifest,
        "missing_required_manifest_paths": missing,
    }


def environment_record(schema_source: str) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "jsonschema": package_version("jsonschema"),
        "schema_source": schema_source,
        "schema_repository": SCHEMA_REPOSITORY,
        "schema_commit": SCHEMA_COMMIT,
        "schema_path": SCHEMA_PATH,
        "schema_git_blob_sha": SCHEMA_GIT_BLOB_SHA,
        "github_sha": os.environ.get("GITHUB_SHA"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--schema-cache",
        type=Path,
        default=Path(__file__).resolve().parent / ".cache" / "starintel-doc-v0.9.0.schema.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "artifacts" / "experiments.json",
    )
    parser.add_argument("--offline", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    schema, source = materialize_schema(args.schema_cache, args.offline)
    result = {
        "claim_status": {
            "experiment_e": "TESTED",
            "experiment_d0": "TESTED",
            "full_experiment_d": "UNTESTED",
            "experiments_a_b_c": "UNTESTED",
        },
        "environment": environment_record(source),
        "experiment_e": experiment_e(schema),
        "experiment_d0": experiment_d0(schema),
    }
    failed = (
        result["experiment_e"]["status"] == "FAILED"
        or result["experiment_d0"]["status"] == "FAILED"
    )
    if failed:
        result["claim_status"]["experiment_e"] = result["experiment_e"]["status"]
        result["claim_status"]["experiment_d0"] = result["experiment_d0"]["status"]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
