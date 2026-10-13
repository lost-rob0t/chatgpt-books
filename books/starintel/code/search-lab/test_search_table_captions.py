"""Regression: Chapter 15 comparison tables carry real Pandoc table captions."""
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
MANUSCRIPT = HERE.parents[1] / 'manuscript' / 'search-15.org'
EXPECTED = [
    ('Boundary | Authority or implementation | What the lab establishes',
     'Evidence established at each pinned search boundary.'),
    ('Behavior at the inspected pin | Public search | Authenticated document search',
     'Public and authenticated search contract differences.'),
    ('Indexed field | Explicit analyzer',
     'Explicit analyzer choices in the historical search index.'),
    ('Canonical field or structure | Observation at this historical index pin | Engineering consequence',
     'Canonical schema fields versus historical index coverage.'),
    ('Mistake | Why it fails | Better next step',
     'Search-evidence mistakes and recommended diagnostic steps.'),
]


class Captions(HTMLParser):
    def __init__(self):
        super().__init__()
        self.captions = []
        self.in_caption = False

    def handle_starttag(self, tag, attrs):
        if tag == 'caption':
            self.captions.append('')
            self.in_caption = True

    def handle_endtag(self, tag):
        if tag == 'caption':
            self.in_caption = False

    def handle_data(self, data):
        if self.in_caption:
            self.captions[-1] += data


class SearchTableCaptionTests(unittest.TestCase):
    def test_each_of_five_tables_has_adjacent_org_caption(self):
        body = MANUSCRIPT.read_text(encoding='utf-8')
        for header, caption in EXPECTED:
            with self.subTest(table=header):
                row = '| ' + header + ' |'
                self.assertEqual(body.count(row), 1)
                self.assertIn('#+caption: ' + caption + '\n' + row, body)

    def test_pandoc_emits_semantic_html_captions(self):
        result = subprocess.run(['pandoc', '-f', 'org', '-t', 'html5'],
                                input=MANUSCRIPT.read_text(encoding='utf-8'),
                                text=True, capture_output=True, check=True)
        parser = Captions()
        parser.feed(result.stdout)
        self.assertEqual(parser.captions, [caption for _, caption in EXPECTED])


if __name__ == '__main__':
    unittest.main()
