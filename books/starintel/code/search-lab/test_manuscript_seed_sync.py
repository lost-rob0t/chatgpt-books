"""Catch divergence between the Chapter 15 teaching deployment and fixture contract."""
from pathlib import Path
import re
import unittest


HERE = Path(__file__).resolve().parent
MANUSCRIPT = HERE.parents[1] / 'manuscript' / 'search-15.org'
PUBLIC_DATASETS = {'book-public', 'book-other-public'}


class ManuscriptSeedSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = MANUSCRIPT.read_text(encoding='utf-8')
        cls.flattened = ' '.join(cls.text.split())

    def test_documented_public_dataset_list_matches_fixture(self):
        match = re.search(r'^STAR_PUBLIC_SEARCH_DATASETS=([a-zA-Z0-9_,-]+)$',
                          self.text, flags=re.MULTILINE)
        self.assertIsNotNone(match, 'explicit public dataset setting is missing')
        self.assertEqual(set(match.group(1).split(',')), PUBLIC_DATASETS)

    def test_documented_server_side_tenant_adaptation(self):
        self.assertIn('STAR_TENANT_DATASET_MAP=book-other-public=other',
                      self.text)

    def test_fifth_seed_is_described_under_its_actual_dataset(self):
        self.assertIn('one to =book-other-public= in =other=', self.flattened)

    def test_public_and_reader_views_are_distinguished(self):
        self.assertIn('reader only receives =book-public= from tenant =default=',
                      self.flattened)


if __name__ == '__main__':
    unittest.main()
