"""Network-free native regressions for inert Chapter 15 source examples."""
import unittest
from check_search_examples import ExampleError, check


class ChapterExamples(unittest.TestCase):
    def test_valid_multiple_languages(self):
        source = ("#+begin_src json\n{\"name\": \"synthetic\"}\n#+end_src\n"
                  "#+begin_src python\nassert (1 + 1) == 2\n#+end_src\n"
                  "#+begin_src sh\necho hello\n#+end_src\n")
        self.assertEqual(check(source), {'json': 1, 'python': 1, 'sh': 1, 'bash': 0})

    def test_valid_json_heredoc(self):
        self.assertEqual(check("#+begin_src sh\ncat <<'JSON'\n{\"ok\":true}\nJSON\n#+end_src"),
                         {'json': 0, 'python': 0, 'sh': 1, 'bash': 0})

    def test_source_python_is_not_executed(self):
        self.assertEqual(check("#+begin_src python\nraise RuntimeError('would run')\n#+end_src"),
                         {'json': 0, 'python': 1, 'sh': 0, 'bash': 0})

    def test_invalid_json(self):
        with self.assertRaisesRegex(ExampleError, 'invalid JSON'):
            check('#+begin_src json\n{"x":}\n#+end_src')

    def test_duplicate_json_keys(self):
        with self.assertRaisesRegex(ExampleError, 'duplicate JSON key'):
            check('#+begin_src json\n{"x":1,"x":2}\n#+end_src')

    def test_non_json_constant(self):
        with self.assertRaisesRegex(ExampleError, 'non-JSON constant'):
            check('#+begin_src json\n{"x": NaN}\n#+end_src')

    def test_malformed_python(self):
        with self.assertRaisesRegex(ExampleError, 'invalid Python'):
            check('#+begin_src python\nif True print(1)\n#+end_src')

    def test_broken_bash_quote(self):
        with self.assertRaisesRegex(ExampleError, 'invalid Bash'):
            check("#+begin_src sh\necho 'broken\n#+end_src")

    def test_broken_json_in_heredoc(self):
        with self.assertRaisesRegex(ExampleError, 'invalid JSON'):
            check("#+begin_src sh\ncat <<'JSON'\n{\"x\": }\nJSON\n#+end_src")

    def test_missing_heredoc_terminator(self):
        with self.assertRaisesRegex(ExampleError, 'invalid Bash|missing JSON'):
            check("#+begin_src sh\ncat <<'JSON'\n{\"x\":1}\n#+end_src")

    def test_unterminated_org_block(self):
        with self.assertRaisesRegex(ExampleError, 'unterminated'):
            check('#+begin_src python\nprint(1)')

    def test_nested_source_block(self):
        with self.assertRaisesRegex(ExampleError, 'nested'):
            check('#+begin_src python\n#+begin_src sh\n#+end_src')

    def test_stray_source_ending(self):
        with self.assertRaisesRegex(ExampleError, 'stray'):
            check('#+end_src')

    def test_unreviewed_language_fails_closed(self):
        with self.assertRaisesRegex(ExampleError, 'unreviewed'):
            check('#+begin_src lisp\n(+ 1 2)\n#+end_src')

    def test_empty_doc_is_not_a_pass(self):
        with self.assertRaisesRegex(ExampleError, 'no source'):
            check('* Chapter 15\nNo examples here.')

    def test_case_insensitive_org_directives(self):
        self.assertEqual(check('#+BEGIN_SRC JSON\n{}\n#+END_SRC'),
                         {'json': 1, 'python': 0, 'sh': 0, 'bash': 0})


if __name__ == '__main__':
    unittest.main()
