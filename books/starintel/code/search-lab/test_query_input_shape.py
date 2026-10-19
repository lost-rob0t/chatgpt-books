"""Source-exact Chapter 15 request_path input-shape regressions.

The pinned Lisp require-query-string accepts a nonempty string on either
surface. This is a client preflight, not an HTTP authorization substitute.
"""
from urllib.parse import parse_qs, urlsplit
import unittest
from lab import request_path


class QueryInputShape(unittest.TestCase):
    def test_public_empty_rejected(self):
        with self.assertRaisesRegex(ValueError, 'nonempty search query'):
            request_path('public', '')

    def test_authenticated_empty_rejected(self):
        with self.assertRaisesRegex(ValueError, 'nonempty search query'):
            request_path('authenticated', '')

    def test_public_none_rejected(self):
        with self.assertRaisesRegex(ValueError, 'nonempty search query'):
            request_path('public', None)

    def test_authenticated_none_rejected(self):
        with self.assertRaisesRegex(ValueError, 'nonempty search query'):
            request_path('authenticated', None)

    def test_bytes_not_a_valid_query_string(self):
        with self.assertRaisesRegex(ValueError, 'nonempty search query'):
            request_path('public', b'name:cooperative')

    def test_int_zero_not_a_valid_query_string(self):
        with self.assertRaisesRegex(ValueError, 'nonempty search query'):
            request_path('authenticated', 0)

    def test_list_not_a_valid_query_string(self):
        with self.assertRaisesRegex(ValueError, 'nonempty search query'):
            request_path('public', ['name:test'])

    def test_dictionary_not_a_valid_query_string(self):
        with self.assertRaisesRegex(ValueError, 'nonempty search query'):
            request_path('authenticated', {'q': 'x'})

    def test_false_not_a_valid_query_string(self):
        with self.assertRaisesRegex(ValueError, 'nonempty search query'):
            request_path('public', False)

    def test_required_string_is_kept_verbatim_not_trimmed(self):
        url = request_path('public', ' ')
        self.assertEqual(parse_qs(urlsplit(url).query, keep_blank_values=True)['q'], [' '])

    def test_unicode_and_reserved_characters_are_percent_encoded(self):
        q = 'name:Caf\u00e9 & (group:test)'
        url = request_path('authenticated', q)
        self.assertEqual(urlsplit(url).path, '/api/v1/documents/search')
        self.assertEqual(parse_qs(urlsplit(url).query)['q'], [q])

    def test_public_path_does_not_leak_into_authenticated_path(self):
        self.assertEqual(urlsplit(request_path('public', 'name:test')).path, '/api/v1/search')
        self.assertEqual(urlsplit(request_path('authenticated', 'name:test')).path,
                         '/api/v1/documents/search')

    def test_public_sort_still_rejected(self):
        with self.assertRaisesRegex(ValueError, 'does not forward sort'):
            request_path('public', 'name:test', sort='name')

    def test_offset_is_still_rejected(self):
        with self.assertRaisesRegex(ValueError, 'skip/offset'):
            request_path('authenticated', 'name:test', offset=0)

    def test_bookmark_preserved_as_opaque_string(self):
        url = request_path('public', 'name:test', bookmark='abc+/==')
        self.assertEqual(parse_qs(urlsplit(url).query)['bookmark'], ['abc+/=='])


if __name__ == '__main__':
    unittest.main()
