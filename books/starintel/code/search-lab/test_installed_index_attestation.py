"""Network-free regressions against the source-pinned CouchDB FTS design contract."""
import copy
import json
import os
import unittest
from pathlib import Path
from verify_installed_design import compare_exported_design, HISTORICAL_GIT_BLOB, git_blob_sha

FIXTURE = (Path(os.environ['STAR_SEARCH_LAB_SERVER']) / 'source/views/search.json').read_bytes()


def encoded(value):
    return json.dumps(value, separators=(',', ':')).encode()


class InstalledIndexContractTests(unittest.TestCase):
    def setUp(self):
        self.installed = json.loads(FIXTURE)

    def compare(self):
        return compare_exported_design(FIXTURE, encoded(self.installed))

    def test_exact_original_design_matches(self):
        self.assertEqual(git_blob_sha(FIXTURE), HISTORICAL_GIT_BLOB)
        self.assertEqual(self.compare()['status'], 'MATCH')

    def test_couchdb_storage_revision_not_a_projection_change(self):
        self.installed['_rev'] = '17-example'
        self.installed['views'] = {'unrelated': {'map': 'function(doc){}'}}
        self.assertEqual(self.compare()['status'], 'MATCH')

    def test_index_function_drift_fails(self):
        self.installed['indexes']['fts']['index'] += ' '
        with self.assertRaisesRegex(ValueError, 'FTS definition differs'):
            self.compare()

    def test_analyzer_drift_fails(self):
        self.installed['indexes']['fts']['analyzer']['fields']['name'] = 'standard'
        with self.assertRaisesRegex(ValueError, 'FTS definition differs'):
            self.compare()

    def test_missing_fts_fails(self):
        self.installed['indexes'].pop('fts')
        with self.assertRaisesRegex(ValueError, 'missing FTS'):
            self.compare()

    def test_wrong_design_identity_fails(self):
        self.installed['_id'] = '_design/something-else'
        with self.assertRaisesRegex(ValueError, 'not the expected'):
            self.compare()

    def test_source_pin_mismatch_fails(self):
        with self.assertRaisesRegex(ValueError, 'Git blob'):
            compare_exported_design(FIXTURE + b'\n', FIXTURE)

    def test_malformed_export_fails(self):
        with self.assertRaisesRegex(ValueError, 'not valid JSON'):
            compare_exported_design(FIXTURE, b'{')

    def test_wrong_json_type_fails(self):
        with self.assertRaisesRegex(ValueError, 'not the expected'):
            compare_exported_design(FIXTURE, b'[]')


if __name__ == '__main__':
    unittest.main()
