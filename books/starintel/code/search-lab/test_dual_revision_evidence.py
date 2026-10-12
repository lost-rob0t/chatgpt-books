"""Chapter 15: keep canonical rev and CouchDB _rev as separate evidence."""
import unittest
from lab import interpret_page


def page(doc=None):
    return {'bookmark': 'opaque', 'rows': [{
        'id': 'org:synthetic',
        'fields': {'dtype': 'org', 'dataset': 'book-public'},
        **({'doc': {'_id': 'org:synthetic', 'dtype': 'org',
                    'dataset': 'book-public', **doc}} if doc is not None else {}),
    }]}


class RevisionEvidenceSeparationTests(unittest.TestCase):
    def test_both_revisions_retain_different_authorities(self):
        hit = interpret_page(page({'_rev': '3-storage', 'rev': 'canonical-v9'}))[0][0]
        self.assertEqual(hit.storage_revision, '3-storage')
        self.assertEqual(hit.canonical_revision, 'canonical-v9')
        self.assertEqual(hit.revision, '3-storage')  # Old field remains compatible.

    def test_canonical_only_does_not_invent_couchdb_revision(self):
        hit = interpret_page(page({'rev': 'canonical-v1'}))[0][0]
        self.assertIsNone(hit.storage_revision)
        self.assertEqual(hit.canonical_revision, 'canonical-v1')
        self.assertEqual(hit.revision, 'canonical-v1')

    def test_storage_only_does_not_invent_canonical_revision(self):
        hit = interpret_page(page({'_rev': '2-couch'}))[0][0]
        self.assertEqual(hit.storage_revision, '2-couch')
        self.assertIsNone(hit.canonical_revision)
        self.assertEqual(hit.revision, '2-couch')

    def test_fields_only_proves_neither_revision(self):
        hit = interpret_page(page())[0][0]
        self.assertIsNone(hit.storage_revision)
        self.assertIsNone(hit.canonical_revision)
        self.assertIsNone(hit.revision)
        self.assertIsNone(hit.document)

    def test_shadowed_canonical_bad_type_is_not_ignored(self):
        for bad in (123, False, ['canonical']):
            with self.subTest(value=bad):
                with self.assertRaisesRegex(ValueError, 'invalid revision'):
                    interpret_page(page({'_rev': '3-couch', 'rev': bad}))

    def test_storage_bad_type_is_rejected_despite_valid_canonical(self):
        for bad in (123, False, ['couch']):
            with self.subTest(value=bad):
                with self.assertRaisesRegex(ValueError, 'invalid revision'):
                    interpret_page(page({'_rev': bad, 'rev': 'canonical-v1'}))

    def test_absent_revision_not_an_error(self):
        hit = interpret_page(page({}))[0][0]
        self.assertIsNone(hit.storage_revision)
        self.assertIsNone(hit.canonical_revision)
        self.assertIsNone(hit.revision)


if __name__ == '__main__':
    unittest.main()
