"""Execute the named Python example actually exported in Chapter 15."""
from pathlib import Path
import re
import unittest

MANUSCRIPT = Path(__file__).resolve().parents[2] / 'manuscript/search-15.org'
BLOCK = re.compile(
    r'^\\#\\+name: search15-evidence-detachment-example\\s*\\n'
    r'^\\#\\+begin_src python\\s*\\n(.*?)^\\#\\+end_src\\s*$',
    re.MULTILINE | re.DOTALL,
)


class ManuscriptDetachmentExampleTests(unittest.TestCase):
    def test_exported_example_runs_against_real_client(self):
        sections = BLOCK.findall(MANUSCRIPT.read_text())
        self.assertEqual(len(sections), 1, 'expected exactly one named example')
        exec(compile(sections[0], str(MANUSCRIPT), 'exec'), {})


if __name__ == '__main__':
    unittest.main()
