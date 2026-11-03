"""Historical source-verified search-client paging contract, no server double."""
import unittest
from urllib.parse import parse_qs, urlsplit

import lab as mod


class NoFalseOffsetContract(unittest.TestCase):
    def test_public_offset_parameters_are_not_pagination(self):
        for key in ('skip', 'offset'):
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, 'does not forward skip/offset'):
                    mod.request_path('public', 'name:synthetic', **{key: 8})

    def test_authenticated_offset_parameters_are_not_pagination(self):
        for key in ('skip', 'offset'):
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, 'does not forward skip/offset'):
                    mod.request_path('authenticated', 'name:synthetic', **{key: 8})

    def test_falsey_skip_is_still_explicitly_rejected(self):
        for surface in ('public', 'authenticated'):
            for key in ('skip', 'offset'):
                for value in (0, None, ''):
                    with self.subTest(surface=surface, key=key, value=value):
                        with self.assertRaisesRegex(ValueError, 'does not forward skip/offset'):
                            mod.request_path(surface, 'name:synthetic', **{key: value})

    def test_public_bookmark_query_and_limit_still_encoded(self):
        result = mod.request_path('public', 'name:"A&B"', limit=1, bookmark='next+/=')
        self.assertEqual(urlsplit(result).path, '/api/v1/search')
        self.assertEqual(parse_qs(urlsplit(result).query),
                         {'q': ['name:"A&B"'], 'limit': ['1'], 'bookmark': ['next+/=']})

    def test_authenticated_sort_and_scope_still_encoded(self):
        result = mod.request_path('authenticated', 'name:synthetic', sort='-name',
                                  tenant='default', dataset='book-public', limit=1)
        self.assertEqual(urlsplit(result).path, '/api/v1/documents/search')
        self.assertEqual(parse_qs(urlsplit(result).query),
                         {'q': ['name:synthetic'], 'sort': ['-name'],
                          'tenant': ['default'], 'dataset': ['book-public'], 'limit': ['1']})

    def test_public_sort_stays_forbidden(self):
        with self.assertRaisesRegex(ValueError, 'does not forward sort'):
            mod.request_path('public', 'name:synthetic', sort='')

    def test_unknown_surface_stays_forbidden(self):
        with self.assertRaisesRegex(ValueError, 'unknown search surface'):
            mod.request_path('raw', 'name:synthetic')


if __name__ == '__main__':
    unittest.main()
