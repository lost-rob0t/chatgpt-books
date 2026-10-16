"""Verify that exported Chapter 15 SVGs tell the same story as their DOT source.

This is a semantic drift check, not a pixel equality assertion. It avoids
Graphviz-layout/version sensitivity while rejecting altered topology or labels.
The deliberately narrow DOT grammar matches the two maintained chapter figures
and fails closed on unrecognized statement forms.
"""
from pathlib import Path
import json
import re
import unittest
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parents[1] / 'assets'
FIGURES = ('search-boundaries', 'search-visibility')
IDENT = r'[A-Za-z_][A-Za-z_0-9]*'
STRING = r'"((?:\\.|[^"\\])*)"'
DECL = re.compile(rf'^\s*({IDENT})\s+\[label={STRING}\];\s*$')
EDGE = re.compile(rf'^\s*({IDENT}(?:\s*->\s*{IDENT})+)\s*(?:\[label={STRING}\])?;\s*$')
HEADER = re.compile(rf'^digraph\s+({IDENT})\s*\{{$')
# These are the complete figure-level defaults in both authored Chapter 15
# DOT sources.  Previously any graph/node defaults were silently ignored, so
# an inserted Graphviz label or a changed visual default could pass against
# the old SVG. Make style changes explicit and force a new rendered artifact.
DEFAULTS = frozenset({
    'graph [rankdir=TB, bgcolor="white"];',
    'node [shape=box, fontname="DejaVu Sans", fontsize=11];',
})


