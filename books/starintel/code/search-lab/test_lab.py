from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
import starintel_canonical as sdk
from lab import interpret_page, next_bookmark, projection, request_path

HERE = Path(__file__).parent
SERVER = Path(os.environ['STAR_SEARCH_LAB_SERVER'])


class IndexTests(unittest.TestCase):
    def emit(self, value):
        return {e['field']: e['value'] for e in projection(SERVER, value)}

    def test_canonical_fixtures_are_sdk_valid(self):
        for path in (HERE / 'fixtures').glob('*.json'):
            sdk.validate_document(json.loads(path.read_text()))

    def test_canonical_org_name_is_indexed(self):
        org = json.loads((HERE / 'fixtures/org.json').read_text())
        self.assertEqual(self.emit(org)['name'], org['name'])

    def test_canonical_person_camelcase_is_not_old_index_field(self):
        person = json.loads((HERE / 'fixtures/person.json').read_text())
        emitted = self.emit(person)
        person['fullName'] = 'Alex Example'
        sdk.validate_document(person)
        emitted = self.emit(person)
        self.assertEqual(emitted['fname'], 'Alex')
        self.assertNotIn('fullName', emitted)
        self.assertNotIn('full_name', emitted)

    def test_nested_data_takes_precedence(self):
        self.assertEqual(self.emit({'name': 'outer', 'data': {'name': 'inner'}})['name'], 'inner')

    def test_null_nested_value_does_not_fall_back(self):
        self.assertNotIn('name', self.emit({'name': 'outer', 'data': {'name': None}}))

    def test_arrays_emit_each_scalar_preserving_false_zero(self):
        values = projection(SERVER, {'data': {'content': [0, False, 'needle', None, {}]}})
        self.assertEqual([e['value'] for e in values if e['field'] == 'content'], [0, False, 'needle'])

    def test_unlisted_field_is_not_searchable(self):
        self.assertNotIn('customSecret', self.emit({'customSecret': 'needle'}))

    def test_tenant_fallback_and_precedence(self):
        self.assertEqual(self.emit({})['tenant_id'], 'default')
        self.assertEqual(self.emit({'tenant': 'old', 'tenant_id': 'new'})['tenant_id'], 'new')

    def test_sources_have_explicit_projection(self):
        emissions = projection(SERVER, {'sources': [{'url': 'https://example.invalid', 'unknown': 'ignored'}]})
        self.assertEqual([e['value'] for e in emissions if e['field'] == 'sources'], ['https://example.invalid'])

    def test_no_default_field_emitted(self):
        self.assertNotIn('default', self.emit({'content': 'needle', 'name': 'needle'}))


class InterpretationTests(unittest.TestCase):
    def page(self):
        return {'total_rows': 99, 'bookmark': 'opaque+/=', 'rows': [
            {'id': 'org:book-example', 'order': [1.4, 'org:book-example'],
             'fields': {'name': 'Example Cooperative'},
             'doc': {'_id': 'org:book-example', '_rev': '1-demo', 'dtype': 'org', 'dataset': 'book-synthetic'}}]}

    def test_hit_identity_revision_and_evidence(self):
        hits, bookmark = interpret_page(self.page())
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].revision, '1-demo')
        self.assertEqual(bookmark, 'opaque+/=')
        self.assertEqual(hits[0].dataset, 'book-synthetic')

    def test_fields_only_is_not_full_document(self):
        page = self.page(); del page['rows'][0]['doc']
        self.assertIsNone(interpret_page(page)[0][0].document)

    def test_error_envelope_is_not_empty_success(self):
        with self.assertRaises(ValueError): interpret_page({'status': 'error', 'code': 'access_denied'})

    def test_identity_disagreement_rejected(self):
        page = self.page(); page['rows'][0]['doc']['_id'] = 'org:other'
        with self.assertRaises(ValueError): interpret_page(page)

    def test_duplicate_identity_rejected(self):
        page = self.page(); page['rows'].append(deepcopy(page['rows'][0]))
        with self.assertRaises(ValueError): interpret_page(page)

    def test_tenant_leak_rejected_in_either_projection(self):
        for field in ('fields', 'doc'):
            page = self.page(); page['rows'][0][field]['tenant_id'] = 'private'
            with self.assertRaises(ValueError): interpret_page(page)

    def test_bookmark_type_rejected(self):
        page = self.page(); page['bookmark'] = 42
        with self.assertRaises(ValueError): interpret_page(page)

    def test_empty_page_ends_even_with_bookmark(self):
        self.assertIsNone(next_bookmark('old', 'new', []))

    def test_repeated_bookmark_with_hits_is_failure(self):
        hits, bookmark = interpret_page(self.page())
        with self.assertRaises(ValueError): next_bookmark(bookmark, bookmark, hits)

    def test_query_and_bookmark_are_urlencoded(self):
        path = request_path('authenticated', 'name:"A&B"', bookmark='opaque+/=')
        self.assertIn('q=name%3A%22A%26B%22', path)
        self.assertIn('bookmark=opaque%2B%2F%3D', path)

    def test_surface_typo_fails_closed(self):
        with self.assertRaises(ValueError): request_path('private?', 'name:needle')
