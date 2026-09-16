#!/usr/bin/env python3
"""Freeze a factual as-of GLEIF API snapshot for the Book 1 feeder fixture.

The snapshot is intentionally separate from GLEIF's illustrative sample bundle.
It follows only relationship links returned by api.gleif.org and records both
raw response hashes and canonical parsed-JSON hashes. A snapshot is evidence of
what the API returned at retrieval time, not a timeless ownership assertion.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

FEEDER_LEI = "6354009BJOFO62XYIX17"
API_ROOT = "https://api.gleif.org/api/v1"
FEEDER_URL = f"{API_ROOT}/lei-records/{FEEDER_LEI}"
TARGET_RELATIONSHIPS = ("master-fund", "fund-manager")
USER_AGENT = "chatgpt-books-ml-starintel-research/1.0"
HERE = Path(__file__).resolve().parent


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def safe_api_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "api.gleif.org"
        and parsed.path.startswith("/api/v1/")
        and parsed.username is None
        and parsed.password is None
    )


def fetch_json(url: str) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    if not safe_api_url(url):
        raise ValueError(f"refusing non-GLEIF API URL: {url!r}")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.api+json",
            "User-Agent": USER_AGENT,
        },
    )
    retrieved_at = datetime.now(timezone.utc).isoformat()
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - allowlisted official API
        raw = response.read()
        metadata = {
            "requested_url": url,
            "final_url": response.geturl(),
            "status": response.status,
            "content_type": response.headers.get("Content-Type"),
            "retrieved_at": retrieved_at,
            "size_bytes": len(raw),
            "raw_sha256": sha256_bytes(raw),
        }
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise TypeError(f"GLEIF API response must be an object: {url}")
    metadata["canonical_json_sha256"] = sha256_bytes(canonical_json_bytes(parsed))
    return parsed, metadata, raw


def extract_target_links(response: dict[str, Any]) -> dict[str, dict[str, str]]:
    data = response.get("data", {})
    if not isinstance(data, dict):
        return {}
    relationships = data.get("relationships", {})
    if not isinstance(relationships, dict):
        return {}

    result: dict[str, dict[str, str]] = {}
    for name in TARGET_RELATIONSHIPS:
        relation = relationships.get(name)
        if not isinstance(relation, dict):
            continue
        links = relation.get("links", {})
        if not isinstance(links, dict):
            continue
        safe_links = {
            key: value
            for key, value in links.items()
            if isinstance(value, str) and safe_api_url(value)
        }
        if safe_links:
            result[name] = safe_links
    return result


def resource_summary(value: dict[str, Any]) -> dict[str, Any]:
    data = value.get("data")
    if isinstance(data, dict):
        return {"type": data.get("type"), "id": data.get("id")}
    if isinstance(data, list):
        return {
            "type": "collection",
            "count": len(data),
            "ids": [item.get("id") for item in data if isinstance(item, dict)],
        }
    return {"type": type(data).__name__}


def main() -> int:
    output_dir = HERE / "artifacts" / "gleif-live-snapshot"
    raw_dir = output_dir / "raw"
    canonical_dir = output_dir / "canonical"
    raw_dir.mkdir(parents=True, exist_ok=True)
    canonical_dir.mkdir(parents=True, exist_ok=True)

    try:
        feeder, feeder_meta, feeder_raw = fetch_json(FEEDER_URL)
        feeder_data = feeder.get("data", {})
        if not isinstance(feeder_data, dict) or feeder_data.get("id") != FEEDER_LEI:
            raise RuntimeError("GLEIF API feeder response did not return the requested LEI resource")

        raw_dir.joinpath("feeder-lei-record.json").write_bytes(feeder_raw)
        canonical_dir.joinpath("feeder-lei-record.json").write_bytes(canonical_json_bytes(feeder))

        links = extract_target_links(feeder)
        followed: dict[str, dict[str, Any]] = {}
        for relationship_name, relationship_links in sorted(links.items()):
            followed[relationship_name] = {}
            for link_name, url in sorted(relationship_links.items()):
                parsed, metadata, raw = fetch_json(url)
                stem = f"{relationship_name}-{link_name}"
                raw_dir.joinpath(f"{stem}.json").write_bytes(raw)
                canonical_dir.joinpath(f"{stem}.json").write_bytes(canonical_json_bytes(parsed))
                followed[relationship_name][link_name] = {
                    "url": url,
                    "metadata": metadata,
                    "resource": resource_summary(parsed),
                }

        required_present = all(
            name in followed
            and "lei-record" in followed[name]
            and "relationship-record" in followed[name]
            for name in TARGET_RELATIONSHIPS
        )
        result = {
            "experiment": "GLEIF_LIVE_SNAPSHOT",
            "status": "TESTED" if required_present else "FAILED",
            "claim_scope": "TIER_B_FACTUAL_AS_OF_SNAPSHOT_ACQUISITION",
            "source_lei": FEEDER_LEI,
            "source": {
                "url": FEEDER_URL,
                "metadata": feeder_meta,
                "resource": resource_summary(feeder),
            },
            "relationship_links": links,
            "followed_resources": followed,
            "required_relationship_resources_present": required_present,
            "limitations": [
                "This records the GLEIF API state at retrieval time and must not be treated as timeless truth.",
                "The API is the primary source for this Tier B snapshot; illustrative sample-bundle semantics remain a separate Tier A fixture.",
                "Full Experiment D is not complete until these frozen responses are mapped, validated, and their provenance is reconstructed offline.",
            ],
        }
        exit_code = 0 if required_present else 1
    except Exception as error:
        result = {
            "experiment": "GLEIF_LIVE_SNAPSHOT",
            "status": "FAILED",
            "claim_scope": "TIER_B_FACTUAL_AS_OF_SNAPSHOT_ACQUISITION",
            "source_lei": FEEDER_LEI,
            "error": f"{type(error).__name__}: {error}",
        }
        exit_code = 1

    output_dir.joinpath("manifest.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
