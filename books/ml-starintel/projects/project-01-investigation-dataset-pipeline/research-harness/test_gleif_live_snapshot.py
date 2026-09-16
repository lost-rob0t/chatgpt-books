#!/usr/bin/env python3
"""Unit tests for factual GLEIF API snapshot acquisition."""

from __future__ import annotations

import unittest

import acquire_gleif_live_snapshot as subject


class GleifLiveSnapshotTests(unittest.TestCase):
    def test_extract_target_links_finds_fund_relationship_resources(self) -> None:
        response = {
            "data": {
                "id": subject.FEEDER_LEI,
                "relationships": {
                    "master-fund": {
                        "links": {
                            "lei-record": "https://api.gleif.org/api/v1/lei-records/MASTER",
                            "relationship-record": "https://api.gleif.org/api/v1/relationship-records/R1",
                        }
                    },
                    "fund-manager": {
                        "links": {
                            "lei-record": "https://api.gleif.org/api/v1/lei-records/MANAGER",
                            "relationship-record": "https://api.gleif.org/api/v1/relationship-records/R2",
                        }
                    },
                    "unrelated": {"links": {"related": "https://example.invalid/nope"}},
                },
            }
        }
        links = subject.extract_target_links(response)
        self.assertEqual(set(links), {"master-fund", "fund-manager"})
        self.assertEqual(
            set(links["master-fund"]),
            {"lei-record", "relationship-record"},
        )

    def test_only_official_gleif_api_urls_are_followed(self) -> None:
        self.assertTrue(subject.safe_api_url("https://api.gleif.org/api/v1/lei-records/X"))
        self.assertFalse(subject.safe_api_url("https://gleif.org/api/v1/lei-records/X"))
        self.assertFalse(subject.safe_api_url("https://api.gleif.org.evil.example/api/v1/X"))
        self.assertFalse(subject.safe_api_url("http://api.gleif.org/api/v1/X"))

    def test_canonical_json_hash_is_stable_for_parsed_snapshot(self) -> None:
        value = {"b": 2, "a": [1, 3]}
        first = subject.canonical_json_bytes(value)
        second = subject.canonical_json_bytes({"a": [1, 3], "b": 2})
        self.assertEqual(first, second)
        self.assertEqual(subject.sha256_bytes(first), subject.sha256_bytes(second))


if __name__ == "__main__":
    unittest.main()
