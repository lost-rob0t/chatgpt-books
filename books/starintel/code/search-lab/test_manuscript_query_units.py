"""Execute the exported Chapter 15 example distinguishing query character and byte limits."""
from pathlib import Path
import re
import unittest

MANUSCRIPT = Path(__file__).resolve().parents[2] / 'manuscript/search-15.org'
BLOCK = re.compile(
    r'^\#\+name: search15-public-query-length-units\s*\n'
    r'^\#\+begin_src python\s*\n(.*?)^\#\+end_src\s*$',
    re.MULTILINE | re.DOTALL,
)


class QueryLengthUnitExampleTests(unittest.TestCase):
    def test_manuscript_character_and_byte_example_runs(self):
        blocks = BLOCK.findall(MANUSCRIPT.read_text())
        self.assertEqual(len(blocks), 1, 'expected one named exported query-unit example')
        exec(compile(blocks[0], str(MANUSCRIPT), 'exec'), {})


if __name__ == '__main__':
    unittest.main()
