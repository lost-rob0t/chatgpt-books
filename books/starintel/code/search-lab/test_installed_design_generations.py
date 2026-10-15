"""Attest explicit historical and merged source generations against exported FTS designs.

Reconstruct only the four exact merged field additions from the historical
source and independently require the Git-blob hash of the merged primary file.
No actual CouchDB export, Clouseau operation, or HTTP search is fabricated.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from verify_installed_design import (
    HISTORICAL_GIT_BLOB, git_blob_sha, compare_exported_design,
)

MERGED_GIT_BLOB = 'dd6336f3047982db2f0e3615fed1413ed1e58e13'
SOURCE = Path(os.environ['STAR_SEARCH_LAB_SERVER']) / 'source/views/search.json'


def merged_source(historical: bytes) -> bytes:
    changed = historical
    for previous, following in (
        (b"'full_name','content'", b"'full_name','fullName','content'"),
        (b"'display_name','legal_name','group'",
         b"'display_name','displayName','legal_name','legalName','group'"),
        (b"'org_type'];", b"'org_type','orgType'];"),
    ):
        if changed.count(previous) != 1:
            raise ValueError('historical source changed; cannot derive merged FTS pin')
        changed = changed.replace(previous, following, 1)
    if git_blob_sha(changed) != MERGED_GIT_BLOB:
        raise ValueError('derived merged FTS design is not upstream Git blob')
    return changed


class InstalledDesignGenerations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.historical = SOURCE.read_bytes()
        if git_blob_sha(cls.historical) != HISTORICAL_GIT_BLOB:
            raise ValueError('expected historical server FTS source pin')
        cls.merged = merged_source(cls.historical)

    def test_exact_merged_source_is_not_an_unpinned_substitute(self):
        self.assertEqual(git_blob_sha(self.merged), MERGED_GIT_BLOB)
        self.assertEqual(git_blob_sha(self.historical), HISTORICAL_GIT_BLOB)

    def test_historical_default_unchanged(self):
        self.assertEqual(compare_exported_design(
            self.historical, self.historical)['status'], 'MATCH')

    def test_explicit_historical(self):
        self.assertEqual(compare_exported_design(
            self.historical, self.historical, 'historical')['generation'], 'historical')

    def test_explicit_merged_can_attest_export(self):
        answer = compare_exported_design(self.merged, self.merged, 'merged')
        self.assertEqual(answer['status'], 'MATCH')
        self.assertEqual(answer['generation'], 'merged')
        self.assertEqual(answer['source_git_blob'], MERGED_GIT_BLOB)

    def test_merged_does_not_pass_historical_default(self):
        with self.assertRaisesRegex(ValueError, 'Git blob'):
            compare_exported_design(self.merged, self.merged)

    def test_mislabeled_historical_is_not_merged(self):
        with self.assertRaisesRegex(ValueError, 'Git blob'):
            compare_exported_design(self.historical, self.historical, 'merged')

    def test_unknown_generation_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unknown pinned'):
            compare_exported_design(self.historical, self.historical, 'latest')

    def test_merged_source_drift_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Git blob'):
            compare_exported_design(self.merged + b'\\n', self.merged, 'merged')

    def test_merged_installed_analyzer_drift_rejected(self):
        modified = json.loads(self.merged)
        modified['indexes']['fts']['analyzer']['fields']['dataset'] = 'standard'
        with self.assertRaisesRegex(ValueError, 'FTS definition differs'):
            compare_exported_design(self.merged, json.dumps(modified).encode(), 'merged')

    def test_merged_export_storage_revision_is_not_fts_drift(self):
        exported = json.loads(self.merged)
        exported['_rev'] = '9-synthetic'
        self.assertEqual(compare_exported_design(
            self.merged, json.dumps(exported).encode(), 'merged')['status'], 'MATCH')

    def test_cli_requires_explicit_merged_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.json'
            exported = Path(folder) / 'installed.json'
            source.write_bytes(self.merged)
            exported.write_bytes(self.merged)
            helper = Path(__file__).resolve().parent / 'verify_installed_design.py'
            command = [sys.executable, str(helper), str(source), str(exported)]
            default = subprocess.run(command, text=True, capture_output=True)
            self.assertNotEqual(default.returncode, 0)
            explicit = subprocess.run(command + ['--generation', 'merged'],
                                      text=True, capture_output=True)
            self.assertEqual(explicit.returncode, 0, explicit.stderr)
            self.assertEqual(json.loads(explicit.stdout)['source_git_blob'],
                             MERGED_GIT_BLOB)


if __name__ == '__main__':
    unittest.main()
