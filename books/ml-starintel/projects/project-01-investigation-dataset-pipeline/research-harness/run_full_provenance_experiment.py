#!/usr/bin/env python3
"""Full Experiment D: frozen factual GLEIF API snapshot -> StarIntel 0.9.

The source snapshot is an as-of observation from the primary GLEIF API. This
module performs the transform entirely offline, verifies the frozen canonical
source hashes, produces entity-closed StarIntel org/relation documents, validates
them against the pinned StarIntel 0.9 schema, and checks provenance round trips.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import run_experiments as base

HERE = Path(__file__).resolve().parent
FIXTURE_DIR = HERE / "fixtures" / "gleif-live-2026-08-17"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"
DATASET = "book1-project1-gleif-live-2026-08-17"
TRANSFORM = "book1-gleif-api-to-starintel-v1"
PUBLISHER = "Global Legal Entity Identifier Foundation (GLEIF)"


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def canonical_source_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def load_snapshot() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    records: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, str]] = []
    for name, metadata in manifest["files"].items():
        value = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
        actual = canonical_source_sha256(value)
        expected = metadata["canonical_json_sha256"]
        if actual != expected:
            failures.append({"file": name, "expected": expected, "actual": actual})
        records[name] = value
    if failures:
        raise RuntimeError(f"frozen canonical GLEIF snapshot hash mismatch: {failures}")
    return {"manifest": manifest, "records": records}


def source_entry(snapshot: dict[str, Any], name: str) -> dict[str, Any]:
    metadata = snapshot["manifest"]["files"][name]
    return {
        "publisher": PUBLISHER,
        "url": metadata["requested_url"],
        "retrieved_at": metadata["retrieved_at"],
        "content_hash": metadata["canonical_json_sha256"],
        "hash_algorithm": "sha256",
        "locator": f"fixture:{name}:resource={metadata['resource_id']}",
        "metadata": {
            "source_kind": "canonical-json-snapshot",
            "fixture_id": snapshot["manifest"]["fixture_id"],
            "fixture_tier": snapshot["manifest"]["fixture_tier"],
            "fixture_file": name,
            "raw_response_sha256": metadata["raw_sha256"],
            "canonical_json_sha256": metadata["canonical_json_sha256"],
            "golden_copy_publish_date": snapshot["manifest"]["golden_copy_publish_date"],
            "resource_type": metadata["resource_type"],
            "resource_id": metadata["resource_id"],
        },
    }


def common_document(snapshot: dict[str, Any], *, name: str, document_id: str, dtype: str) -> dict[str, Any]:
    metadata = snapshot["manifest"]["files"][name]
    return {
        "_id": document_id,
        "dataset": DATASET,
        "dtype": dtype,
        "schema_version": "0.9.0",
        "version": 1,
        "date_added": metadata["retrieved_at"],
        "date_updated": metadata["retrieved_at"],
        "sources": [source_entry(snapshot, name)],
        "evidence": [],
        "provenance": {
            "imported_from": "GLEIF API v1 factual as-of snapshot",
            "original_schema_version": "GLEIF API v1 JSON:API",
            "original_path": metadata["requested_url"],
            "transform": TRANSFORM,
            "metadata": {
                "fixture_id": snapshot["manifest"]["fixture_id"],
                "fixture_tier": snapshot["manifest"]["fixture_tier"],
                "fixture_file": name,
                "raw_response_sha256": metadata["raw_sha256"],
                "canonical_json_sha256": metadata["canonical_json_sha256"],
                "golden_copy_publish_date": snapshot["manifest"]["golden_copy_publish_date"],
            },
        },
        "data": {},
        "extensions": {
            "ml_starintel": {
                "fixture_id": snapshot["manifest"]["fixture_id"],
                "fixture_tier": snapshot["manifest"]["fixture_tier"],
                "as_of_snapshot": True,
            }
        },
    }


def lei_identifier(lei: str) -> dict[str, Any]:
    return {"scheme": "LEI", "value": lei, "canonical": True}


def map_org(snapshot: dict[str, Any], name: str) -> dict[str, Any]:
    source = snapshot["records"][name]
    resource = source["data"]
    attributes = resource["attributes"]
    entity = attributes["entity"]
    registration = attributes["registration"]
    lei = attributes["lei"]
    document = common_document(
        snapshot,
        name=name,
        document_id=f"gleif-org-{lei}",
        dtype="org",
    )
    document["data"] = {
        "name": entity["legalName"]["name"],
        "legal_name": entity["legalName"]["name"],
        "lei": lei,
        "org_type": entity.get("category") or "",
        "registration_number": entity.get("registeredAs") or "",
        "jurisdiction": entity.get("jurisdiction") or "",
        "country": (entity.get("legalAddress") or {}).get("country") or "",
        "status": entity.get("status") or "",
        "founded_at": entity.get("creationDate"),
        "external_ids": [lei_identifier(lei)],
    }
    document["extensions"]["ml_starintel"]["gleif"] = {
        "conformity_flag": attributes.get("conformityFlag"),
        "legal_form": entity.get("legalForm"),
        "registered_at": entity.get("registeredAt"),
        "registration": registration,
        "golden_copy": source.get("meta", {}).get("goldenCopy"),
    }
    return document


def map_orgs(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    names = [
        "feeder-lei-record.json",
        "fund-manager-lei-record.json",
        "master-fund-lei-record.json",
    ]
    return [map_org(snapshot, name) for name in names]


def endpoint(lei: str, org_by_lei: dict[str, dict[str, Any]]) -> dict[str, Any]:
    document = org_by_lei.get(lei)
    return {
        "document_id": document["_id"] if document else "",
        "external_id": lei,
        "dtype": "org",
        "name": document["data"]["legal_name"] if document else "",
        "unresolved": document is None,
        "external_ids": [lei_identifier(lei)],
        "qualifiers": {"identifier_scheme": "LEI"},
    }


def relationship_period(attributes: dict[str, Any]) -> tuple[str | None, str | None, list[dict[str, Any]]]:
    periods = attributes["relationship"].get("periods") or []
    normalized = [
        {
            "period_type": item.get("type"),
            "start_at": item.get("startDate"),
            "end_at": item.get("endDate"),
        }
        for item in periods
        if isinstance(item, dict)
    ]
    main = next(
        (item for item in normalized if item["period_type"] == "RELATIONSHIP_PERIOD"),
        normalized[0] if normalized else {},
    )
    return main.get("start_at"), main.get("end_at"), normalized


def map_relationship(snapshot: dict[str, Any], name: str, org_by_lei: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source = snapshot["records"][name]
    resource = source["data"]
    attributes = resource["attributes"]
    relationship = attributes["relationship"]
    registration = attributes["registration"]
    start = relationship["startNode"]["id"]
    end = relationship["endNode"]["id"]
    predicate = relationship["type"]
    start_at, end_at, periods = relationship_period(attributes)
    digest = hashlib.sha256(resource["id"].encode("utf-8")).hexdigest()[:20]
    document = common_document(
        snapshot,
        name=name,
        document_id=f"gleif-rel-{digest}",
        dtype="relation",
    )
    document["data"] = {
        "subject": endpoint(start, org_by_lei),
        "predicate": predicate,
        "object": endpoint(end, org_by_lei),
        "directed": True,
        "relation_type": predicate,
        "start_at": start_at,
        "end_at": end_at,
        "active": relationship.get("status") == "ACTIVE",
        "qualifiers": {
            "gleif": {
                "api_relationship_record_id": resource["id"],
                "start_node_type": relationship["startNode"].get("type"),
                "end_node_type": relationship["endNode"].get("type"),
                "relationship_status": relationship.get("status"),
                "periods": periods,
                "valid_from": attributes.get("validFrom"),
                "valid_to": attributes.get("validTo"),
                "registration": registration,
                "golden_copy": source.get("meta", {}).get("goldenCopy"),
            }
        },
    }
    return document


def map_relationships(snapshot: dict[str, Any], orgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    org_by_lei = {document["data"]["lei"]: document for document in orgs}
    names = [
        "fund-manager-relationship-record.json",
        "master-fund-relationship-record.json",
    ]
    return [map_relationship(snapshot, name, org_by_lei) for name in names]


def document_source_hashes_reconstructable(snapshot: dict[str, Any], documents: list[dict[str, Any]]) -> bool:
    files = snapshot["manifest"]["files"]
    for document in documents:
        source = document["sources"][0]
        name = source["metadata"]["fixture_file"]
        if name not in files:
            return False
        metadata = files[name]
        if source["content_hash"] != metadata["canonical_json_sha256"]:
            return False
        if source["metadata"]["raw_response_sha256"] != metadata["raw_sha256"]:
            return False
        if canonical_source_sha256(snapshot["records"][name]) != metadata["canonical_json_sha256"]:
            return False
    return True


def run_experiment(*, validate: bool = True) -> dict[str, Any]:
    snapshot = load_snapshot()
    orgs = map_orgs(snapshot)
    relations = map_relationships(snapshot, orgs)
    documents = [*orgs, *relations]
    org_leis = {document["data"]["lei"] for document in orgs}
    endpoints = {
        endpoint_value
        for document in relations
        for endpoint_value in (
            document["data"]["subject"]["external_id"],
            document["data"]["object"]["external_id"],
        )
    }

    validation: list[dict[str, Any]] = []
    if validate:
        schema, schema_source = base.materialize_schema(
            HERE / ".cache" / "starintel-doc-v0.9.0.schema.json",
            offline=True,
        )
        for document in documents:
            valid, category, message = base.validate_document(document, schema)
            validation.append(
                {
                    "id": document["_id"],
                    "dtype": document["dtype"],
                    "valid": valid,
                    "category": category,
                    "message": message,
                }
            )
    else:
        schema_source = "not-run"

    checks = {
        "frozen_canonical_source_hashes_match": all(
            canonical_source_sha256(snapshot["records"][name]) == metadata["canonical_json_sha256"]
            for name, metadata in snapshot["manifest"]["files"].items()
        ),
        "entity_closed": endpoints <= org_leis,
        "all_relationship_endpoints_resolved": all(
            not document["data"][side]["unresolved"]
            for document in relations
            for side in ("subject", "object")
        ),
        "primary_relationship_types_preserved": {
            document["data"]["predicate"] for document in relations
        } == {"IS_FEEDER_TO", "IS_FUND-MANAGED_BY"},
        "all_source_hashes_reconstructable": document_source_hashes_reconstructable(snapshot, documents),
        "json_roundtrip_preserves_documents": json.loads(json.dumps(documents, sort_keys=True)) == documents,
    }
    if validate:
        checks["all_starintel_documents_validate"] = all(item["valid"] for item in validation)

    passed = all(checks.values())
    return {
        "experiment": "D",
        "status": "TESTED" if passed else "FAILED",
        "claim_scope": "TIER_B_FACTUAL_AS_OF_PROVENANCE_ROUNDTRIP",
        "description": "Frozen factual GLEIF API as-of snapshot -> entity-closed canonical StarIntel org/relation documents -> offline provenance reconstruction",
        "fixture_id": snapshot["manifest"]["fixture_id"],
        "fixture_tier": snapshot["manifest"]["fixture_tier"],
        "schema_source": schema_source,
        "document_count": len(documents),
        "org_count": len(orgs),
        "relation_count": len(relations),
        "checks": checks,
        "validation": validation,
        "source_manifest": snapshot["manifest"],
        "limitations": [
            "This experiment establishes reproducibility of one factual as-of GLEIF snapshot; it does not claim the relationships are timeless.",
            "Committed source files are canonical parsed JSON snapshots; exact raw response hashes are preserved from the acquisition run and raw bytes remain in that CI artifact.",
            "This experiment does not test model leakage, prediction quality, or cross-language StarIntel conformance.",
        ],
        "documents": documents,
    }


def main() -> int:
    result = run_experiment(validate=True)
    output = HERE / "artifacts" / "full-provenance-experiment.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "TESTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
