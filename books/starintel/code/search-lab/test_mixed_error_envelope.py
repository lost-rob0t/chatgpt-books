"""An explicit search error must take precedence over rows in a decoded page."""
import unittest

from lab import interpret_page


def synthetic_row():
    return {'id': 'org:synthetic',
            'fields': {'dtype': 'org', 'dataset': 'book-synthetic'},
            'doc': {'_id': 'org:synthetic', '_rev': '1-synthetic',
                    'dtype': 'org', 'dataset': 'book-synthetic'}}


class MixedEnvelopeTests(unittest.TestCase):
    def test_empty_rows_with_explicit_error_is_failure(self):
        with self.assertRaises(ValueError):
            interpret_page({'rows': [], 'bookmark': None, 'error': 'forbidden'})

    def test_populated_rows_with_explicit_error_is_failure(self):
        with self.assertRaises(ValueError):
            interpret_page({'rows': [synthetic_row()], 'error': 'backend_error'})

    def test_error_key_present_even_when_null_is_failure(self):
        with self.assertRaises(ValueError):
            interpret_page({'rows': [], 'error': None})

    def test_normal_empty_page_is_not_error(self):
        self.assertEqual(interpret_page({'rows': [], 'bookmark': None}), ([], None))

    def test_normal_page_preserves_document_and_fields(self):
        hits, bookmark = interpret_page({'rows': [synthetic_row()], 'bookmark': 'opaque'})
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].storage_revision, '1-synthetic')
        self.assertEqual(hits[0].dataset, 'book-synthetic')
        self.assertEqual(bookmark, 'opaque')

    def test_error_only_envelope_fails(self):
        with self.assertRaises(ValueError):
            interpret_page({'error': 'not_found'})


if __name__ == '__main__':
    unittest.main()
