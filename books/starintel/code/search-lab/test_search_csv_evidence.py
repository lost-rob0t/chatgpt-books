"""Native hermetic tests for the Chapter 15 text-encoded CSV evidence preview."""
import csv
from io import StringIO
import json
from types import SimpleNamespace
import unittest

from search_csv_evidence import COLUMNS, MAX_ROWS, export_hit_page, text_cell


def hit(identity='doc-1', dtype='person', dataset='book-public', canonical_revision='r1', storage_revision='2-abc', **extra):
    return SimpleNamespace(identity=identity, dtype=dtype, dataset=dataset,
                           canonical_revision=canonical_revision, storage_revision=storage_revision,
                           **extra)


def rows(payload):
    return list(csv.reader(StringIO(payload, newline='')))


class SearchCsvEvidenceTests(unittest.TestCase):
    def test_reversible_plain_values_have_an_explicit_text_prefix(self):
        row = rows(export_hit_page([hit()]))[1]
        self.assertEqual([json.loads(cell[2:]) for cell in row],
                         ['doc-1', 'person', 'book-public', 'r1', '2-abc'])
        self.assertTrue(all(cell.startswith('s:') for cell in row))

    def test_formula_starts_are_not_at_start_of_exported_cells(self):
        probes = ['=1+2', '+SUM(A1)', '-1+2', '@SUM(1)', '＝2+2', '＋2', '－3', '＠foo']
        for value in probes:
            with self.subTest(value=value):
                cell = rows(export_hit_page([hit(identity=value)]))[1][0]
                self.assertEqual(cell[:2], 's:')
                self.assertEqual(json.loads(cell[2:]), value)

    def test_leading_whitespace_or_control_cannot_reveal_formula_prefix(self):
        for prefix in (' ', '\t', '\r', '\n', '\ufeff', '\u200b'):
            raw = prefix + '=1+2'
            with self.subTest(prefix=prefix):
                cell = rows(export_hit_page([hit(identity=raw)]))[1][0]
                self.assertTrue(cell.startswith('s:"'))
                self.assertEqual(json.loads(cell[2:]), raw)

    def test_delimiter_quote_and_newline_do_not_create_extra_rows(self):
        value = 'a","=2+2\r\nother row,"tail"'
        result = rows(export_hit_page([hit(identity=value)]))
        self.assertEqual(len(result), 2)
        self.assertEqual(len(result[1]), len(COLUMNS))
        self.assertEqual(json.loads(result[1][0][2:]), value)

    def test_unicode_bidi_and_control_bytes_are_visibly_escaped(self):
        cell = rows(export_hit_page([hit(identity='x\u202e\x00\x1fy')]))[1][0]
        self.assertIn('\\u202e', cell)
        self.assertIn('\\u0000', cell)
        self.assertIn('\\u001f', cell)
        self.assertNotIn('\u202e', cell)
        self.assertEqual(json.loads(cell[2:]), 'x\u202e\x00\x1fy')

    def test_null_is_not_confusable_with_literal_null(self):
        result = rows(export_hit_page([hit(dtype=None, dataset='null')]))[1]
        self.assertEqual(result[1], 'null')
        self.assertEqual(result[2], 's:"null"')

    def test_omits_nested_documents_stored_fields_scores_and_bookmarks(self):
        value = '=DO_NOT_EXPORT'
        payload = export_hit_page([hit(document={'secret': value}, fields={'tenant_id': value},
                                       score=value, bookmark=value)])
        self.assertNotIn('secret', payload)
        self.assertNotIn('tenant_id', payload)
        self.assertNotIn('DO_NOT_EXPORT', payload)
        self.assertEqual(rows(payload)[0], list(COLUMNS))

    def test_rejects_nonstring_scalar_instead_of_converting_to_text(self):
        for value in (0, True, [], {'a': 'b'}, 1.5):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    export_hit_page([hit(dtype=value)])

    def test_rejects_empty_or_missing_identity(self):
        with self.assertRaises(ValueError):
            export_hit_page([hit(identity='')])
        with self.assertRaises(ValueError):
            export_hit_page([SimpleNamespace(dtype='person')])

    def test_limit_exactly_hundred_then_rejects_more(self):
        self.assertEqual(len(rows(export_hit_page([hit(identity=str(i)) for i in range(MAX_ROWS)]))), MAX_ROWS + 1)
        with self.assertRaises(ValueError):
            export_hit_page([hit(identity=str(i)) for i in range(MAX_ROWS + 1)])

    def test_rejects_unbounded_or_lazy_input(self):
        for value in (None, (hit(x) for x in ['a']), {'hits': []}, 'abc'):
            with self.subTest(value=type(value)):
                with self.assertRaises(ValueError):
                    export_hit_page(value)

    def test_rejects_oversized_cell_without_truncating_evidence(self):
        with self.assertRaises(ValueError):
            text_cell('x' * 4097)

    def test_empty_page_exports_only_header(self):
        self.assertEqual(rows(export_hit_page([])), [list(COLUMNS)])

    def test_utf8_scalar_is_roundtrippable_without_emitting_codepoint(self):
        value = 'café ☃'
        payload = export_hit_page([hit(identity=value)])
        self.assertEqual(json.loads(rows(payload)[1][0][2:]), value)
        self.assertNotIn('☃', payload)


if __name__ == '__main__':
    unittest.main()
