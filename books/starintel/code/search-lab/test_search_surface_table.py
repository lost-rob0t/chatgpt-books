"""Regression for the rendered Chapter 15 search contract comparison table."""
from pathlib import Path
import unittest

MANUSCRIPT = Path(__file__).resolve().parents[2] / 'manuscript/search-15.org'
CAPTION = '#+caption: Public and authenticated search contract differences.'
BACKEND = '| Backend request | =search/fts=, =include_docs=true= | =search/fts=, =include_docs=true= |'
SORT = '| =sort= forwarding | Not forwarded by this handler | Forwarded if supplied |'


def comparison_rows(source: str) -> list[str]:
    lines = source.splitlines()
    matches = [i for i, line in enumerate(lines) if line == CAPTION]
    if len(matches) != 1:
        raise ValueError('exactly one Chapter 15 search comparison caption required')
    start = matches[0] + 1
    rows = []
    for line in lines[start:]:
        if not line.startswith('|'):
            break
        rows.append(line)
    return rows


class SearchSurfaceTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MANUSCRIPT.read_text(encoding='utf-8')
        cls.rows = comparison_rows(cls.source)

    def test_backend_request_is_inside_original_comparison_table(self):
        self.assertIn(BACKEND, self.rows)

    def test_sort_and_backend_evidence_are_adjacent(self):
        self.assertIn(SORT, self.rows)
        self.assertIn(BACKEND, self.rows)
        self.assertEqual(self.rows.index(BACKEND), self.rows.index(SORT) + 1)

    def test_backend_request_is_present_exactly_once(self):
        self.assertEqual(self.source.splitlines().count(BACKEND), 1)

    def test_comparison_has_three_columns(self):
        data_rows = [row for row in self.rows if not row.startswith('|---')]
        self.assertGreaterEqual(len(data_rows), 10)
        self.assertTrue(all(row.count('|') == 4 for row in data_rows)


if __name__ == '__main__':
    unittest.main()
