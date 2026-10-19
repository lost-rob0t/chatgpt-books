"""Native regression for stable Chapter 15 reader-map links and Org export."""
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import tempfile
import unittest

from check_search_navigation import LANDMARKS, MAP_HEADING, inspect, main


def chapter(links=True, anchors=True):
    text = ('* Chapter 15 -- Source-grounded search\n'
            ':PROPERTIES:\n:ID: c28dc507-faf2-4e26-b1ba-bc2b8236e7af\n:END:\n'
            '** ' + MAP_HEADING + '\n'
            'Choose a boundary; none of these anchors certifies durable evidence.\n')
    if links:
        text += ''.join(f'- [[#{ident}][{heading}]]\n' for ident, heading in LANDMARKS)
    for ident, heading in LANDMARKS:
        text += '** ' + heading + '\n'
        if anchors:
            text += ':PROPERTIES:\n:CUSTOM_ID: ' + ident + '\n:END:\n'
        text += 'A bounded, fictional search observation.\n'
    return text


class _Fragments(HTMLParser):
    def __init__(self):
        super().__init__()
        self.anchors = set()
        self.references = []

    def handle_starttag(self, tag, attrs):
        info = dict(attrs)
        if 'id' in info:
            self.anchors.add(info['id'])
        if tag == 'a' and info.get('href', '').startswith('#'):
            self.references.append(info['href'][1:])


class SearchNavigationTests(unittest.TestCase):
    def test_valid_map_and_landmarks(self):
        self.assertEqual(inspect(chapter()), [])

    def test_missing_reader_map_is_rejected(self):
        missing = chapter().replace('** ' + MAP_HEADING, '** A different heading')
        self.assertIn('missing reader map', ' '.join(inspect(missing)))

    def test_missing_anchor_is_rejected(self):
        self.assertIn('landmark', ' '.join(inspect(chapter(anchors=False))))

    def test_wrong_owner_is_rejected(self):
        sample = chapter().replace('** Evidence and version map', '** Wrong section')
        self.assertIn('must belong to', ' '.join(inspect(sample)))

    def test_duplicated_anchor_is_rejected(self):
        sample = chapter() + ':PROPERTIES:\n:CUSTOM_ID: search15-scope\n:END:\n'
        self.assertIn('duplicate CUSTOM_ID', ' '.join(inspect(sample)))

    def test_extra_or_dangling_link_is_rejected(self):
        sample = chapter().replace('[[#search15-scope]', '[[#search15-unknown]')
        self.assertIn('unregistered fragment', ' '.join(inspect(sample)))

    def test_one_missing_map_link_is_rejected(self):
        sample = chapter().replace('[[#search15-scope][Choose the search surface deliberately]]', 'Scope is not linked')
        self.assertIn('exactly one link to search15-scope', ' '.join(inspect(sample)))

    def test_links_inside_source_blocks_do_not_satisfy_map(self):
        original = chapter().replace('[[#search15-version][Evidence and version map]]', 'This link is missing')
        fake = '#+begin_src text\n[[#search15-version][Evidence and version map]]\n#+end_src\n'
        sample = original.replace('** ' + MAP_HEADING + '\n', '** ' + MAP_HEADING + '\n' + fake)
        self.assertIn('exactly one link to search15-version', ' '.join(inspect(sample)))

    def test_markup_inside_example_is_not_an_anchor(self):
        sample = chapter() + '#+begin_src org\n** Bogus\n:CUSTOM_ID: search15-debug\n#+end_src\n'
        self.assertEqual(inspect(sample), [])

    def test_cli_success_and_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'chapter.org'
            source.write_text(chapter())
            self.assertEqual(main([str(source)]), 0)
            source.write_text(chapter(anchors=False))
            self.assertEqual(main([str(source)]), 1)
            self.assertEqual(main([str(source), str(source)]), 2)

    def test_pandoc_links_reach_exported_landmarks(self):
        result = subprocess.run(['pandoc', '-f', 'org', '-t', 'html5'],
                                input=chapter(), text=True, capture_output=True,
                                check=True)
        parser = _Fragments()
        parser.feed(result.stdout)
        expected = {ident for ident, _ in LANDMARKS}
        self.assertEqual(set(parser.references), expected)
        self.assertTrue(expected <= parser.anchors)


if __name__ == '__main__':
    unittest.main()
