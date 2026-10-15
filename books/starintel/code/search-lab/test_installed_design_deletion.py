"""Offline FTS design export: a matching tombstone is not an installed design."""
import json
import os
from pathlib import Path
import unittest
import verify_installed_design as under_test

HERE = Path(__file__).resolve().parent
HISTORICAL = (Path(os.environ['STAR_SEARCH_LAB_SERVER']) / 'source/views/search.json').read_bytes()


def merged_source():
    source = HISTORICAL
    for before, after in (
        (b"'full_name','content'", b"'full_name','fullName','content'"),
        (b"'display_name','legal_name','group'", b"'display_name','displayName','legal_name','legalName','group'"),
        (b"'org_type'];", b"'org_type','orgType'];"),
    ):
        assert source.count(before) == 1
        source = source.replace(before, after)
    assert under_test.git_blob_sha(source) == under_test.MERGED_GIT_BLOB
    return source


def export_with(source, **metadata):
    doc = json.loads(source)
    doc.update(metadata)
    return json.dumps(doc).encode('utf-8')


class DesignLivenessTests(unittest.TestCase):
    def test_historical_source_is_exact_pinned_original(self):
        self.assertEqual(under_test.git_blob_sha(HISTORICAL), under_test.HISTORICAL_GIT_BLOB)
        self.assertEqual(under_test.compare_exported_design(HISTORICAL, HISTORICAL)['status'], 'MATCH')

    def test_merged_source_is_exact_pinned_original(self):
        merged = merged_source()
        self.assertEqual(under_test.compare_exported_design(merged, merged, 'merged')['status'], 'MATCH')

    def test_live_export_with_revision_is_not_rejected(self):
        self.assertEqual(under_test.compare_exported_design(HISTORICAL, export_with(HISTORICAL, _rev='4-demo'))['status'], 'MATCH')

    def test_explicit_false_not_deleted_is_allowed(self):
        self.assertEqual(under_test.compare_exported_design(HISTORICAL, export_with(HISTORICAL, _deleted=False))['status'], 'MATCH')

    def test_historical_deleted_design_must_not_match(self):
        with self.assertRaisesRegex(ValueError, 'deleted'):
            under_test.compare_exported_design(HISTORICAL, export_with(HISTORICAL, _deleted=True))

    def test_merged_deleted_design_must_not_match(self):
        merged = merged_source()
        with self.assertRaisesRegex(ValueError, 'deleted'):
            under_test.compare_exported_design(merged, export_with(merged, _deleted=True), 'merged')

    def test_nonboolean_deleted_flag_must_not_match(self):
        for value in ('true', 1, None, {}, []):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'deleted'):
                under_test.compare_exported_design(HISTORICAL, export_with(HISTORICAL, _deleted=value))

    def test_index_function_drift_still_fails(self):
        doc = json.loads(HISTORICAL)
        doc['indexes']['fts']['index'] += ' '
        with self.assertRaisesRegex(ValueError, 'FTS definition differs'):
            under_test.compare_exported_design(HISTORICAL, json.dumps(doc).encode())


if __name__ == '__main__':
    unittest.main()
