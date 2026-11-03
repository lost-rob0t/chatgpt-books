"""A stored search projection and embedded document are separate evidence."""
from copy import deepcopy
import unittest
from lab import interpret_page


def example_page():
    return {
        'rows': [{
            'id': 'person:book',
            'fields': {'dtype': 'person', 'dataset': 'book-public', 'fname': 'Example'},
            'doc': {'_id': 'person:book', '_rev': '1-demo',
                    'dtype': 'person', 'dataset': 'book-public'},
        }],
        'bookmark': 'opaque',
    }


class IndexDocumentConsistencyTests(unittest.TestCase):
    def test_matching_index_and_document_are_preserved(self):
        hits, bookmark = interpret_page(example_page())
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].revision, '1-demo')
        self.assertEqual(hits[0].dataset, 'book-public')
        self.assertEqual(bookmark, 'opaque')

    def test_stored_dataset_disagreement_is_not_silently_resolved(self):
        page = example_page()
        page['rows'][0]['fields']['dataset'] = 'book-private'
        with self.assertRaisesRegex(ValueError, 'dataset.*disagree'):
            interpret_page(page)

    def test_stored_type_disagreement_is_not_silently_resolved(self):
        page = example_page()
        page['rows'][0]['fields']['dtype'] = 'relation'
        with self.assertRaisesRegex(ValueError, 'dtype.*disagree'):
            interpret_page(page)

    def test_absent_stored_metadata_is_not_invented(self):
        page = example_page()
        del page['rows'][0]['fields']['dataset']
        del page['rows'][0]['fields']['dtype']
        hits, _ = interpret_page(page)
        self.assertEqual(hits[0].dtype, 'person')
        self.assertEqual(hits[0].dataset, 'book-public')
        self.assertNotIn('dtype', hits[0].fields)

    def test_fields_only_hit_remains_fields_only(self):
        page = example_page()
        del page['rows'][0]['doc']
        hits, _ = interpret_page(page)
        self.assertIsNone(hits[0].document)
        self.assertEqual(hits[0].dataset, 'book-public')

    def test_existing_egress_tenant_guard_remains(self):
        page = example_page()
        page['rows'][0]['fields']['tenant_id'] = 'secret'
        with self.assertRaisesRegex(ValueError, 'tenancy metadata leaked'):
            interpret_page(page)

    def test_existing_revision_guard_remains(self):
        page = example_page()
        page['rows'][0]['doc']['_rev'] = 12
        with self.assertRaisesRegex(ValueError, 'invalid revision'):
            interpret_page(page)

    def test_existing_duplicate_hit_guard_remains(self):
        page = example_page()
        page['rows'].append(deepcopy(page['rows'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate identity'):
            interpret_page(page)


if __name__ == '__main__':
    unittest.main()
