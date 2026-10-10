import unittest
from extract_forms import form

class ExtractionTests(unittest.TestCase):
    def test_string_and_comment_parentheses(self):
        source = '(defun wanted () "; ) (" ; )\n  42)\n(defun other () 7)'
        self.assertEqual(form(source, 'wanted'), source.split('\n(defun other')[0])

    def test_missing_duplicate_and_unterminated_fail(self):
        for source in ('(defun other () 1)', '(defun x () 1)\n(defun x () 2)', '(defun x ()'):
            with self.assertRaises(ValueError): form(source, 'x')
