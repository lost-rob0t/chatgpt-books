"""Native, network-free checks of the Chapter 15 Org-to-BibTeX key boundary."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from check_search_citations import CitationError, check, main


BIB = '''@misc{server-search,
 title={Pinned source},
}
@article{couchdb-api,
 title={Search API},
}
'''


class CitationKeyTests(unittest.TestCase):
    def test_one_resolved_citation(self):
        self.assertEqual(check('[cite:@server-search]', BIB),
                         {'citation_groups': 1, 'references': 1,
                          'unique_cited_keys': 1, 'bibliography_entries': 2})

    def test_multiline_citation_group(self):
        report = check('[cite:@server-search;\n@couchdb-api; @server-search]', BIB)
        self.assertEqual(report['references'], 3)
        self.assertEqual(report['unique_cited_keys'], 2)

    def test_org_citation_style(self):
        self.assertEqual(check('[cite/t:@server-search]', BIB)['references'], 1)

    def test_undefined_citation_rejected(self):
        with self.assertRaisesRegex(CitationError, 'undefined citation keys: missing'):
            check('[cite:@missing]', BIB)

    def test_case_sensitive_citation_resolution(self):
        with self.assertRaisesRegex(CitationError, 'undefined citation keys'):
            check('[cite:@SERVER-search]', BIB)

    def test_missing_keys_are_sorted_for_diagnostics(self):
        with self.assertRaisesRegex(CitationError, 'undefined citation keys: a, z'):
            check('[cite:@z; @a]', BIB)

    def test_duplicate_bibtex_key_rejected(self):
        with self.assertRaisesRegex(CitationError, 'duplicate bibliography key: server-search'):
            check('[cite:@server-search]', BIB + '@book{server-search, title={Drift}}')

    def test_no_citation_group_rejected(self):
        with self.assertRaisesRegex(CitationError, 'no Org citations'):
            check('Source metadata is elsewhere.', BIB)

    def test_group_without_key_rejected(self):
        with self.assertRaisesRegex(CitationError, 'no @key'):
            check('[cite: missing marker]', BIB)

    def test_truncated_group_rejected(self):
        with self.assertRaisesRegex(CitationError, 'unterminated'):
            check('Claim [cite:@server-search', BIB)

    def test_bibtex_special_blocks_are_not_references(self):
        bib = '@string{alias, fake}\n@comment{fake, note}\n' + BIB
        with self.assertRaisesRegex(CitationError, 'undefined citation keys: fake'):
            check('[cite:@fake]', bib)

    def test_noncitation_text_not_counted(self):
        report = check('raw @nonexistent and [cite:@server-search]', BIB)
        self.assertEqual(report['references'], 1)

    def test_parenthesized_bibtex_entry(self):
        bib = '@book(alt-source, title={Other})\n' + BIB
        self.assertEqual(check('[cite:@alt-source]', bib)['references'], 1)

    def test_cli_validates_files_and_reports_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'chapter.org').write_text('[cite:@server-search]', encoding='utf-8')
            (p / 'refs.bib').write_text(BIB, encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main([str(p / 'chapter.org'), str(p / 'refs.bib')]), 0)
            self.assertIn('"citation_groups": 1', stdout.getvalue())

    def test_cli_exits_nonzero_on_missing_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'chapter.org').write_text('[cite:@missing]', encoding='utf-8')
            (p / 'refs.bib').write_text(BIB, encoding='utf-8')
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    main([str(p / 'chapter.org'), str(p / 'refs.bib')])
            self.assertEqual(result.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
