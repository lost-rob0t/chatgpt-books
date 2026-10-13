"""Check actual Pandoc EPUB image alternatives and captions for Chapter 15."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from zipfile import ZipFile
from xml.etree import ElementTree

BOOK = Path(__file__).resolve().parents[2]
MANUSCRIPT = BOOK / 'manuscript/search-15.org'
IMAGES = (
    ('assets/search-boundaries.svg',
     'Public search uses server-owned datasets and wildcard tenancy; authenticated search uses caller scopes; both compile backend constraints before returning scrubbed hits.',
     'Public and authenticated search establish different scopes before calling the same CouchDB full-text index.'),
    ('assets/search-visibility.svg',
     'An accepted record must reach durable storage, selected index fields and analyzer state before an authorized query can return it; omitted fields or scope exclusions can produce no hit.',
     'HTTP acceptance, durable read-back, index projection and authorized hits are separate observations.'),
)
NAMESPACE = '{http://www.w3.org/1999/xhtml}'


def source_figure(lines, asset):
    matches = [i for i, line in enumerate(lines) if asset in line]
    if len(matches) != 1:
        raise AssertionError(f'expected one Chapter 15 reference to {asset}, found {len(matches)}')
    index = matches[0]
    if '<img ' in lines[index]:
        before = index
        while before >= 0 and lines[before].strip() != '#+begin_export html':
            before -= 1
        after = index
        while after < len(lines) and lines[after].strip() != '#+end_export':
            after += 1
        if before < 0 or after >= len(lines):
            raise AssertionError(f'HTML-export image missing block delimiters: {asset}')
        return '\n'.join(lines[before:after + 1])
    if (not lines[index].startswith('[[file:') or index < 2
            or not lines[index - 2].startswith('#+caption:')):
        raise AssertionError(f'unrecognized Org image block: {asset}')
    return '\n'.join(lines[index - 2:index + 1])


class SearchFigureAccessibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lines = MANUSCRIPT.read_text().splitlines()
        snippets = [source_figure(lines, asset) for asset, _, _ in IMAGES]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'figures.org'
            target = root / 'figures.epub'
            source.write_text('#+title: Chapter 15 diagrams\n\n' + '\n\n'.join(snippets) + '\n')
            subprocess.run(['pandoc', '-f', 'org', '-t', 'epub3',
                            '--resource-path', str(BOOK), str(source),
                            '-o', str(target)], check=True, capture_output=True, text=True)
            with ZipFile(target) as package:
                docs = [package.read(path) for path in package.namelist()
                        if path.endswith('.xhtml')]
        cls.figures = []
        for document in docs:
            root = ElementTree.fromstring(document)
            cls.figures.extend(root.findall('.//' + NAMESPACE + 'figure'))

    def test_both_diagrams_survive_epub_export(self):
        self.assertEqual(len(self.figures), len(IMAGES))
        for figure in self.figures:
            self.assertIsNotNone(figure.find(NAMESPACE + 'img'))

    def test_diagram_descriptions_are_on_images(self):
        for figure, (_, expected, _) in zip(self.figures, IMAGES):
            with self.subTest(expected=expected[:24]):
                image = figure.find(NAMESPACE + 'img')
                self.assertEqual(image.get('alt'), expected)

    def test_figcaption_survives_export(self):
        for figure, (_, _, expected) in zip(self.figures, IMAGES):
            with self.subTest(expected=expected[:24]):
                caption = figure.find(NAMESPACE + 'figcaption')
                self.assertIsNotNone(caption)
                self.assertEqual(''.join(caption.itertext()).strip(), expected)
