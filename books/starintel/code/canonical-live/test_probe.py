#!/usr/bin/env python3
"""No-network regressions for the P0 real-stack probe and evidence boundary."""

import copy
import json
import sys
import unittest
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe import ProbeError, Response, _assert_document, execute


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeTransport:
    def __init__(self, *, deny=401, reject=422, missing_forever=False,
                 reverse_relation=False):
        self.deny = deny
        self.reject = reject
        self.missing_forever = missing_forever
        self.reverse_relation = reverse_relation
        self.records = {}
        self.lookups = {}
        self.methods = []

    def request(self, method, url, headers, body=None):
        path = urllib.parse.unquote(urllib.parse.urlsplit(url).path)
        self.methods.append((method, path))
        if path == "/openapi.json":
            data = {"paths": {
                "/api/v1/documents": {
                    "post": {"x-starintel-operation-id": "documents.create"}},
                "/api/v1/documents/{id}": {
                    "get": {"x-starintel-operation-id": "documents.get"}},
            }}
            return Response(200, json.dumps(data).encode())
        if path.startswith("/api/v1/documents/") and method == "GET":
            if "Authorization" not in headers:
                return Response(self.deny, b"secret-denial")
            key = path.removeprefix("/api/v1/documents/")
            self.lookups[key] = self.lookups.get(key, 0) + 1
            if key not in self.records or self.lookups[key] == 1 or self.missing_forever:
                return Response(404, b"not yet")
            document = copy.deepcopy(self.records[key])
            if self.reverse_relation and document["dtype"] == "relation":
                document["source"], document["destination"] = (
                    document["destination"], document["source"])
            document["rev"] = "2-fake-storage"
            return Response(200, json.dumps(document).encode())
        if path == "/api/v1/documents" and method == "POST":
            document = json.loads(body)
            if "_id" in document:
                return Response(self.reject, b"secret-validator-error")
            self.records[document["id"]] = document
            return Response(200, b"{}")
        raise AssertionError(f"unexpected request: {method} {path}")


class CanonicalLiveTests(unittest.TestCase):
    def execute(self, transport=None, deadline=5):
        fake_clock = FakeClock()
        transport = transport or FakeTransport()
        return execute("http://127.0.0.1:22000", "test-only-credential",
                       "a" * 40, transport=transport,
                       clock=fake_clock.clock, sleep=fake_clock.sleep,
                       deadline_seconds=deadline)

    def test_three_canonical_types_are_submitted_and_read_back(self):
        fake = FakeTransport()
        report = self.execute(fake)
        self.assertEqual(report["claim_status"], "TESTED")
        self.assertEqual(report["schema_version"], "0.10.1")
        self.assertEqual([item["dtype"] for item in report["documents"]],
                         ["person", "org", "relation"])
        self.assertEqual([item["read_attempts"] for item in report["documents"]],
                         [2, 2, 2])
        self.assertEqual(report["malformed_canonical_post_http_status"], 422)
        self.assertEqual(report["unauthenticated_get_http_status"], 401)
        self.assertNotIn("test-only-credential", str(report))
        relation = next(doc for doc in fake.records.values()
                        if doc["dtype"] == "relation")
        self.assertEqual(relation["source"]["id"].split(":")[0], "person")
        self.assertEqual(relation["destination"]["id"].split(":")[0], "org")
        self.assertEqual(relation["predicate"], "member-of")

    def test_bad_schema_admission_must_fail(self):
        with self.assertRaises(ProbeError):
            self.execute(FakeTransport(reject=200))

    def test_unauthorized_read_must_be_denied(self):
        with self.assertRaises(ProbeError):
            self.execute(FakeTransport(deny=200))

    def test_missing_readback_never_becomes_tested(self):
        with self.assertRaisesRegex(ProbeError, "not durably observable"):
            self.execute(FakeTransport(missing_forever=True), deadline=1.0)

    def test_relation_direction_mutation_fails(self):
        with self.assertRaisesRegex(ProbeError, "relation read-back changed"):
            self.execute(FakeTransport(reverse_relation=True))

    def test_storage_keys_are_not_allowed_in_canonical_output(self):
        original = {"id": "person:test", "dataset": "test", "dtype": "person",
                    "schemaVersion": "0.10.1", "fname": "Example"}
        with self.assertRaisesRegex(ProbeError, "leaked storage"):
            _assert_document({**original, "_rev": "2-private"}, original)

    def test_real_stacks_must_be_loopback_and_pinned(self):
        with self.assertRaises(ProbeError):
            execute("https://production.example.org", "token", "a" * 40,
                    transport=FakeTransport())
        with self.assertRaises(ProbeError):
            execute("http://127.0.0.1:22000", "token", "master",
                    transport=FakeTransport())


if __name__ == "__main__":
    unittest.main()