def parse_dot(raw: str) -> tuple[str, dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    """Parse the two authored figures; do not guess semantics for novel DOT."""
    statements = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(statements) < 5 or not (match := HEADER.fullmatch(statements[0])) or statements[-1] != '}':
        raise ValueError('expected one complete directed Chapter 15 graph')
    graph_name = match.group(1)
    nodes: dict[str, tuple[str, ...]] = {}
    edges: dict[str, tuple[str, ...]] = {}
    seen_defaults: set[str] = set()
    for stmt in statements[1:-1]:
        if stmt.startswith('graph [') or stmt.startswith('node ['):
            if stmt not in DEFAULTS or stmt in seen_defaults:
                raise ValueError('unsupported or duplicate DOT graph/node defaults')
            seen_defaults.add(stmt)
            continue
        if match := DECL.fullmatch(stmt):
            node, label = match.groups()
            if node in nodes:
                raise ValueError('duplicate DOT node declaration')
            nodes[node] = tuple(json.loads('"' + label + '"').split('\n'))
            continue
        if match := EDGE.fullmatch(stmt):
            chain, label = match.groups()
            parts = re.split(r'\s*->\s*', chain)
            for start, finish in zip(parts, parts[1:]):
                key = f'{start}->{finish}'
                if key in edges:
                    raise ValueError('duplicate DOT edge')
                edges[key] = () if label is None else tuple(json.loads('"' + label + '"').split('\n'))
            continue
        raise ValueError(f'unsupported DOT statement: {stmt[:100]}')
    if seen_defaults != DEFAULTS:
        raise ValueError('missing required DOT graph/node defaults')
    if not nodes or not edges or any(part not in nodes for key in edges for part in key.split('->')):
        raise ValueError('DOT graph contains an undeclared endpoint or has no graph content')
    return graph_name, nodes, edges


def parse_svg(raw: str) -> tuple[str, dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    try:
        doc = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ValueError('SVG is not parseable XML') from error
    ns = '{http://www.w3.org/2000/svg}'
    if doc.tag != ns + 'svg':
        raise ValueError('not an SVG root element')
    graphs = [g for g in doc.iter(ns + 'g') if g.get('class') == 'graph']
    if len(graphs) != 1:
        raise ValueError('expected exactly one rendered graph')
    graph_title = graphs[0].find(ns + 'title')
    if graph_title is None or not graph_title.text:
        raise ValueError('rendered graph lacks its title')
    nodes: dict[str, tuple[str, ...]] = {}
    edges: dict[str, tuple[str, ...]] = {}
    for g in graphs[0].iter(ns + 'g'):
        kind = g.get('class')
        if kind not in ('node', 'edge'):
            continue
        title = g.find(ns + 'title')
        if title is None or not title.text:
            raise ValueError('rendered graph element has no identity')
        text = tuple(''.join(t.itertext()) for t in g.findall(ns + 'text'))
        collection = nodes if kind == 'node' else edges
        if title.text in collection:
            raise ValueError('duplicate rendered graph element')
        collection[title.text] = text
    return graph_title.text, nodes, edges


def verify_figure(dot_text: str, svg_text: str) -> None:
    source = parse_dot(dot_text)
    rendered = parse_svg(svg_text)
    if source != rendered:
        name_a, nodes_a, edges_a = source
        name_b, nodes_b, edges_b = rendered
        if name_a != name_b:
            raise ValueError('rendered graph identity differs from source')
        for kind, a, b in (('node', nodes_a, nodes_b), ('edge', edges_a, edges_b)):
            if a != b:
                raise ValueError(f'rendered {kind} IDs/labels/topology differ from DOT source')
        raise ValueError('rendered graph differs from DOT source')


class SearchDiagramSemanticsTests(unittest.TestCase):
    def figure(self, name: str) -> tuple[str, str]:
        return ((ASSETS / f'{name}.dot').read_text(encoding='utf-8'),
                (ASSETS / f'{name}.svg').read_text(encoding='utf-8'))

    def test_both_rendered_figures_match_authored_semantics(self):
        for name in FIGURES:
            with self.subTest(name=name):
                verify_figure(*self.figure(name))

    def test_changed_public_limit_is_detected(self):
        dot, svg = self.figure('search-boundaries')
        self.assertIn('limit 1..50', dot)
        with self.assertRaisesRegex(ValueError, 'labels'):
            verify_figure(dot.replace('limit 1..50', 'limit 1..500'), svg)

    def test_changed_authorization_edge_is_detected(self):
        dot, svg = self.figure('search-boundaries')
        self.assertIn('private -> caller -> compile;', dot)
        with self.assertRaisesRegex(ValueError, 'topology'):
            verify_figure(dot.replace('private -> caller -> compile;', 'private -> compile;'), svg)

    def test_changed_visibility_consequence_is_detected(self):
        dot, svg = self.figure('search-visibility')
        self.assertIn('Does not establish no stored record', dot)
        with self.assertRaisesRegex(ValueError, 'labels'):
            verify_figure(dot.replace('Does not establish no stored record', 'Proves deleted'), svg)

    def test_missing_svg_edge_is_detected(self):
        dot, svg = self.figure('search-visibility')
        body = re.sub(r'<g id="edge\d+" class="edge">[\s\S]*?</g>', '', svg, count=1)
        self.assertNotEqual(body, svg)
        with self.assertRaisesRegex(ValueError, 'topology'):
            verify_figure(dot, body)

    def test_duplicate_svg_node_is_detected(self):
        dot, svg = self.figure('search-boundaries')
        node = re.search(r'<g id="node\d+" class="node">[\s\S]*?</g>', svg)
        self.assertIsNotNone(node)
        with self.assertRaisesRegex(ValueError, 'duplicate rendered graph element'):
            verify_figure(dot, svg.replace(node.group(0), node.group(0) * 2, 1))

    def test_svg_xml_truncation_is_detected(self):
        dot, svg = self.figure('search-boundaries')
        with self.assertRaisesRegex(ValueError, 'parseable XML'):
            verify_figure(dot, svg[:len(svg) // 2])

    def test_new_unparsed_dot_syntax_fails_closed(self):
        dot, svg = self.figure('search-boundaries')
        with self.assertRaisesRegex(ValueError, 'unsupported DOT statement'):
            verify_figure(dot.replace('}', 'subgraph cluster_0 {}\n}'), svg)


if __name__ == '__main__':
    unittest.main()
