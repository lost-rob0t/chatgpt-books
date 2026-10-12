"""Chapter 15: the hit's revision is evidence only when it has a revision shape."""
import unittest
from lab import interpret_page


class RevisionEvidenceTests(unittest.TestCase):
    @staticmethod
    def page(doc):
        return {'bookmark': 'opaque', 'rows': [{
            'id': 'org:synthetic', 'fields': {'name': 'Demo'},
            'doc': {'_id': 'org:synthetic', **doc},
        }]}

    def test_storage_revision_is_retained(self):
        hits, _ = interpret_page(self.page({'_rev': '1-demo'}))
        self.assertEqual(hits[0].revision, '1-demo')

    def test_canonical_revision_is_retained(self):
        hits, _ = interpret_page(self.page({'rev': 'canonical-v2'}))
        self.assertEqual(hits[0].revision, 'canonical-v2')

    def test_absent_revision_is_explicitly_unknown(self):
        hits, _ = interpret_page(self.page({}))
        self.assertIsNone(hits[0].revision)

    def test_nonstrings_do_not_masquerade_as_revisions(self):
        for rev in (42, False, ['1', '2']):
            with self.subTest(value=rev):
                with self.assertRaisesRegex(ValueError, 'invalid revision'):
                    interpret_page(self.page({'_rev': rev}))

    def test_invalid_canonical_revision_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'invalid revision'):
            interpret_page(self.page({'rev': ['v1', 'v2']}))


if __name__ == '__main__':
    unittest.main()
