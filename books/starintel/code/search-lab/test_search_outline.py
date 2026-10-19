"""Native regressions for the book's Chapter 15 Org heading hierarchy."""
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from check_search_outline import CHAPTER_ID, ROOT, inspect, main

EXAMPLE = f'''* Chapter 15 -- Source-grounded Search
:PROPERTIES:
:ID:       {CHAPTER_ID}
:END:
** Study case
#+begin_src python
* Not a real chapter
*** Exercise -- Not a real exercise
#+end_src
*** Exercise -- Sample
** Next case
*** Worked exercise -- Verify
'''


class SearchOutlineTests(unittest.TestCase):
    def test_valid_nested_exercises(self):
        self.assertEqual(inspect(EXAMPLE), [])

    def test_accidental_second_chapter_breaks_export_spine(self):
        broken = EXAMPLE + '* A fictional meeting accidentally becomes a chapter\n'
        self.assertRegex(' '.join(inspect(broken)), 'exactly one Chapter 15')

    def test_wrong_level_worked_exercise_rejected(self):
        broken = EXAMPLE.replace('*** Worked exercise', '** Worked exercise')
        self.assertRegex(' '.join(inspect(broken)), 'exercise must be level 3')

    def test_wrong_level_unparented_exercise_rejected(self):
        broken = EXAMPLE.replace('** Study case\n', '')
        broken = broken.replace('** Next case\n', '')
        self.assertRegex(' '.join(inspect(broken)), 'exercise must be level 3')

    def test_markup_inside_src_block_is_not_a_heading(self):
        self.assertEqual(inspect(EXAMPLE), [])

    def test_malformed_block_fails_closed(self):
        self.assertIn('unclosed Org block', ' '.join(inspect(EXAMPLE + '#+begin_example\n')))
        self.assertIn('unmatched Org block end', ' '.join(inspect(EXAMPLE + '#+end_src\n')))

    def test_stable_org_id_not_replaced(self):
        wrong = EXAMPLE.replace(CHAPTER_ID, 'some-other-id')
        self.assertRegex(' '.join(inspect(wrong)), 'stable Chapter 15 Org ID')

    def test_cli_exit_codes_and_line_diagnostics(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'lesson.org'
            p.write_text(EXAMPLE, encoding='utf-8')
            self.assertEqual(main([str(p)]), 0)
            p.write_text(EXAMPLE + '* accidental sibling\n', encoding='utf-8')
            self.assertEqual(main([str(p)]), 1)
            self.assertEqual(main([str(p), str(p)]), 2)
            proc = subprocess.run([sys.executable,
                str(Path(__file__).with_name('check_search_outline.py')), str(p)],
                text=True, capture_output=True)
            self.assertEqual(proc.returncode, 1)
            self.assertIn('exactly one Chapter 15', proc.stderr)

    def test_actual_chapter(self):
        self.assertTrue(ROOT.is_file(), f'Chapter 15 not found at {ROOT}')
        self.assertEqual(inspect(ROOT.read_text(encoding='utf-8')), [])


if __name__ == '__main__':
    unittest.main()
