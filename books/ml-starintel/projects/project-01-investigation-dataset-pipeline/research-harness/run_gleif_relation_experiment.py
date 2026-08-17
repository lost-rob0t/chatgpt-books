#!/usr/bin/env python3
"""D2A: official GLEIF sample -> canonical StarIntel org/relation adapter shape.

This experiment intentionally remains Tier A. GLEIF documents its sample corpus
as testing/format material, so a passing adapter test is not promoted to the
full factual public-observation provenance Experiment D.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import run_experiments as base

HERE = Path(__file__).resolve().parent
FIXTURE_PATH = HERE / "fixtures" / "gleif-official-json-sample-feeder-v1.extract.json"
FIXTURE_SHA256 = "2e150c9ab4573c8788d47e4ed210b6964f154037e59674d99fb838cdc3ed31c3"
SUPPORTING_DOCS_URL = "https://www.gleif.org/en/lei-data/access-and-use-lei-data/supporting-documents"
DATASET = "book1-project1-gleif-official-samples"
TRANSFORM = "book1-gleif-cdf-to-starintel-v1"


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scalar(value: Any) -> Any:
    if isinstance(value, dict) and set(value) == {"$"}:
        return value["$"]
    return value


def load_fixture() -> dict[str, Any]:
    actual = sha256_path(FIXTURE_PATH)
    if actual != FIXTURE_SHA256:
        raise RuntimeError(
            f"frozen GLEIF extract hash mismatch: expected {FIXTURE_SHA256}, got {actual}"
        )
    value = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("GLEIF fixture must be an object")
    return value


def common_document(fixture: dict[str, Any], *, document_id: str, dtype: str, member: str, member_hash: str, original_schema: str, locator: str) -> dict[str, Any]:
    retrieved_at = fixture["retrieved_at"]
    source = fixture["source"]
    return {
        "_id": document_id,
        "dataset": DATASET,
        "dtype": dtype,
        "schema_version": "0.9.0",
        "version": 1,
        "date_added": retrieved_at,
        "date_updated": retrieved_at,
        "sources": [
            {
                "publisher": source["publisher"],
                "url": SUPPORTING_DOCS_URL,
                "retrieved_at": retrieved_at,
                "content_hash": member_hash,
                "hash_algorithm": "sha256",
                "locator": locator,
                "metadata": {
                    "archive_name": source["archive_name"],
                    "archive_sha256": source["archive_sha256"],
                    "member": member,
                    "fixture_tier": fixture["fixture_tier"],
                    "frozen_extract_sha256": FIXTURE_SHA256,
                },
            }
        ],
        "evidence": [],
        "provenance": {
            "imported_from": "GLEIF official current-format JSON sample bundle",
            "original_schema_version": original_schema,
            "original_path": member,
            "transform": TRANSFORM,
            "metadata": {
                "archive_sha256": source["archive_sha256"],
                "source_member_sha256": member_hash,
                "fixture_id": fixture["fixture_id"],
                "fixture_tier": fixture["fixture_tier"],
                "frozen_extract_sha256": FIXTURE_SHA256,
            },
        },
        "data": {},
        "extensions": {
            "ml_starintel": {
                "fixture_id": fixture["fixture_id"],
                "fixture_tier": fixture["fixture_tier"],
                "research_only": True,
            }
        },
    }


def lei_identifier(lei: str) -> dict[str, Any]:
    return {"scheme": "LEI", "value": lei, "canonical": True}


def map_level1_org(fixture: dict[str, Any]) -> dict[str, Any]:
    record = fixture["level1_record"]
    lei = scalar(record["LEI"])
    entity = record["Entity"]
    registration = record["Registration"]
    source = fixture["source"]
    document = common_document(
        fixture,
        document_id=f"gleif-org-{lei}",
        dtype="org",
        member=source["lei_member"],
        member_hash=source["lei_member_sha256"],
        original_schema="LEI-CDF-3.1",
        locator=f"LEI={lei}",
    )
    document["data"] = {
        "name": scalar(entity["LegalName"]),
        "legal_name": scalar(entity["LegalName"]),
        "lei": lei,
        "org_type": scalar(entity.get("EntityCategory", {})),
        "jurisdiction": scalar(entity.get("LegalJurisdiction", {})),
        "country": scalar(entity.get("LegalAddress", {}).get("Country", {})),
        "status": scalar(entity.get("EntityStatus", {})),
        "founded_at": scalar(entity.get("EntityCreationDate", {})),
        "external_ids": [lei_identifier(lei)],
    }
    document["extensions"]["ml_starintel"]["gleif_registration"] = {
        "registration_status": scalar(registration.get("RegistrationStatus", {})),
        "validation_sources": scalar(registration.get("ValidationSources", {})),
        "managing_lou": scalar(registration.get("ManagingLOU", {})),
        "registration_authority": scalar(
            entity.get("RegistrationAuthority", {}).get("RegistrationAuthorityID", {})
        ),
        "registration_authority_entity_id": scalar(
            entity.get("RegistrationAuthority", {}).get("RegistrationAuthorityEntityID", {})
        ),
    }
    return document


def normalize_periods(relationship: dict[str, Any]) -> list[dict[str, Any]]:
    container = relationship.get("RelationshipPeriods", {}).get("RelationshipPeriod", [])
    periods = container if isinstance(container, list) else [container]
    result = []
    for period in periods:
        if not isinstance(period, dict):
            continue
        result.append(
            {
                "period_type": scalar(period.get("PeriodType", {})),
                "start_at": scalar(period.get("StartDate", {})),
                "end_at": scalar(period.get("EndDate", {})) if "EndDate" in period else None,
            }
        )
    return result


def relationship_end_leis(fixture: dict[str, Any]) -> list[str]:
    values = []
    for wrapper in fixture["relationship_records"]:
        relationship = wrapper["RelationshipRecord"]["Relationship"]
        values.append(scalar(relationship["EndNode"]["NodeID"]))
    return values


def endpoint(lei: str, *, unresolved: bool) -> dict[str, Any]:
    return {
        "external_id": lei,
        "dtype": "org",
        "unresolved": unresolved,
        "external_ids": [lei_identifier(lei)],
        "qualifiers": {"identifier_scheme": "LEI"},
    }


def map_relationships(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    source = fixture["source"]
    missing = set(fixture["known_absent_level1_endpoint_leis"])
    documents: list[dict[str, Any]] = []
    for index, wrapper in enumerate(fixture["relationship_records"]):
        record = wrapper["RelationshipRecord"]
        relationship = record["Relationship"]
        registration = record["Registration"]
        start = scalar(relationship["StartNode"]["NodeID"])
        end = scalar(relationship["EndNode"]["NodeID"])
        relationship_type = scalar(relationship["RelationshipType"])
        periods = normalize_periods(relationship)
        relationship_period = next(
            (item for item in periods if item["period_type"] == "RELATIONSHIP_PERIOD"),
            periods[0] if periods else {},
        )
        document = common_document(
            fixture,
            document_id=f"gleif-rel-{index + 1}-{start}-{relationship_type}-{end}",
            dtype="relation",
            member=source["rr_member"],
            member_hash=source["rr_member_sha256"],
            original_schema="RR-CDF-2.1",
            locator=f"relationship[{index}]:{start}:{relationship_type}:{end}",
        )
        document["data"] = {
            "subject": endpoint(start, unresolved=False),
            "predicate": relationship_type,
            "object": endpoint(end, unresolved=end in missing),
            "directed": True,
            "relation_type": relationship_type,
            "start_at": relationship_period.get("start_at"),
            "end_at": relationship_period.get("end_at"),
            "active": scalar(relationship.get("RelationshipStatus", {})) == "ACTIVE",
            "qualifiers": {
                "gleif": {
                    "start_node_type": scalar(relationship["StartNode"]["NodeIDType"]),
                    "end_node_type": scalar(relationship["EndNode"]["NodeIDType"]),
                    "relationship_status": scalar(relationship.get("RelationshipStatus", {})),
                    "periods": periods,
                    "registration_status": scalar(registration.get("RegistrationStatus", {})),
                    "validation_sources": scalar(registration.get("ValidationSources", {})),
                    "validation_documents": scalar(registration.get("ValidationDocuments", {})),
                    "validation_reference": scalar(registration.get("ValidationReference", {})),
                    "managing_lou": scalar(registration.get("ManagingLOU", {})),
                }
            },
        }
        documents.append(document)
    return documents


def run_experiment(*, validate: bool = True) -> dict[str, Any]:
    fixture = load_fixture()
    org = map_level1_org(fixture)
    relations = map_relationships(fixture)
    documents = [org, *relations]

    validation = []
    if validate:
        schema, schema_source = base.materialize_schema(
            HERE / ".cache" / "starintel-doc-v0.9.0.schema.json",
            offline=False,
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

    end_leis = relationship_end_leis(fixture)
    missing = set(fixture["known_absent_level1_endpoint_leis"])
    checks = {
        "frozen_extract_sha256_matches": sha256_path(FIXTURE_PATH) == FIXTURE_SHA256,
        "gleif_relationship_types_preserved": {item["data"]["predicate"] for item in relations}
        == {"IS_FEEDER_TO", "IS_FUND-MANAGED_BY"},
        "missing_level1_endpoints_explicitly_unresolved": all(
            item["data"]["object"]["unresolved"] for item in relations
        ) and set(end_leis) == missing,
        "source_level1_endpoint_resolved": all(
            not item["data"]["subject"]["unresolved"] for item in relations
        ),
        "source_member_hash_lineage_preserved": all(
            item["sources"][0]["content_hash"] == fixture["source"]["rr_member_sha256"]
            for item in relations
        ),
        "json_roundtrip_preserves_documents": json.loads(json.dumps(documents, sort_keys=True)) == documents,
    }
    if validate:
        checks["all_starintel_documents_validate"] = all(item["valid"] for item in validation)

    passed = all(checks.values())
    return {
        "experiment": "D2A",
        "status": "TESTED" if passed else "FAILED",
        "claim_scope": "TIER_A_ADAPTER_SHAPE",
        "full_experiment_d": "UNTESTED",
        "description": "Frozen official GLEIF current-format sample extract -> canonical StarIntel org + relation adapter shape",
        "fixture_sha256": sha256_path(FIXTURE_PATH),
        "fixture_tier": fixture["fixture_tier"],
        "schema_source": schema_source,
        "document_count": len(documents),
        "relation_count": len(relations),
        "relationship_end_leis": end_leis,
        "known_absent_level1_endpoint_leis": sorted(missing),
        "checks": checks,
        "validation": validation,
        "limitations": [
            "GLEIF publishes this sample corpus for format/testing use; passing D2A is not a factual current-ownership claim.",
            "The official JSON sample bundle does not contain Level 1 records for the two feeder relationship endpoints used here.",
            "Full Experiment D requires a frozen factual public observation or explicit augmentation of the missing endpoint records with separate provenance.",
        ],
        "documents": documents,
    }


def main() -> int:
    result = run_experiment(validate=True)
    output = HERE / "artifacts" / "gleif-relation-adapter-experiment.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "TESTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
