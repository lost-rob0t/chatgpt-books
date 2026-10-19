"""Guard the published Chapter 15 Lisp check inventory against prose drift."""
from pathlib import Path
import re
import unittest

HERE = Path(__file__).resolve().parent
BOOK = HERE.parents[1]


class HermeticInventoryTests(unittest.TestCase):
    def test_native_scenario_inventory(self):
        source = (HERE / 'hermetic.lisp').read_text(encoding='utf-8')
        labels = re.findall(r'^\(check\s+"([^"\n]+)"', source, flags=re.MULTILINE)
        self.assertEqual(len(labels), 16)
        self.assertEqual(len(labels), len(set(labels)), 'scenario labels must be unique')
        self.assertIn('Unicode public cap measures characters rather than UTF-8 octets', labels)

    def test_reader_facing_inventory_is_current(self):
        lab = (HERE / 'README.org').read_text(encoding='utf-8')
        chapter = (BOOK / 'manuscript/search-15.org').read_text(encoding='utf-8')
        self.assertIn('16 hermetic Lisp scenario checks', lab)
        self.assertIn('sixteen Lisp scenario checks', chapter)


if __name__ == '__main__':
    unittest.main()
