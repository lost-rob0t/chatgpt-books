#!/usr/bin/env python3

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import inject_probe
from summarize_trace import SERVER_PIN, TraceError, build_trace, classify_fault


OBSERVED = {
    "submission": {
        "state": "http_publish_boundary_returned",
        "http_status": 200,
    },
    "persistence": {
        "state": "observed",
        "http_status": 200,
        "read_attempts": 2,
    },
}


class TraceTests(unittest.TestCase):
    def test_http_admission_failure_is_sanitized(self) -> None:
        self.assertEqual(
            classify_fault(1, "", "ingest adapter: StarIntel admission failed with HTTP 503: secret body"),
            {"class": "http_admission_failed", "http_status": 503},
        )

    def test_transport_failure_is_sanitized(self) -> None:
        self.assertEqual(
            classify_fault(1, "", "ingest adapter: StarIntel HTTP transport failed: reset"),
            {"class": "http_transport_failed"},
        )

    def test_success_without_readback_is_a_distinct_fault_outcome(self) -> None:
        outcome = classify_fault(
            0,
            '{"submission":{"state":"http_publish_boundary_returned","http_status":200},'
            '"persistence":{"state":"not_observed_before_deadline",'
            '"last_http_status":404,"read_attempts":3}}',
            "",
        )
        self.assertEqual(outcome["class"], "http_returned_without_persistence_observation")
        self.assertEqual(outcome["last_read_http_status"], 404)

    def test_observed_fault_document_is_contradictory(self) -> None:
        with self.assertRaises(TraceError):
            classify_fault(
                0,
                '{"submission":{"state":"http_publish_boundary_returned","http_status":200},'
                '"persistence":{"state":"observed","http_status":200,"read_attempts":1}}',
                "",
            )

    def test_unclassified_adapter_failure_fails_closed(self) -> None:
        with self.assertRaises(TraceError):
            classify_fault(2, "", "unexpected adapter failure")

    def test_full_trace_requires_verified_rabbit_outage(self) -> None:
        with self.assertRaises(TraceError):
            build_trace(
                server_pin=SERVER_PIN,
                happy=OBSERVED,
                fault_returncode=1,
                fault_stdout="",
                fault_stderr="StarIntel admission failed with HTTP 503",
                recovery=OBSERVED,
                rabbitmq_stopped=False,
                http_service_alive=True,
            )

    def test_full_trace_preserves_unproven_boundaries(self) -> None:
        trace = build_trace(
            server_pin=SERVER_PIN,
            happy=OBSERVED,
            fault_returncode=1,
            fault_stdout="",
            fault_stderr="StarIntel admission failed with HTTP 503: omitted",
            recovery=OBSERVED,
            rabbitmq_stopped=True,
            http_service_alive=True,
        )
        self.assertEqual(trace["claim_status"], "TESTED")
        self.assertEqual(trace["fault_injection"]["outcome"]["http_status"], 503)
        self.assertIn("publisher_confirm_acceptance", trace["not_proven"])
        self.assertNotIn("omitted", str(trace))

    def test_injector_requires_exact_upstream_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stack-test.sh"
            path.write_text("#!/bin/sh\necho nope\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                inject_probe.inject(path)

    def test_injector_is_single_use_and_preserves_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stack-test.sh"
            path.write_text("#!/bin/sh\n" + inject_probe.MARKER, encoding="utf-8")
            inject_probe.inject(path)
            rewritten = path.read_text(encoding="utf-8")
            self.assertIn(inject_probe.INJECTION, rewritten)
            self.assertIn(inject_probe.MARKER, rewritten)
            with self.assertRaises(RuntimeError):
                inject_probe.inject(path)


if __name__ == "__main__":
    unittest.main()
