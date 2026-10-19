"""Prove the five historical HTTP seed fixtures actually emit queryable fname evidence.

Requires the same pinned historical server checkout as the Chapter 15 test runner.
A Node index callback proves raw field emission, NOT Lucene tokenization,
authorization, service deployment, or tenant adaptation.
"""
import os
from pathlib import Path
import unittest

from lab import projection
from service_checks import fixture, fixture_dataset

SERVER = Path(os.environ['STAR_SEARCH_LAB_SERVER'])
NEEDLE = 'bookneedlefixedcase'


def values(document, field):
    return [entry['value'] for entry in projection(SERVER, document)
            if entry['field'] == field]


class HistoricalSeedProjectionTests(unittest.TestCase):
    def test_all_five_seeds_emit_exact_fielded_search_term_and_dataset(self):
        expected = ['book-public', 'book-public', 'book-public',
                    'book-private', 'book-other-public']
        for i, dataset in enumerate(expected):
            with self.subTest(ordinal=i):
                identity = f'starintel:person:seed-index-{i}'
                document = fixture(identity, fixture_dataset(i), NEEDLE)
                self.assertEqual(document['_id'], identity)
                self.assertEqual(document['schema_version'], '0.9.0')
                self.assertNotIn('tenant_id', document)
                self.assertNotIn('tenant', document)
                self.assertEqual(values(document, 'fname'), [NEEDLE])
                self.assertEqual(values(document, 'dataset'), [dataset])
                self.assertEqual(values(document, 'dtype'), ['person'])

    def test_nested_fname_is_selected_even_with_conflicting_root_fname(self):
        document = fixture('starintel:person:shadow', 'book-public', NEEDLE)
        document['fname'] = 'wrong-root-value'
        self.assertEqual(values(document, 'fname'), [NEEDLE])

    def test_null_nested_fname_suppresses_root_fallback(self):
        document = fixture('starintel:person:null-shadow', 'book-public', NEEDLE)
        document['fname'] = NEEDLE
        document['data']['fname'] = None
        self.assertEqual(values(document, 'fname'), [])

    def test_absent_nested_fname_falls_back_to_root(self):
        document = fixture('starintel:person:root-fallback', 'book-public', NEEDLE)
        document['data'].pop('fname')
        document['fname'] = NEEDLE
        self.assertEqual(values(document, 'fname'), [NEEDLE])

    def test_schema_version_is_not_an_fts_field(self):
        document = fixture('starintel:person:version', 'book-public', NEEDLE)
        self.assertEqual(values(document, 'schema_version'), [])


if __name__ == '__main__':
    unittest.main()
