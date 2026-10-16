"""Fail-closed checks for figure-level DOT defaults in Chapter 15."""
from pathlib import Path
import unittest

from test_search_diagram_semantics import parse_dot, verify_figure

ASSETS = Path(__file__).resolve().parents[2] / 'assets'


def pair():
    return ((ASSETS / 'search-boundaries.dot').read_text(),
            (ASSETS / 'search-boundaries.svg').read_text())


class DotDefaultsTests(unittest.TestCase):
    def test_graph_label_cannot_be_injected_while_reusing_old_svg(self):
        dot, svg = pair()
        tampered = dot.replace('graph [rankdir=TB, bgcolor="white"];',
                               'graph [rankdir=TB, bgcolor="white", label="False proof"];')
        self.assertNotEqual(dot, tampered)
        with self.assertRaisesRegex(ValueError, 'defaults'):
            verify_figure(tampered, svg)

    def test_graph_background_change_must_be_detected(self):
        dot, svg = pair()
        with self.assertRaisesRegex(ValueError, 'defaults'):
            verify_figure(dot.replace('bgcolor="white"', 'bgcolor="black"'), svg)

    def test_node_typography_change_must_be_detected(self):
        dot, svg = pair()
        with self.assertRaisesRegex(ValueError, 'defaults'):
            verify_figure(dot.replace('fontsize=11', 'fontsize=30'), svg)

    def test_second_graph_directive_is_rejected(self):
        dot, _ = pair()
        dup = dot.replace('graph [rankdir=TB, bgcolor="white"];',
                          'graph [rankdir=TB, bgcolor="white"];\n  graph [rankdir=TB, bgcolor="white"];')
        with self.assertRaisesRegex(ValueError, 'defaults'):
            parse_dot(dup)

    def test_missing_node_directive_is_rejected(self):
        dot, _ = pair()
        removed = dot.replace('  node [shape=box, fontname="DejaVu Sans", fontsize=11];\n', '')
        self.assertNotEqual(dot, removed)
        with self.assertRaisesRegex(ValueError, 'defaults'):
            parse_dot(removed)


if __name__ == '__main__':
    unittest.main()
