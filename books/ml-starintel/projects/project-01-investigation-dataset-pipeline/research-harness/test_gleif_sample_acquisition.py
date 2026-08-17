#!/usr/bin/env python3
"""Unit tests for the GLEIF sample acquisition/inventory helper."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import acquire_gleif_samples as subject


class GleifSampleAcquisitionTests(unittest.TestCase):
    def make_zip(self, root: Path) -> Path:
        archive = root / "fixture.zip"
        lei_record = {
            "record": {"lei": subject.TARGET_LEIS[0]},
            "relationships": [{"type": "IS_SUBFUND_OF", "end": subject.TARGET_LEIS[1]}],
        }
        unrelated = {"record": {"lei": "UNRELATED000000000000"}}
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
            handle.writestr("samples/lei.json", json.dumps(lei_record, sort_keys=True))
            handle.writestr("samples/unrelated.json", json.dumps(unrelated, sort_keys=True))
            handle.writestr("README.txt", "not json")
        return archive

    def test_collect_inventory_finds_target_leis_and_relationship_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self.make_zip(root)
            output = root / "selected"
            inventory = subject.collect_inventory(archive, output)

            self.assertEqual(inventory["status"], "TESTED")
            self.assertEqual(len(inventory["members"]), 3)
            selected = inventory["selected_members"]
            self.assertEqual(len(selected), 1)
            self.assertEqual(selected[0]["name"], "samples/lei.json")
            self.assertEqual(selected[0]["matched_leis"], list(subject.TARGET_LEIS[:2]))
            self.assertEqual(selected[0]["relationship_types"], ["IS_SUBFUND_OF"])
            self.assertTrue((output / "samples" / "lei.json").is_file())

    def test_recursive_strings_walks_nested_json_without_inventing_values(self) -> None:
        value = {"a": ["x", {"b": "y"}], "c": 7, "d": None}
        self.assertEqual(list(subject.recursive_strings(value)), ["x", "y"])

    def test_invalid_json_member_is_recorded_not_selected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "bad.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("bad.json", b"{not-json")
            inventory = subject.collect_inventory(archive, root / "selected")
            member = inventory["members"][0]
            self.assertEqual(member["json_status"], "FAILED")
            self.assertEqual(inventory["selected_members"], [])


if __name__ == "__main__":
    unittest.main()
