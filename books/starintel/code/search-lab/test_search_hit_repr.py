"""Safe default diagnostic rendering of untrusted interpreted search hits."""
from dataclasses import FrozenInstanceError, asdict
import unittest

from lab import Hit


class SearchHitReprTests(unittest.TestCase):
    def setUp(self):
        self.hit = Hit(
            identity='fictional-private-id', revision='private-revision',
            dtype='person', dataset='fictional-private-dataset',
            document={'note': 'fictional-sensitive-document', 'session': 'redacted'},
            fields={'name': 'fictional-untrusted-name', 'token': 'fictional-token'},
            storage_revision='fictional-storage-revision',
            canonical_revision='fictional-canonical-revision',
        )

    def test_default_repr_is_inert_and_constant(self):
        self.assertEqual(repr(self.hit), 'Hit(<search evidence redacted>)')

    def test_list_repr_cannot_print_row_or_embedded_document(self):
        rendered = repr([self.hit])
        self.assertEqual(rendered, '[Hit(<search evidence redacted>)]')
        for secret in ('fictional-sensitive-document', 'fictional-token',
                       'fictional-private-id', 'fictional-private-dataset'):
            self.assertNotIn(secret, rendered)

    def test_str_is_also_inert(self):
        self.assertEqual(str(self.hit), repr(self.hit))

    def test_repr_does_not_expose_revisions_or_type(self):
        rendered = repr(self.hit)
        for text in ('private-revision', 'fictional-storage-revision',
                     'fictional-canonical-revision', 'person'):
            self.assertNotIn(text, rendered)

    def test_repr_does_not_touch_untrusted_nested_objects(self):
        class MaliciousRepr:
            def __repr__(self):
                raise AssertionError('untrusted repr evaluated')
        hit = Hit('id', None, None, None, {'value': MaliciousRepr()}, {})
        self.assertEqual(repr(hit), 'Hit(<search evidence redacted>)')

    def test_retrieval_and_equality_contracts_are_unchanged(self):
        self.assertEqual(self.hit.identity, 'fictional-private-id')
        self.assertEqual(self.hit.document['note'], 'fictional-sensitive-document')
        self.assertEqual(self.hit.fields['name'], 'fictional-untrusted-name')
        self.assertEqual(self.hit, Hit(**asdict(self.hit)))

    def test_frozen_dataclass_unchanged(self):
        with self.assertRaises(FrozenInstanceError):
            self.hit.identity = 'different'

    def test_explicit_asdict_is_not_claimed_redacted(self):
        self.assertEqual(asdict(self.hit)['document']['note'],
                         'fictional-sensitive-document')


if __name__ == '__main__':
    unittest.main()
