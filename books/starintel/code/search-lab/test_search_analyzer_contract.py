"""Pinned per-field analyzer contract; raw JS emission is not Lucene analysis."""
import json
import os
from pathlib import Path
import unittest

from lab import projection, require_pin, SERVER_PIN

SERVER = Path(os.environ['STAR_SEARCH_LAB_SERVER'])
DESIGN = SERVER / 'source/views/search.json'


class SearchAnalyzerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_pin(SERVER, SERVER_PIN)
        cls.fts = json.loads(DESIGN.read_text())['indexes']['fts']
        cls.analyzer = cls.fts['analyzer']

    def test_explicit_analyzer_mode_and_default(self):
        self.assertEqual(self.analyzer['name'], 'perfield')
        self.assertEqual(self.analyzer['default'], 'standard')

    def test_scope_dimensions_are_keyword_analyzed(self):
        for name in ('dataset', 'tenant_id'):
            with self.subTest(field=name):
                self.assertEqual(self.analyzer['fields'][name], 'keyword')

    def test_name_and_content_do_not_share_analyzers(self):
        self.assertEqual(self.analyzer['fields']['name'], 'keyword')
        self.assertEqual(self.analyzer['fields']['content'], 'standard')

    def test_dtype_and_title_use_standard_default(self):
        for name in ('dtype', 'title'):
            with self.subTest(field=name):
                self.assertNotIn(name, self.analyzer['fields'])
        self.assertEqual(self.analyzer['default'], 'standard')

    def test_real_index_emits_original_values_not_tokens(self):
        phrase = 'A & B Cooperative'
        events = projection(SERVER, {
            'dataset': 'book-public', 'tenant_id': 'default',
            'dtype': 'org', 'name': phrase, 'content': phrase,
        })
        for field, expected in (
            ('dataset', 'book-public'), ('tenant_id', 'default'),
            ('name', phrase), ('content', phrase),
        ):
            with self.subTest(field=field):
                matches = [item for item in events if item['field'] == field]
                self.assertEqual([item['value'] for item in matches], [expected])
                self.assertTrue(all(item['options']['store'] is True for item in matches))


if __name__ == '__main__':
    unittest.main()
