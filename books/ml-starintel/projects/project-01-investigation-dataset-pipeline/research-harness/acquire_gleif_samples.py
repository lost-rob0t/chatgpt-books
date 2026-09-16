#!/usr/bin/env python3
"""Acquire and inventory GLEIF's official current-format JSON sample archive.

This helper does not interpret GLEIF relationship semantics or claim that the
samples are factual current observations. It freezes source identity and finds
candidate members for the next Project 1 provenance experiment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SOURCE_URL = (
    "https://www.gleif.org/lei-data/access-and-use-lei-data/supporting-documents/"
    "2021-11-23_lei-cdf-3.1-and-rr-cdf-2.1-and-repex-cdf-2.1-json-samples_v1.1-final.zip"
)
TARGET_LEIS = (
    "635400OCWIKPSEDOHY65",  # Sample 1: umbrella structure / master fund
    "6354009BJOFO62XYIX17",  # Sample 2: master/feeder
    "635400G9OA8AFLAKAL93",  # Sample 1 documented sibling sub-fund
)
USER_AGENT = "chatgpt-books-ml-starintel-research/1.0"
HERE = Path(__file__).resolve().parent


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def recursive_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from recursive_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from recursive_strings(item)


def download_archive(destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        SOURCE_URL,
        headers={
            "Accept": "application/zip,application/octet-stream;q=0.9,*/*;q=0.1",
            "User-Agent": USER_AGENT,
        },
    )
    retrieved_at = datetime.now(timezone.utc).isoformat()
    with urllib.request.urlopen(request, timeout=90) as response:  # noqa: S310 - fixed official URL
        payload = response.read()
        content_type = response.headers.get("Content-Type")
        final_url = response.geturl()
    if not payload.startswith(b"PK"):
        raise RuntimeError(f"GLEIF response is not a ZIP archive: content-type={content_type!r}")
    destination.write_bytes(payload)
    return {
        "source_url": SOURCE_URL,
        "final_url": final_url,
        "retrieved_at": retrieved_at,
        "content_type": content_type,
        "size_bytes": len(payload),
        "sha256": sha256_bytes(payload),
    }


def member_record(name: str, payload: bytes) -> dict[str, Any]:
    record: dict[str, Any] = {
        "name": name,
        "size_bytes": len(payload),
        "sha256": sha256_bytes(payload),
        "json_status": "NOT_JSON",
        "matched_leis": [],
        "relationship_types": [],
    }
    if not name.lower().endswith(".json"):
        return record
    try:
        value = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        record["json_status"] = "FAILED"
        record["json_error"] = f"{type(error).__name__}: {error}"
        return record

    strings = list(recursive_strings(value))
    string_set = set(strings)
    record["json_status"] = "PARSED"
    record["matched_leis"] = [lei for lei in TARGET_LEIS if lei in string_set]
    record["relationship_types"] = sorted(
        {item for item in string_set if item.startswith("IS_") and item == item.upper()}
    )
    return record


def safe_extract_member(handle: zipfile.ZipFile, name: str, root: Path) -> Path:
    target = (root / name).resolve()
    root_resolved = root.resolve()
    if root_resolved not in target.parents and target != root_resolved:
        raise ValueError(f"unsafe ZIP member path: {name!r}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with handle.open(name) as source, target.open("wb") as destination:
        shutil.copyfileobj(source, destination)
    return target


def collect_inventory(archive: Path, selected_dir: Path) -> dict[str, Any]:
    members: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    selected_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive) as handle:
        for info in sorted(handle.infolist(), key=lambda item: item.filename):
            if info.is_dir():
                continue
            payload = handle.read(info.filename)
            record = member_record(info.filename, payload)
            members.append(record)
            if record["matched_leis"]:
                extracted = safe_extract_member(handle, info.filename, selected_dir)
                selected_record = dict(record)
                selected_record["extracted_path"] = str(extracted.relative_to(selected_dir))
                selected.append(selected_record)

    return {
        "experiment": "GLEIF_SAMPLE_ACQUISITION",
        "status": "TESTED",
        "archive_path": str(archive),
        "archive_sha256": sha256_path(archive),
        "archive_size_bytes": archive.stat().st_size,
        "target_leis": list(TARGET_LEIS),
        "members": members,
        "selected_members": selected,
        "limitations": [
            "Inventory success does not make the sample contents current factual observations.",
            "GLEIF documents the sample corpus as testing material; some samples are illustrative and some derive from real-world examples.",
            "No StarIntel relation mapping or full Experiment D claim is made by this acquisition helper.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=HERE / "artifacts" / "gleif-sample-acquisition.json",
    )
    parser.add_argument(
        "--selected-dir",
        type=Path,
        default=HERE / "artifacts" / "gleif-selected-members",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    archive = args.archive or HERE / ".cache" / "gleif-current-format-json-samples.zip"
    acquisition: dict[str, Any]
    try:
        if args.archive is None:
            acquisition = download_archive(archive)
        else:
            acquisition = {
                "source_url": SOURCE_URL,
                "retrieved_at": None,
                "sha256": sha256_path(archive),
                "size_bytes": archive.stat().st_size,
                "mode": "offline",
            }
        inventory = collect_inventory(archive, args.selected_dir)
        result = {"acquisition": acquisition, **inventory}
        exit_code = 0
    except Exception as error:  # preserve the real failure as a research artifact
        result = {
            "experiment": "GLEIF_SAMPLE_ACQUISITION",
            "status": "FAILED",
            "source_url": SOURCE_URL,
            "error": f"{type(error).__name__}: {error}",
        }
        exit_code = 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
