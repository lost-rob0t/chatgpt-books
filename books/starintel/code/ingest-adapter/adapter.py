#!/usr/bin/env python3
"""Thin HTTP ingest client for the StarIntel book.

This client deliberately does not implement the StarIntel document schema,
RabbitMQ routing, authorization policy, or CouchDB persistence.  It crosses the
public HTTP boundary and records which observations were actually made.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol


class AdapterError(RuntimeError):
    """Base error for client-side adapter failures."""


class AdmissionError(AdapterError):
    """The HTTP admission boundary returned a non-success status."""

    def __init__(self, status: int, body: bytes):
        preview = body.decode("utf-8", errors="replace")[:512]
        super().__init__(f"StarIntel admission failed with HTTP {status}: {preview}")
        self.status = status
        self.body = body


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes


class Transport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> Response: ...


class UrlLibTransport:
    """Small stdlib transport with HTTP errors returned as normal responses."""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> Response:
        request = urllib.request.Request(
            url=url,
            data=body,
            headers=dict(headers),
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return Response(response.status, response.read())
        except urllib.error.HTTPError as error:
            return Response(error.code, error.read())
        except urllib.error.URLError as error:
            raise AdapterError(f"StarIntel HTTP transport failed: {error.reason}") from error


def _nonempty_string(document: Mapping[str, object], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(f"document field {key!r} must be a non-empty string")
    return value


def _endpoint(base_url: str, *segments: str) -> str:
    base = base_url.rstrip("/")
    encoded = "/".join(urllib.parse.quote(segment, safe="") for segment in segments)
    return f"{base}/{encoded}"


def _headers(token: str) -> dict[str, str]:
    if not token.strip():
        raise AdapterError("a bearer token is required")
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _persistence_evidence(
    *,
    base_url: str,
    document_id: str,
    token: str,
    wait_seconds: float,
    poll_interval: float,
    transport: Transport,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
) -> dict[str, object]:
    if wait_seconds < 0:
        raise AdapterError("persistence wait must be non-negative")
    if poll_interval <= 0:
        raise AdapterError("poll interval must be positive")

    url = _endpoint(base_url, "document", document_id)
    deadline = clock() + wait_seconds
    attempts = 0

    while True:
        attempts += 1
        response = transport.request("GET", url, _headers(token), None)
        if 200 <= response.status < 300:
            return {
                "state": "observed",
                "http_status": response.status,
                "read_attempts": attempts,
            }
        if response.status != 404:
            raise AdmissionError(response.status, response.body)
        if clock() >= deadline:
            return {
                "state": "not_observed_before_deadline",
                "last_http_status": response.status,
                "read_attempts": attempts,
            }
        sleep(min(poll_interval, max(0.0, deadline - clock())))


def submit_document(
    *,
    base_url: str,
    token: str,
    document: Mapping[str, object],
    wait_persisted: float | None = None,
    poll_interval: float = 0.25,
    transport: Transport | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    """Submit one already-formed document and report observed boundary states.

    Structural checks here protect URL construction and reporting only.  The
    StarIntel server remains the schema and authorization authority.
    """

    if not isinstance(document, Mapping):
        raise AdapterError("document must be a JSON object")

    document_id = _nonempty_string(document, "_id")
    dtype = _nonempty_string(document, "dtype")
    transport = transport or UrlLibTransport()
    body = json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    url = _endpoint(base_url, "new", "document", dtype)
    response = transport.request("POST", url, _headers(token), body)

    if not 200 <= response.status < 300:
        raise AdmissionError(response.status, response.body)

    evidence: dict[str, object] = {
        "document_id": document_id,
        "submission": {
            "state": "http_publish_boundary_returned",
            "http_status": response.status,
        },
        "persistence": {"state": "not_checked"},
    }

    if wait_persisted is not None:
        evidence["persistence"] = _persistence_evidence(
            base_url=base_url,
            document_id=document_id,
            token=token,
            wait_seconds=wait_persisted,
            poll_interval=poll_interval,
            transport=transport,
            clock=clock,
            sleep=sleep,
        )

    return evidence


def _load_document(path: Path) -> Mapping[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, dict):
        raise AdapterError("input JSON must be an object")
    return document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Submit a StarIntel document and keep acceptance distinct from persistence."
    )
    parser.add_argument("document", type=Path, help="JSON document to submit")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("STARINTEL_URL", "http://127.0.0.1:8080"),
        help="StarIntel HTTP base URL (default: STARINTEL_URL or http://127.0.0.1:8080)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("STARINTEL_TOKEN"),
        help="Bearer credential (default: STARINTEL_TOKEN)",
    )
    parser.add_argument(
        "--wait-persisted",
        type=float,
        default=None,
        metavar="SECONDS",
        help="poll GET /document/:id for a separate persistence observation",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.25,
        metavar="SECONDS",
        help="persistence polling interval (default: 0.25)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.token is None:
        parser.error("--token or STARINTEL_TOKEN is required")

    try:
        evidence = submit_document(
            base_url=args.base_url,
            token=args.token,
            document=_load_document(args.document),
            wait_persisted=args.wait_persisted,
            poll_interval=args.poll_interval,
        )
    except AdapterError as error:
        print(f"ingest adapter: {error}", file=sys.stderr)
        return 1

    json.dump(evidence, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
