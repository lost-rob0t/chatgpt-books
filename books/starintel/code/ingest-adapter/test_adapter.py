#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from typing import Mapping

from adapter import AdapterError, AdmissionError, Response, submit_document


DOCUMENT = {
    "_id": "starintel:person:book-demo",
    "dtype": "person",
    "dataset": "book-demo",
    "schema_version": "0.9.0",
}


@dataclass
class Call:
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None


class FakeTransport:
    def __init__(self, responses: list[Response]):
        self.responses = list(responses)
        self.calls: list[Call] = []

    def request(self, method, url, headers, body):
        self.calls.append(Call(method, url, dict(headers), body))
        if not self.responses:
            raise AssertionError("unexpected transport call")
        return self.responses.pop(0)


class FakeTime:
    def __init__(self):
        self.now = 100.0
        self.sleeps: list[float] = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class IngestAdapterTests(unittest.TestCase):
    def test_post_records_acceptance_without_claiming_persistence(self):
        transport = FakeTransport([Response(200, b"{}")])

        evidence = submit_document(
            base_url="http://star.test/",
            token="secret-token",
            document=DOCUMENT,
            transport=transport,
        )

        self.assertEqual("http_publish_boundary_returned", evidence["submission"]["state"])
        self.assertEqual("not_checked", evidence["persistence"]["state"])
        self.assertEqual(1, len(transport.calls))
        call = transport.calls[0]
        self.assertEqual("POST", call.method)
        self.assertEqual("http://star.test/new/document/person", call.url)
        self.assertEqual("Bearer secret-token", call.headers["Authorization"])
        self.assertEqual(DOCUMENT, json.loads(call.body.decode("utf-8")))

    def test_readback_is_a_separate_observation(self):
        transport = FakeTransport(
            [Response(200, b"{}"), Response(404, b"missing"), Response(200, b"{}")]
        )
        fake_time = FakeTime()

        evidence = submit_document(
            base_url="http://star.test",
            token="token",
            document=DOCUMENT,
            wait_persisted=2.0,
            poll_interval=0.5,
            transport=transport,
            clock=fake_time.clock,
            sleep=fake_time.sleep,
        )

        self.assertEqual("observed", evidence["persistence"]["state"])
        self.assertEqual(2, evidence["persistence"]["read_attempts"])
        self.assertEqual("GET", transport.calls[1].method)
        self.assertEqual(
            "http://star.test/document/starintel%3Aperson%3Abook-demo",
            transport.calls[1].url,
        )
        self.assertEqual([0.5], fake_time.sleeps)

    def test_readback_timeout_stays_non_durable_evidence(self):
        transport = FakeTransport(
            [Response(201, b"{}"), Response(404, b""), Response(404, b""), Response(404, b"")]
        )
        fake_time = FakeTime()

        evidence = submit_document(
            base_url="http://star.test",
            token="token",
            document=DOCUMENT,
            wait_persisted=1.0,
            poll_interval=0.5,
            transport=transport,
            clock=fake_time.clock,
            sleep=fake_time.sleep,
        )

        self.assertEqual("not_observed_before_deadline", evidence["persistence"]["state"])
        self.assertEqual(3, evidence["persistence"]["read_attempts"])

    def test_post_rejection_is_not_reported_as_acceptance(self):
        transport = FakeTransport([Response(403, b'{"error":"forbidden"}')])
        with self.assertRaises(AdmissionError) as caught:
            submit_document(
                base_url="http://star.test",
                token="token",
                document=DOCUMENT,
                transport=transport,
            )
        self.assertEqual(403, caught.exception.status)

    def test_readback_auth_failure_is_not_downgraded_to_not_found(self):
        transport = FakeTransport([Response(200, b"{}"), Response(403, b"forbidden")])
        with self.assertRaises(AdmissionError) as caught:
            submit_document(
                base_url="http://star.test",
                token="token",
                document=DOCUMENT,
                wait_persisted=1.0,
                transport=transport,
            )
        self.assertEqual(403, caught.exception.status)

    def test_url_segments_are_quoted(self):
        document = dict(DOCUMENT, _id="id/with space", dtype="custom/type")
        transport = FakeTransport([Response(200, b"{}")])
        submit_document(
            base_url="http://star.test",
            token="token",
            document=document,
            transport=transport,
        )
        self.assertEqual(
            "http://star.test/new/document/custom%2Ftype",
            transport.calls[0].url,
        )

    def test_local_checks_are_structural_not_a_fake_schema(self):
        transport = FakeTransport([Response(200, b"{}")])
        deliberately_incomplete = {"_id": "demo", "dtype": "person"}
        evidence = submit_document(
            base_url="http://star.test",
            token="token",
            document=deliberately_incomplete,
            transport=transport,
        )
        self.assertEqual("http_publish_boundary_returned", evidence["submission"]["state"])

    def test_missing_identity_dtype_or_token_fails_before_network(self):
        for document in ({"dtype": "person"}, {"_id": "demo"}):
            transport = FakeTransport([])
            with self.assertRaises(AdapterError):
                submit_document(
                    base_url="http://star.test",
                    token="token",
                    document=document,
                    transport=transport,
                )
            self.assertEqual([], transport.calls)

        transport = FakeTransport([])
        with self.assertRaises(AdapterError):
            submit_document(
                base_url="http://star.test",
                token="",
                document=DOCUMENT,
                transport=transport,
            )
        self.assertEqual([], transport.calls)


if __name__ == "__main__":
    unittest.main()
