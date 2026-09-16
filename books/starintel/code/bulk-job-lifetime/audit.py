#!/usr/bin/env python3
"""Audit sanitized bulk-job lifecycle observations without simulating StarIntel.

The input is JSONL captured by a trusted test/instrumentation boundary. This
tool does not contact StarIntel services and does not infer hidden state. It
checks whether the observed lifecycle is sufficient to prove that terminal
jobs released request-only payloads while preserving stable status counters.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ACTIVE_STATUSES = frozenset({"queued", "running"})
TERMINAL_STATUSES = frozenset({"completed", "completed-with-errors", "failed"})
ALLOWED_STATUSES = ACTIVE_STATUSES | TERMINAL_STATUSES


class TraceError(ValueError):
    """The observation trace is malformed."""


@dataclass(frozen=True)
class Snapshot:
    seq: int
    job_id: str
    status: str
    total: int
    succeeded: int
    failed: int
    documents_retained: bool
    service_context_retained: bool


@dataclass(frozen=True)
class Finding:
    job_id: str
    state: str
    reason: str


@dataclass(frozen=True)
class Audit:
    state: str
    jobs_observed: int
    terminal_jobs_proven: int
    incomplete_jobs: int
    contradictions: int
    findings: tuple[Finding, ...]


def _strict_int(value: object, name: str, line_number: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TraceError(f"line {line_number}: {name} must be a non-negative integer")
    return value


def _strict_bool(value: object, name: str, line_number: int) -> bool:
    if not isinstance(value, bool):
        raise TraceError(f"line {line_number}: {name} must be a boolean")
    return value


def _snapshot_from_object(obj: object, line_number: int) -> Snapshot:
    if not isinstance(obj, dict):
        raise TraceError(f"line {line_number}: expected a JSON object")

    seq = _strict_int(obj.get("seq"), "seq", line_number)
    job_id = obj.get("job_id")
    status = obj.get("status")
    total = _strict_int(obj.get("total"), "total", line_number)
    succeeded = _strict_int(obj.get("succeeded"), "succeeded", line_number)
    failed = _strict_int(obj.get("failed"), "failed", line_number)
    documents_retained = _strict_bool(
        obj.get("documents_retained"), "documents_retained", line_number
    )
    service_context_retained = _strict_bool(
        obj.get("service_context_retained"),
        "service_context_retained",
        line_number,
    )

    if not isinstance(job_id, str) or not job_id:
        raise TraceError(f"line {line_number}: job_id must be a non-empty string")
    if status not in ALLOWED_STATUSES:
        allowed = ", ".join(sorted(ALLOWED_STATUSES))
        raise TraceError(f"line {line_number}: status must be one of: {allowed}")
    if succeeded + failed > total:
        raise TraceError(
            f"line {line_number}: succeeded + failed cannot exceed total"
        )

    return Snapshot(
        seq=seq,
        job_id=job_id,
        status=status,
        total=total,
        succeeded=succeeded,
        failed=failed,
        documents_retained=documents_retained,
        service_context_retained=service_context_retained,
    )


def load_trace(path: Path) -> tuple[Snapshot, ...]:
    snapshots: list[Snapshot] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise TraceError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
            snapshots.append(_snapshot_from_object(obj, line_number))
    return validate_trace(snapshots)


def validate_trace(snapshots: Iterable[Snapshot]) -> tuple[Snapshot, ...]:
    materialized = tuple(snapshots)
    if not materialized:
        raise TraceError("trace must contain at least one snapshot")

    seqs = [snapshot.seq for snapshot in materialized]
    if seqs != sorted(set(seqs)):
        raise TraceError("seq values must be unique and strictly increasing")

    previous_by_job: dict[str, Snapshot] = {}
    for snapshot in materialized:
        previous = previous_by_job.get(snapshot.job_id)
        if previous is not None:
            if snapshot.total != previous.total:
                raise TraceError(
                    f"job {snapshot.job_id}: total changed from "
                    f"{previous.total} to {snapshot.total}"
                )
            if snapshot.succeeded < previous.succeeded or snapshot.failed < previous.failed:
                raise TraceError(
                    f"job {snapshot.job_id}: succeeded/failed counters must not decrease"
                )
            if previous.status in TERMINAL_STATUSES:
                raise TraceError(
                    f"job {snapshot.job_id}: observed another snapshot after terminal "
                    f"status {previous.status}"
                )
            if previous.status == "running" and snapshot.status == "queued":
                raise TraceError(
                    f"job {snapshot.job_id}: status regressed from running to queued"
                )
        previous_by_job[snapshot.job_id] = snapshot

    return materialized


def _terminal_finding(snapshot: Snapshot) -> Finding:
    reasons: list[str] = []

    if snapshot.documents_retained:
        reasons.append("terminal snapshot still retains document payload")
    if snapshot.service_context_retained:
        reasons.append("terminal snapshot still retains request-only service context")

    if snapshot.status == "completed":
        if snapshot.failed != 0 or snapshot.succeeded != snapshot.total:
            reasons.append("completed counts do not equal total successes and zero failures")
    elif snapshot.status == "completed-with-errors":
        if snapshot.failed == 0 or snapshot.succeeded + snapshot.failed != snapshot.total:
            reasons.append(
                "completed-with-errors requires at least one failure and complete accounting"
            )

    if reasons:
        return Finding(
            job_id=snapshot.job_id,
            state="contradicted",
            reason="; ".join(reasons),
        )

    return Finding(
        job_id=snapshot.job_id,
        state="proven",
        reason=(
            "terminal snapshot preserves stable counters while both request-only "
            "retention flags are false"
        ),
    )


def audit(snapshots: Iterable[Snapshot]) -> Audit:
    snapshots = validate_trace(snapshots)
    latest: dict[str, Snapshot] = {}
    for snapshot in snapshots:
        latest[snapshot.job_id] = snapshot

    findings: list[Finding] = []
    for job_id in sorted(latest):
        snapshot = latest[job_id]
        if snapshot.status in TERMINAL_STATUSES:
            findings.append(_terminal_finding(snapshot))
        else:
            findings.append(
                Finding(
                    job_id=job_id,
                    state="incomplete",
                    reason=(
                        f"latest observed status is {snapshot.status}; no terminal "
                        "release observation exists"
                    ),
                )
            )

    contradictions = sum(f.state == "contradicted" for f in findings)
    incomplete = sum(f.state == "incomplete" for f in findings)
    proven = sum(f.state == "proven" for f in findings)

    if contradictions:
        state = "contradicted"
    elif incomplete:
        state = "incomplete"
    else:
        state = "proven"

    return Audit(
        state=state,
        jobs_observed=len(findings),
        terminal_jobs_proven=proven,
        incomplete_jobs=incomplete,
        contradictions=contradictions,
        findings=tuple(findings),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="audit sanitized async bulk-job lifecycle observations"
    )
    parser.add_argument("trace", type=Path, help="JSONL lifecycle trace")
    args = parser.parse_args()

    try:
        result = audit(load_trace(args.trace))
    except (OSError, TraceError) as exc:
        parser.error(str(exc))

    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    return 1 if result.state == "contradicted" else 0


if __name__ == "__main__":
    raise SystemExit(main())
