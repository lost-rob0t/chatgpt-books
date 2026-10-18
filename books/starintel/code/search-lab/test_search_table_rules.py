"""Native regression cases for Chapter 15 Org evidence table shapes."""
import unittest
from pathlib import Path

from check_search_table_rules import table_issues


GOOD = '''| Observation | Supported claim | Missing proof |
|-------------+-----------------+---------------|
| Search row | One matching result | Durable read |
| Canonical read | One versioned record | Index coverage |
'''
BAD = GOOD.replace('|-------------+-----------------+---------------|', '|-')


class TableShapeTests(unittest.TestCase):
    def test_complete_rule(self):
        self.assertEqual(table_issues(GOOD), [])

    def test_abbreviated_rule_is_a_source_style_regression(self):
        self.assertEqual(table_issues(BAD), ['line 2: separator must cover 3 columns'])

    def test_wrong_number_of_rule_segments(self):
        self.assertIn('line 2: separator must cover 3 columns',
                      table_issues(GOOD.replace('|-------------+-----------------+---------------|',
                                                '|-------+-------------|')))

    def test_ragged_data_row(self):
        self.assertIn('line 3: expected 3 cells',
                      table_issues(GOOD.replace('| Search row | One matching result | Durable read |',
                                                '| Search row | Durable read |')))

    def test_missing_rule_is_not_a_fabricated_failure(self):
        self.assertEqual(table_issues('| Left | Right |\n| A | B |\n'), [])

    def test_separate_table_blocks(self):
        self.assertEqual(table_issues(GOOD + '\nElsewhere\n\n' + GOOD), [])

    def test_literal_pipe_inside_escaped_text(self):
        sample = GOOD.replace('Search row', r'Search \| row')
        self.assertEqual(table_issues(sample), [])

    def test_source_and_example_blocks_are_not_manuscript_tables(self):
        sample = ('#+begin_src text\n' + BAD + '#+end_src\n'
                  '#+begin_example\n' + BAD + '#+end_example\n' + GOOD)
        self.assertEqual(table_issues(sample), [])

    def test_line_number_is_from_full_document(self):
        self.assertEqual(table_issues('Introduction\n\n' + BAD),
                         ['line 4: separator must cover 3 columns'])

    def test_full_chapter_when_authentic_checkout_available(self):
        chapter = Path(__file__).resolve().parents[2] / 'manuscript/search-15.org'
        if not chapter.is_file():
            self.skipTest('authentic complete chapter checkout unavailable locally')
        self.assertEqual(table_issues(chapter.read_text(encoding='utf-8')), [])

    def test_actual_analysis_evidence_table_before_repair_is_red(self):
        original = '''| Distinct observation | What it establishes | What it does not establish |
|-
| Search hit | A query surfaced a scoped projected record | Which conclusion was accepted, or whether the revision is current |
| Authorized canonical by-ID read | The returned document fields and revision at read time | That the analytical method or cited evidence is valid |
| Verified sources and reasoning | A bounded basis for independently evaluating an asserted conclusion | Search index freshness or authorization to other datasets |'''
        self.assertEqual(table_issues(original), ['line 2: separator must cover 3 columns'])
        repaired = original.replace('\n|-\n', '\n|----------------------+--------------------------+----------------------------|\n')
        self.assertEqual(table_issues(repaired), [])


if __name__ == '__main__':
    unittest.main()
