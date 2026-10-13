"""BK08 offline selector: HTML class tokens use ASCII HTML space only.

These tests distinguish genuine CSS class-token boundaries from Python's much
broader Unicode whitespace splitting. No browser, network or models needed.
"""
from __future__ import annotations

import unittest

from offline_html_trace_executor import BoundedParser, TraceFailure, select_one


class TestHTMLClassTokenWhitespace(unittest.TestCase):
    @staticmethod
    def document(html: str):
        parser = BoundedParser()
        parser.feed(html)
        parser.close()
        return parser.root

    def assert_zero(self, root, selector: str) -> None:
        with self.assertRaises(TraceFailure) as caught:
            select_one(root, selector)
        self.assertEqual(caught.exception.code, "selector_zero")

    def test_01_nbsp_is_not_a_class_token_boundary(self) -> None:
        root = self.document('<p id="only" class="alpha\u00a0beta">Text</p>')
        self.assert_zero(root, "p.beta")

    def test_02_other_non_ascii_spaces_are_not_boundaries(self) -> None:
        for char in ("\u1680", "\u2000", "\u2003", "\u2009", "\u202f", "\u205f", "\u3000"):
            with self.subTest(codepoint=f"U+{ord(char):04X}"):
                root = self.document(f'<p class="alpha{char}beta">Text</p>')
                self.assert_zero(root, ".beta")

    def test_03_vertical_tab_is_not_an_html_space(self) -> None:
        root = self.document('<p class="alpha\vbeta">Text</p>')
        self.assert_zero(root, ".beta")

    def test_04_html_entity_nbsp_is_not_an_ascii_space(self) -> None:
        root = self.document('<p class="alpha&#160;beta">Text</p>')
        self.assert_zero(root, ".beta")

    def test_05_css_whitespace_still_separates_classes(self) -> None:
        for char in (" ", "\t", "\n", "\r", "\f"):
            with self.subTest(ascii=repr(char)):
                root = self.document(f'<p id="yes" class="alpha{char}beta">Text</p>')
                self.assertEqual(select_one(root, ".beta").attrs["id"], "yes")

    def test_06_ascii_mixed_whitespace_and_compound_selector(self) -> None:
        root = self.document('<p id="yes" class="alpha \t\n\f\rbeta">Text</p>')
        self.assertEqual(select_one(root, "p.alpha.beta#yes").attrs["id"], "yes")

    def test_07_non_ascii_space_is_retained_inside_single_class(self) -> None:
        root = self.document('<p id="only" class="alpha\u00a0beta">Text</p>')
        selected = select_one(root, "#only")
        self.assertEqual(selected.attrs["class"], "alpha\u00a0beta")

    def test_08_non_ascii_space_must_not_create_false_ambiguity(self) -> None:
        root = self.document('<p id="decoy" class="alpha\u00a0beta">Other</p>'
                             '<p id="real" class="beta">Target</p>')
        self.assertEqual(select_one(root, ".beta").attrs["id"], "real")

    def test_09_tagged_compound_selector_is_not_unicode_split(self) -> None:
        root = self.document('<span class="alpha\u2003beta">Wrong</span>')
        self.assert_zero(root, "span.alpha.beta")

    def test_10_missing_class_still_returns_typed_zero(self) -> None:
        root = self.document('<p id="plain">Only ID</p>')
        self.assert_zero(root, "p.beta")


if __name__ == "__main__":
    unittest.main()
