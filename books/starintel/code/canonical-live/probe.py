#!/usr/bin/env python3
"""P0 book lab: verify canonical StarIntel 0.10.1 over the real disposable stack.

This is a read-only teaching harness with respect to production systems: the
caller must supply the disposable test-stack URL and credential in environment
variables. The only writes are isolated synthetic records into that test stack.
It never stores HTTP bodies, credentials, or actor/private state in its report.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol


SCHEMA_VERSION = "0.10.1"
AUTHORITY = "org.starintel/core@1"
FIXTURES = Path(__file__).resolve().parents[1] / "canonical-records" / "fixtures"
FORBIDDEN_EGRESS = frozenset({"_id", "_rev", "tenant_id", "schema_version"})


class ProbeError(RuntimeError):
    """A bounded assertion failed; never include raw HTTP responses."""


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes


class Transport(Protocol):
    def request(self, method: str, url: str, headers: Mapping[str, str],
                body: bytes | None = None) -> Response: ...


class UrlLibTransport:
    def request(self, method: str, url: str, headers: Mapping[str, str],
                body: bytes | None = None) -> Response:
        request = urllib.request.Request(url, data=body, headers=dict(headers),
                                         method=method)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return Response(response.status, response.read())
        except urllib.error.HTTPError as error:
            return Response(error.code, error.read())
        except (urllib.error.URLError, TimeoutError) as error:
            raise ProbeError("HTTP transport failed; no durable observation") from error


def _path(base: str, *segments: str) -> str:
    return base.rstrip("/") + "/" + "/".join(
        urllib.parse.quote(segment, safe="") for segment in segments
    )


def _json(response: Response, label: str) -> dict:
    try:
        value = json.loads(response.body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ProbeError(f"{label}: response was not valid JSON") from error
    if not isinstance(value, dict):
        raise ProbeError(f"{label}: expected a JSON object")
    return value


def _load_fixture(name: str) -> dict:
    value = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProbeError(f"{name}: fixture must be an object")
    return value


def _expect_status(response: Response, label: str, expected: set[int]) -> None:
    if response.status not in expected:
        raise ProbeError(f"{label}: HTTP {response.status}, expected {sorted(expected)}")


def _assert_document(actual: dict, expected: dict) -> None:
    if FORBIDDEN_EGRESS.intersection(actual):
        raise ProbeError("canonical read-back leaked storage or legacy keys")
    for field in ("id", "dataset", "dtype", "schemaVersion"):
        if actual.get(field) != expected.get(field):
            raise ProbeError(f"canonical read-back changed {field}")
    if actual.get("schemaVersion") != SCHEMA_VERSION:
        raise ProbeError("read-back was not canonical 0.10.1")
    # Relation identity and direction are part of the claim: source/destination
    # must not silently become an undirected generic 'related-to' edge.
    if expected["dtype"] == "relation":
        for field in ("source", "destination", "predicate"):
            if actual.get(field) != expected.get(field):
                raise ProbeError(f"canonical relation read-back changed {field}")
    elif expected["dtype"] == "person":
        if actual.get("fname") != expected.get("fname"):
            raise ProbeError("canonical person read-back changed fname")
    elif expected["dtype"] == "org":
        if actual.get("name") != expected.get("name"):
            raise ProbeError("canonical organization read-back changed name")


def execute(
    base_url: str,
    token: str,
    server_pin: str,
    *,
    transport: Transport | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    deadline_seconds: float = 60.0,
) -> dict:
    """Return only evidence after every step succeeds; otherwise raise."""
    if not base_url.startswith("http://127.0.0.1:"):
        raise ProbeError("live probe requires the loopback disposable test stack")
    if not token or not server_pin or len(server_pin) != 40:
        raise ProbeError("disposable credential or exact upstream SHA missing")
    transport = transport or UrlLibTransport()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    json_headers = {**headers, "Content-Type": "application/json"}

    openapi = transport.request("GET", _path(base_url, "openapi.json"), {})
    _expect_status(openapi, "OpenAPI discovery", {200})
    paths = _json(openapi, "OpenAPI").get("paths", {})
    if (not isinstance(paths, dict)
        or paths.get("/api/v1/documents", {}).get("post", {}).get(
            "x-starintel-operation-id") != "documents.create"
        or paths.get("/api/v1/documents/{id}", {}).get("get", {}).get(
            "x-starintel-operation-id") != "documents.get"):
        raise ProbeError("current contract lacks expected document operations")

    suffix = uuid.uuid4().hex[:20]
    documents = {name: _load_fixture(name) for name in ("person", "org", "relation")}
    for name, doc in documents.items():
        doc["id"] = f"{name}:book-p0-{suffix}"
        if doc.get("schemaVersion") != SCHEMA_VERSION:
            raise ProbeError("canonical fixture drifted")
    documents["relation"]["source"]["id"] = documents["person"]["id"]
    documents["relation"]["destination"]["id"] = documents["org"]["id"]

    denied = transport.request(
        "GET", _path(base_url, "api", "v1", "documents", documents["person"]["id"]),
        {"Accept": "application/json"},
    )
    _expect_status(denied, "unauthenticated document read", {401, 403})

    # The malformed key is invalid canonical transport syntax. This operation
    # must not be admitted as a legacy document or rewritten by the server.
    invalid = {**documents["person"], "id": f"person:book-p0-invalid-{suffix}",
               "_id": f"person:book-p0-invalid-{suffix}"}
    rejection = transport.request(
        "POST", _path(base_url, "api", "v1", "documents"), json_headers,
        json.dumps(invalid, separators=(",", ":")).encode("utf-8"),
    )
    _expect_status(rejection, "invalid canonical admission", {422})

    observations = []
    for name in ("person", "org", "relation"):
        expected = documents[name]
        creation = transport.request(
            "POST", _path(base_url, "api", "v1", "documents"), json_headers,
            json.dumps(expected, separators=(",", ":")).encode("utf-8"),
        )
        _expect_status(creation, f"{name} HTTP admission", {200, 201, 202})
        endpoint = _path(base_url, "api", "v1", "documents", expected["id"])
        until = clock() + deadline_seconds
        attempts = 0
        while True:
            attempts += 1
            response = transport.request("GET", endpoint, headers)
            if response.status == 200:
                _assert_document(_json(response, f"{name} read-back"), expected)
                break
            if response.status != 404:
                raise ProbeError(f"{name} read-back: unexpected HTTP {response.status}")
            if clock() >= until:
                raise ProbeError(f"{name} was not durably observable before deadline")
            sleep(min(0.5, max(0, until - clock())))
        observations.append({
            "dtype": name,
            "submission_http_status": creation.status,
            "readback_http_status": response.status,
            "read_attempts": attempts,
            "canonical_fields_verified": True,
        })

    return {
        "schema": "starintel-book-canonical-service-proof-v1",
        "server_pin": server_pin,
        "canonical_authority": AUTHORITY,
        "schema_version": SCHEMA_VERSION,
        "claim_status": "TESTED",
        "contract_discovery": "observed",
        "unauthenticated_get_http_status": denied.status,
        "malformed_canonical_post_http_status": rejection.status,
        "documents": observations,
        "not_proven": [
            "referential_integrity_enforced",
            "all_canonical_dtypes_supported",
            "publisher_confirm_or_actor_execution",
            "restart_recovery_or_outbox_crash_window",
            "performance_or_production_availability",
        ],
    }


def main() -> int:
    try:
        base_url = os.environ["STARINTEL_URL"]
        token = os.environ["STARINTEL_TOKEN"]
        pin = os.environ["STARINTEL_SERVER_PIN"]
        output = Path(os.environ["STARINTEL_BOOK_CANONICAL_OUTPUT"])
        report = execute(base_url, token, pin)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
        print("Canonical 0.10.1 service proof passed (synthetic records, sanitized artifact).")
        return 0
    except (ProbeError, OSError, KeyError) as error:
        # Never print credentials, request/response bodies or raw URLs.
        print(f"Canonical service proof failed: {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
