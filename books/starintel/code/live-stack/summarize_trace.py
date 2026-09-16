#!/usr/bin/env python3
"""Validate and sanitize evidence from the disposable StarIntel stack probe."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping

SERVER_PIN = "1ac298b797bd4bc0e71cfde083c6a59af55ccc6f"
HTTP_STATUS = re.compile(r"HTTP\s+(\d{3})")


class TraceError(RuntimeError):
    """The probe evidence is incomplete, contradictory, or unsafe to promote."""


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TraceError(f"cannot read JSON evidence {path}: {error}") from error
    if not isinstance(value, dict):
        raise TraceError(f"evidence {path} must be a JSON object")
    return value


def _require_observed(label: str, evidence: Mapping[str, Any]) -> dict[str, Any]:
    submission = evidence.get("submission")
    persistence = evidence.get("persistence")
    if not isinstance(submission, dict) or not isinstance(persistence, dict):
        raise TraceError(f"{label} observation is missing submission/persistence objects")
    if submission.get("state") != "http_publish_boundary_returned":
        raise TraceError(f"{label} did not observe the HTTP publication boundary")
    if persistence.get("state") != "observed":
        raise TraceError(f"{label} did not observe authorized durable read-back")
    status = submission.get("http_status")
    read_status = persistence.get("http_status")
    if not isinstance(status, int) or not isinstance(read_status, int):
        raise TraceError(f"{label} HTTP evidence is not numeric")
    return {
        "submission_state": "http_publish_boundary_returned",
        "submission_http_status": status,
        "persistence_state": "observed",
        "readback_http_status": read_status,
        "read_attempts": persistence.get("read_attempts"),
    }


def classify_fault(returncode: int, stdout: str, stderr: str) -> dict[str, Any]:
    """Classify only evidence the adapter actually exposed; never retain raw bodies."""

    if returncode == 0:
        try:
            evidence = json.loads(stdout)
        except json.JSONDecodeError as error:
            raise TraceError(f"fault probe returned invalid JSON: {error}") from error
        if not isinstance(evidence, dict):
            raise TraceError("fault probe JSON must be an object")
        submission = evidence.get("submission")
        persistence = evidence.get("persistence")
        if not isinstance(submission, dict) or not isinstance(persistence, dict):
            raise TraceError("fault probe is missing submission/persistence evidence")
        if submission.get("state") != "http_publish_boundary_returned":
            raise TraceError("fault probe success lacks publication-boundary evidence")
        persistence_state = persistence.get("state")
        if persistence_state == "observed":
            raise TraceError(
                "fault injection was contradicted: the unique fault document became durable "
                "while RabbitMQ was verified stopped"
            )
        if persistence_state != "not_observed_before_deadline":
            raise TraceError(f"unexpected fault persistence state: {persistence_state!r}")
        return {
            "class": "http_returned_without_persistence_observation",
            "submission_http_status": submission.get("http_status"),
            "persistence_state": persistence_state,
            "last_read_http_status": persistence.get("last_http_status"),
            "read_attempts": persistence.get("read_attempts"),
        }

    status_match = HTTP_STATUS.search(stderr)
    if status_match:
        return {
            "class": "http_admission_failed",
            "http_status": int(status_match.group(1)),
        }
    if "HTTP transport failed" in stderr:
        return {"class": "http_transport_failed"}
    raise TraceError("fault probe failed without a recognized HTTP/transport observation")


def build_trace(
    *,
    server_pin: str,
    happy: Mapping[str, Any],
    fault_returncode: int,
    fault_stdout: str,
    fault_stderr: str,
    recovery: Mapping[str, Any],
    rabbitmq_stopped: bool,
    http_service_alive: bool,
) -> dict[str, Any]:
    if server_pin != SERVER_PIN:
        raise TraceError(f"unexpected StarIntel Server pin: {server_pin}")
    if not rabbitmq_stopped:
        raise TraceError("fault precondition was not observed: RabbitMQ was still running")

    return {
        "schema": "starintel-book-service-trace-v1",
        "server_revision": server_pin,
        "claim_status": "TESTED",
        "happy_path": _require_observed("happy path", happy),
        "fault_injection": {
            "rabbitmq_running": False,
            "http_service_alive": bool(http_service_alive),
            "outcome": classify_fault(fault_returncode, fault_stdout, fault_stderr),
        },
        "operator_recovery": {
            "action": "start_rabbitmq_then_restart_star_server",
            **_require_observed("recovery path", recovery),
        },
        "not_proven": [
            "publisher_confirm_acceptance",
            "settlement_failure_redelivery",
            "outbox_crash_window",
            "transparent_reconnect_without_operator_restart",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-pin", required=True)
    parser.add_argument("--happy", type=Path, required=True)
    parser.add_argument("--fault-stdout", type=Path, required=True)
    parser.add_argument("--fault-stderr", type=Path, required=True)
    parser.add_argument("--fault-returncode", type=int, required=True)
    parser.add_argument("--recovery", type=Path, required=True)
    parser.add_argument("--rabbitmq-stopped", choices=("true", "false"), required=True)
    parser.add_argument("--http-service-alive", choices=("true", "false"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        trace = build_trace(
            server_pin=args.server_pin,
            happy=_load_json(args.happy),
            fault_returncode=args.fault_returncode,
            fault_stdout=args.fault_stdout.read_text(encoding="utf-8"),
            fault_stderr=args.fault_stderr.read_text(encoding="utf-8"),
            recovery=_load_json(args.recovery),
            rabbitmq_stopped=args.rabbitmq_stopped == "true",
            http_service_alive=args.http_service_alive == "true",
        )
    except (OSError, TraceError) as error:
        raise SystemExit(f"service trace: {error}") from error

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(trace, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
