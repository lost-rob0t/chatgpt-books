#!/usr/bin/env python3
"""Derive a conservative replay boundary from independently verified batch evidence.

This is a teaching tool, not StarIntel server code.  It deliberately does not
query CouchDB, normalize StarIntel documents, or decide whether two documents
are equivalent.  Its input is a sanitized ledger whose rows have already been
classified by an operator or a separate evidence-gathering step.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ALLOWED_STATUSES = frozenset({"verified_match", "absent", "mismatch", "unknown"})


class LedgerError(ValueError):
    """The evidence ledger is malformed or internally inconsistent."""


@dataclass(frozen=True)
class EvidenceRow:
    offset: int
    document_id: str
    status: str


@dataclass(frozen=True)
class Reconciliation:
    batch_size: int
    verified_match_count: int
    absent_count: int
    mismatch_count: int
    unknown_count: int
    verified_prefix_count: int
    first_unverified_offset: int | None
    safe_resume_offset: int | None
    state: str
    reason: str


def _row_from_object(obj: object, line_number: int) -> EvidenceRow:
    if not isinstance(obj, dict):
        raise LedgerError(f"line {line_number}: expected a JSON object")

    offset = obj.get("offset")
    document_id = obj.get("id")
    status = obj.get("status")

    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise LedgerError(f"line {line_number}: offset must be a non-negative integer")
    if not isinstance(document_id, str) or not document_id:
        raise LedgerError(f"line {line_number}: id must be a non-empty string")
    if status not in ALLOWED_STATUSES:
        allowed = ", ".join(sorted(ALLOWED_STATUSES))
        raise LedgerError(f"line {line_number}: status must be one of: {allowed}")

    return EvidenceRow(offset=offset, document_id=document_id, status=status)


def load_ledger(path: Path) -> tuple[EvidenceRow, ...]:
    rows: list[EvidenceRow] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise LedgerError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
            rows.append(_row_from_object(obj, line_number))
    return validate_rows(rows)


def validate_rows(rows: Iterable[EvidenceRow]) -> tuple[EvidenceRow, ...]:
    materialized = tuple(rows)
    if not materialized:
        raise LedgerError("ledger must contain at least one batch row")

    offsets = [row.offset for row in materialized]
    expected_offsets = list(range(len(materialized)))
    if offsets != expected_offsets:
        raise LedgerError(
            "ledger offsets must appear exactly once in ascending order from 0 "
            f"through {len(materialized) - 1}; got {offsets!r}"
        )

    ids = [row.document_id for row in materialized]
    if len(ids) != len(set(ids)):
        raise LedgerError("ledger document ids must be unique within the batch")

    return materialized


def reconcile(rows: Iterable[EvidenceRow]) -> Reconciliation:
    rows = validate_rows(rows)
    counts = {status: 0 for status in ALLOWED_STATUSES}
    for row in rows:
        counts[row.status] += 1

    prefix_count = 0
    for row in rows:
        if row.status != "verified_match":
            break
        prefix_count += 1

    first_unverified = prefix_count if prefix_count < len(rows) else None

    if counts["mismatch"] or counts["unknown"]:
        return Reconciliation(
            batch_size=len(rows),
            verified_match_count=counts["verified_match"],
            absent_count=counts["absent"],
            mismatch_count=counts["mismatch"],
            unknown_count=counts["unknown"],
            verified_prefix_count=prefix_count,
            first_unverified_offset=first_unverified,
            safe_resume_offset=None,
            state="requires_manual_reconciliation",
            reason="mismatch or unknown evidence prevents a mechanically safe replay boundary",
        )

    if counts["absent"] == 0:
        return Reconciliation(
            batch_size=len(rows),
            verified_match_count=counts["verified_match"],
            absent_count=0,
            mismatch_count=0,
            unknown_count=0,
            verified_prefix_count=len(rows),
            first_unverified_offset=None,
            safe_resume_offset=None,
            state="fully_verified",
            reason="every batch row is independently classified as a verified match",
        )

    suffix = rows[prefix_count:]
    if suffix and all(row.status == "absent" for row in suffix):
        return Reconciliation(
            batch_size=len(rows),
            verified_match_count=counts["verified_match"],
            absent_count=counts["absent"],
            mismatch_count=0,
            unknown_count=0,
            verified_prefix_count=prefix_count,
            first_unverified_offset=prefix_count,
            safe_resume_offset=prefix_count,
            state="verified_prefix_absent_suffix",
            reason=(
                "the ledger proves one contiguous verified prefix followed only by "
                "independently verified absence"
            ),
        )

    return Reconciliation(
        batch_size=len(rows),
        verified_match_count=counts["verified_match"],
        absent_count=counts["absent"],
        mismatch_count=0,
        unknown_count=0,
        verified_prefix_count=prefix_count,
        first_unverified_offset=first_unverified,
        safe_resume_offset=None,
        state="requires_manual_reconciliation",
        reason="verified rows appear after an absent row; the durable set is not a simple prefix",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="derive a conservative replay boundary from a sanitized evidence ledger"
    )
    parser.add_argument("ledger", type=Path, help="JSONL evidence ledger")
    args = parser.parse_args()

    try:
        result = reconcile(load_ledger(args.ledger))
    except (OSError, LedgerError) as exc:
        parser.error(str(exc))

    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
