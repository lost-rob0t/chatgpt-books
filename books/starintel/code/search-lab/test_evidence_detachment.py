"""Search result evidence must not alias a subsequently edited response."""
import unittest
from lab import interpret_page


def page():
    return {'rows': [{'id': 'starintel:org:synthetic',
                      'fields': {'dtype': 'org', 'dataset': 'demo',
                                 'names': ['indexed'], 'audit': {'rank': 1}},
                      'doc': {'_id': 'starintel:org:synthetic', 'dtype': 'org',
                              'dataset': 'demo', 'rev': 'orig',
                              'provenance': {'paths': ['initial']}}}],
            'bookmark': 'opaque'}


class EvidenceDetachmentTests(unittest.TestCase):
    def test_source_document_changes_do_not_rewrite_hit(self):
        response = page()
        hit = interpret_page(response)[0][0]
        response['rows'][0]['doc']['rev'] = 'changed'
        self.assertEqual(hit.document['rev'], 'orig')
        self.assertEqual(hit.canonical_revision, 'orig')

    def test_nested_provenance_is_detached(self):
        response = page()
        hit = interpret_page(response)[0][0]
        response['rows'][0]['doc']['provenance']['paths'][0] = 'changed'
        self.assertEqual(hit.document['provenance']['paths'], ['initial'])

    def test_stored_fields_are_detached_recursively(self):
        response = page()
        hit = interpret_page(response)[0][0]
        response['rows'][0]['fields']['audit']['rank'] = 999
        response['rows'][0]['fields']['names'].append('changed')
        self.assertEqual(hit.fields['audit']['rank'], 1)
        self.assertEqual(hit.fields['names'], ['indexed'])

    def test_second_interpretation_does_not_mutate_first_hit(self):
        response = page()
        first = interpret_page(response)[0][0]
        response['rows'][0]['doc']['provenance']['paths'].append('later')
        second = interpret_page(response)[0][0]
        self.assertEqual(first.document['provenance']['paths'], ['initial'])
        self.assertEqual(second.document['provenance']['paths'], ['initial', 'later'])

    def test_fields_only_stays_fields_only(self):
        response = page()
        response['rows'][0].pop('doc')
        hit = interpret_page(response)[0][0]
        self.assertIsNone(hit.document)
        self.assertEqual(hit.fields['names'], ['indexed'])

    def test_invalid_scope_field_still_fails_closed(self):
        response = page()
        response['rows'][0]['fields']['dataset'] = 'wrong'
        with self.assertRaises(ValueError):
            interpret_page(response)


if __name__ == '__main__':
    unittest.main()
