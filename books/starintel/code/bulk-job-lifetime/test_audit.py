#!/usr/bin/env python3
from __future__ import annotations

import unittest

from audit import Snapshot, TraceError, audit, validate_trace


def s(
    seq: int,
    job_id: str = "job-1",
    status: str = "queued",
    total: int = 2,
    succeeded: int = 0,
    failed: int = 0,
    documents_retained: bool = True,
    service_context_retained: bool = True,
) -> Snapshot:
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


class BulkJobLifetimeAuditTests(unittest.TestCase):
    def test_completed_lifecycle_proves_release(self) -> None:
        result = audit(
            (
                s(0),
                s(1, status="running", succeeded=1),
                s(
                    2,
                    status="completed",
                    succeeded=2,
                    documents_retained=False,
                    service_context_retained=False,
                ),
            )
        )
        self.assertEqual(result.state, "proven")
        self.assertEqual(result.terminal_jobs_proven, 1)

    def test_completed_with_errors_can_prove_release(self) -> None:
        result = audit(
            (
                s(0, status="running"),
                s(
                    1,
                    status="completed-with-errors",
                    succeeded=1,
                    failed=1,
                    documents_retained=False,
                    service_context_retained=False,
                ),
            )
        )
        self.assertEqual(result.state, "proven")

    def test_failed_job_may_have_partial_counts(self) -> None:
        result = audit(
            (
                s(0, status="running"),
                s(
                    1,
                    status="failed",
                    succeeded=1,
                    documents_retained=False,
                    service_context_retained=False,
                ),
            )
        )
        self.assertEqual(result.state, "proven")

    def test_terminal_document_retention_is_a_contradiction(self) -> None:
        result = audit(
            (
                s(
                    0,
                    status="completed",
                    succeeded=2,
                    documents_retained=True,
                    service_context_retained=False,
                ),
            )
        )
        self.assertEqual(result.state, "contradicted")
        self.assertIn("document payload", result.findings[0].reason)

    def test_terminal_service_context_retention_is_a_contradiction(self) -> None:
        result = audit(
            (
                s(
                    0,
                    status="completed",
                    succeeded=2,
                    documents_retained=False,
                    service_context_retained=True,
                ),
            )
        )
        self.assertEqual(result.state, "contradicted")
        self.assertIn("service context", result.findings[0].reason)

    def test_nonterminal_latest_snapshot_is_incomplete_not_green(self) -> None:
        result = audit((s(0), s(1, status="running", succeeded=1)))
        self.assertEqual(result.state, "incomplete")
        self.assertEqual(result.incomplete_jobs, 1)
        self.assertEqual(result.terminal_jobs_proven, 0)

    def test_completed_counts_must_match_total(self) -> None:
        result = audit(
            (
                s(
                    0,
                    status="completed",
                    succeeded=1,
                    documents_retained=False,
                    service_context_retained=False,
                ),
            )
        )
        self.assertEqual(result.state, "contradicted")
        self.assertIn("completed counts", result.findings[0].reason)

    def test_total_cannot_change_across_job_lifecycle(self) -> None:
        with self.assertRaisesRegex(TraceError, "total changed"):
            validate_trace((s(0, total=2), s(1, status="running", total=3)))

    def test_counters_cannot_decrease(self) -> None:
        with self.assertRaisesRegex(TraceError, "must not decrease"):
            validate_trace(
                (
                    s(0, status="running", succeeded=1),
                    s(1, status="running", succeeded=0),
                )
            )

    def test_terminal_status_cannot_be_followed_by_another_snapshot(self) -> None:
        with self.assertRaisesRegex(TraceError, "after terminal"):
            validate_trace(
                (
                    s(
                        0,
                        status="failed",
                        documents_retained=False,
                        service_context_retained=False,
                    ),
                    s(1, status="running"),
                )
            )

    def test_sequence_values_must_be_strictly_increasing(self) -> None:
        with self.assertRaisesRegex(TraceError, "strictly increasing"):
            validate_trace((s(1), s(0, job_id="job-2")))


if __name__ == "__main__":
    unittest.main()
