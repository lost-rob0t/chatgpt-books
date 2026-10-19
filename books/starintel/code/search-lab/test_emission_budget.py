"""Hermetic, native Node checks of exact pinned StarIntel index emissions."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / os.environ.get("INDEX_SCRIPT", "index_projection.js")
DESIGN = Path(os.environ["STAR_SEARCH_LAB_SERVER"]) / "source/views/search.json"


def emit(doc):
    return subprocess.run(
        ["node", str(SCRIPT), str(DESIGN)],
        input=json.dumps(doc), text=True, capture_output=True, timeout=5,
        check=False,
    )


class EmissionBudgetTests(unittest.TestCase):
    def test_small_real_index_projection(self):
        result = emit({"dataset": "demo", "dtype": "person", "data": {"content": ["A", False, 0]}})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([(e["field"], e["value"]) for e in json.loads(result.stdout)],
                         [("tenant_id", "default"), ("dataset", "demo"),
                          ("dtype", "person"), ("content", "A"),
                          ("content", False), ("content", 0)])

    def test_at_exact_lab_cap_succeeds(self):
        doc = {"dataset": "demo", "dtype": "person", "data": {"content": list(range(2045))}}
        result = emit(doc)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)), 2048)

    def test_one_more_emission_fails_closed(self):
        doc = {"dataset": "demo", "dtype": "person", "data": {"content": list(range(2046))}}
        result = emit(doc)
        self.assertNotEqual(result.returncode, 0, "unbounded emission array accepted")
        self.assertIn("search lab emission budget exceeded (2048)", result.stderr)
        self.assertEqual(result.stdout, "", "partial JSON must never masquerade as complete emission evidence")

    def test_regular_nested_fields_unchanged(self):
        doc = {"name": "outer", "data": {"name": "inner", "content": ["hello"]}}
        result = emit(doc)
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = json.loads(result.stdout)
        self.assertEqual([x["value"] for x in rows if x["field"] == "name"], ["inner"])
        self.assertEqual([x["value"] for x in rows if x["field"] == "content"], ["hello"])


if __name__ == "__main__":
    unittest.main()
