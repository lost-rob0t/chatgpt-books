"""Root Org ID must belong to Chapter 15, not an unrelated later subtree."""
import unittest
from check_search_outline import CHAPTER_ID, inspect

ROOT = f'''* Chapter 15 -- Document Search
:PROPERTIES:
:ID:       {CHAPTER_ID}
:END:

** Search scopes
Public datasets remain server-owned; authenticated scope is caller-bound.
*** Exercise -- Name the evidence boundary
'''


class RootIdBindingTests(unittest.TestCase):
    def test_canonical_root_drawer_is_accepted(self):
        self.assertEqual(inspect(ROOT), [])

    def test_id_moved_to_section_does_not_attest_root(self):
        changed = ROOT.replace(f':PROPERTIES:\n:ID:       {CHAPTER_ID}\n:END:\n', '')
        changed = changed.replace('** Search scopes\n',
                                  f'** Search scopes\n:PROPERTIES:\n:ID: {CHAPTER_ID}\n:END:\n')
        self.assertIn('Chapter 15 root must own its stable Org ID',
                      ' '.join(inspect(changed)))

    def test_id_in_regular_prose_does_not_attest_root(self):
        changed = ROOT.replace(f':PROPERTIES:\n:ID:       {CHAPTER_ID}\n:END:\n',
                               f'Here is an unrelated example:\n:ID: {CHAPTER_ID}\n')
        self.assertIn('Chapter 15 root must own its stable Org ID',
                      ' '.join(inspect(changed)))

    def test_id_outside_property_drawer_does_not_attest_root(self):
        changed = ROOT.replace(':PROPERTIES:\n', ':MISTYPED_PROPERTIES:\n')
        self.assertIn('Chapter 15 root must own its stable Org ID',
                      ' '.join(inspect(changed)))

    def test_other_properties_in_root_drawer_are_permitted(self):
        changed = ROOT.replace(f':ID:       {CHAPTER_ID}\n',
                               f':EXPORT_FILE_NAME: search-15\n:ID: {CHAPTER_ID}\n')
        self.assertEqual(inspect(changed), [])

    def test_id_in_source_block_does_not_count(self):
        changed = ROOT.replace(f':PROPERTIES:\n:ID:       {CHAPTER_ID}\n:END:\n',
                               f'#+begin_src text\n:PROPERTIES:\n:ID: {CHAPTER_ID}\n:END:\n#+end_src\n')
        self.assertIn('Chapter 15 root must own its stable Org ID',
                      ' '.join(inspect(changed)))

    def test_missing_drawer_terminator(self):
        broken = ROOT.replace(':END:\n', '')
        self.assertIn('Chapter 15 root must own its stable Org ID',
                      ' '.join(inspect(broken)))

    def test_other_org_id_cannot_substitute(self):
        broken = ROOT.replace(f':ID:       {CHAPTER_ID}',
                              ':ID: unrelated-chapter-id')
        self.assertIn('Chapter 15 root must own its stable Org ID',
                      ' '.join(inspect(broken)))

    def test_second_root_rejected(self):
        self.assertIn('exactly one Chapter 15',
                      ' '.join(inspect(ROOT + '\n* Other book\n')))

    def test_duplicate_root_id_rejected(self):
        broken = ROOT.replace(f':ID:       {CHAPTER_ID}\n',
                              f':ID:       {CHAPTER_ID}\n:ID: {CHAPTER_ID}\n')
        self.assertIn('one stable Chapter 15 Org ID', ' '.join(inspect(broken)))


if __name__ == '__main__':
    unittest.main()
