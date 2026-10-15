"""Pinned public-sort parameter contract: the public handler ignores sort."""
import unittest
from urllib.parse import parse_qs, urlsplit
from lab import request_path


class PublicSortBoundaryTests(unittest.TestCase):
    def test_public_sort_rejected(self):
        with self.assertRaisesRegex(ValueError, 'public.*sort'):
            request_path('public', 'name:synthetic', sort='["name<string>"]')

    def test_public_sort_with_bookmark_rejected(self):
        with self.assertRaisesRegex(ValueError, 'public.*sort'):
            request_path('public', 'name:synthetic', bookmark='opaque+/=', sort='name')

    def test_explicit_empty_public_sort_rejected(self):
        with self.assertRaisesRegex(ValueError, 'public.*sort'):
            request_path('public', 'name:synthetic', sort='')

    def test_normal_public_request_still_encoded(self):
        path = request_path('public', 'name:"A&B"', limit=1, bookmark='opaque+/=')
        self.assertEqual(urlsplit(path).path, '/api/v1/search')
        self.assertEqual(parse_qs(urlsplit(path).query), {
            'q': ['name:"A&B"'], 'limit': ['1'], 'bookmark': ['opaque+/=']})

    def test_authenticated_sort_passthrough_still_encoded(self):
        path = request_path('authenticated', 'name:synthetic', sort='["name<string>"]')
        self.assertEqual(urlsplit(path).path, '/api/v1/documents/search')
        self.assertEqual(parse_qs(urlsplit(path).query)['sort'], ['["name<string>"]'])

    def test_unknown_surface_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'unknown search surface'):
            request_path('maybe', 'name:synthetic', sort='name')

if __name__ == '__main__':
    unittest.main()
