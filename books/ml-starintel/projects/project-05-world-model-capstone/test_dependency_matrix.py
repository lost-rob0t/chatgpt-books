"""Candidate dependency source pins are not implicit integration approval."""
import json
from pathlib import Path
import re
import unittest
from capstone import ContractError, require_component

MATRIX = json.loads((Path(__file__).parent / "dependencies.json").read_text())
SHA = re.compile(r"[0-9a-f]{40}\Z")

class MatrixContractTest(unittest.TestCase):
    def test_scope(self):
        self.assertEqual(MATRIX["version"], "bk10.dependency-matrix.v1")
        self.assertEqual(MATRIX["repository"], "lost-rob0t/chatgpt-books")

    def test_all_owners(self):
        rows = MATRIX["components"]
        self.assertEqual([r["worker"] for r in rows], [f"BK{i:02}" for i in range(1, 10)])
        self.assertEqual([r["issue"] for r in rows], list(range(143, 152)))

    def test_all_pins_and_branch_states(self):
        for r in MATRIX["components"]:
            self.assertRegex(r["branch_head_sha"], SHA)
            if r["source_path"]:
                self.assertRegex(r["commit_sha"], SHA)
                self.assertRegex(r["source_blob_sha"], SHA)
                self.assertNotEqual(r["branch_head_sha"], MATRIX["main_commit_sha"])
            else:
                self.assertIsNone(r["commit_sha"])
                self.assertIsNone(r["source_blob_sha"])

    def test_unreviewed_never_enabled(self):
        for r in MATRIX["components"]:
            self.assertIsNone(r["contract"])
            for k in ["integration_ready", "open_component_pr_verified", "independent_review_verified", "exact_head_pr_checks_verified"]:
                self.assertFalse(r[k])
            with self.subTest(r=r["worker"]), self.assertRaisesRegex(ContractError, "unavailable"):
                require_component({r["name"]: r}, r["name"])

    def test_has_both_status_classes(self):
        states = {r["state"] for r in MATRIX["components"]}
        self.assertIn("candidate-implementation-unreviewed", states)
        self.assertIn("no-current-feature-implementation-verified", states)

if __name__ == "__main__":
    unittest.main()
