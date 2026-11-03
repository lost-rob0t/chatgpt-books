"""Chapter 15 cross-boundary proof: a *server-stamped* fixture reaches FTS.

The original upstream Lisp functions are inspected at the pinned checkout;
the Python staging function below is a disclosed model, NOT Lisp execution.
The FTS field emissions are from the original pinned JavaScript index callback.
"""
import copy
import hashlib
import os
from pathlib import Path
import unittest

from extract_forms import form
from lab import projection
from service_checks import fixture, fixture_dataset

SERVER = Path(os.environ['STAR_SEARCH_LAB_SERVER'])
INDEX_BLOB = '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a'
RESOLVER_SHA256 = 'f8c753ad9b2605c2d132d8abf8179c5b0ea27a807e634e57f6cc7c509119dca0'
STAMP_SHA256 = '58601f38d5883b3d470faa1bdc27525f4c817f56484bd5d648cd57870be03980'
NEEDLE = 'bookneedletenantsynthetic'


def index_values(document, field):
    return [event['value'] for event in projection(SERVER, document)
            if event['field'] == field]


def model_stamped_for_index(document, dataset_map):
    """Source-grounded *model* of the pinned server's internal tenant stamp.

    This is intentionally not an implementation of server authorization.
    Clients must NOT submit tenant_id. The server injects that internal key.
    """
    result = copy.deepcopy(document)
    if 'tenant_id' not in result and 'tenant' not in result:
        result['tenant_id'] = dataset_map.get(result.get('dataset'), 'default')
    return result


class TenantStampedIndexTests(unittest.TestCase):
    def test_exact_historical_index_git_blob(self):
        data = (SERVER / 'source/views/search.json').read_bytes()
        digest = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        self.assertEqual(digest, INDEX_BLOB)

    def test_original_upstream_stamp_and_resolver_form_fingerprints(self):
        upstream = (SERVER / 'source/frontends/http-boundary-core.lisp').read_text()
        for name, expected in [('resolved-server-tenant', RESOLVER_SHA256),
                               ('stamp-server-tenant!', STAMP_SHA256)]:
            actual = hashlib.sha256(form(upstream, name).encode()).hexdigest()
            self.assertEqual(actual, expected, name + ' upstream contract drift')

    def test_pinned_bulk_ingress_stamps_before_publish(self):
        bulk = (SERVER / 'source/frontends/http-bulk-jobs.lisp').read_text()
        self.assertGreaterEqual(
            bulk.count(':body (jsown:to-json (stamp-server-tenant! document))'), 2,
            'both historical publish paths must use server tenant stamping')

    def test_client_seed_has_no_tenant_and_raw_index_falls_back(self):
        raw = fixture('starintel:person:tenant-control', fixture_dataset(4), NEEDLE)
        self.assertNotIn('tenant_id', raw)
        self.assertNotIn('tenant', raw)
        self.assertEqual(index_values(raw, 'tenant_id'), ['default'])
        self.assertEqual(index_values(raw, 'dataset'), ['book-other-public'])

    def test_stamped_other_tenant_changes_real_index_projection(self):
        raw = fixture('starintel:person:tenant-other', fixture_dataset(4), NEEDLE)
        internal = model_stamped_for_index(raw, {'book-other-public': 'other'})
        self.assertEqual(index_values(internal, 'tenant_id'), ['other'])
        self.assertEqual(index_values(internal, 'dataset'), ['book-other-public'])
        self.assertEqual(index_values(internal, 'fname'), [NEEDLE])
        self.assertNotIn('tenant_id', raw, 'internal stamping must not mutate client seed')

    def test_unmapped_public_and_private_fixtures_stay_default_tenant(self):
        for ordinal in (0, 1, 2, 3):
            with self.subTest(ordinal=ordinal):
                raw = fixture('starintel:person:tenant-' + str(ordinal),
                              fixture_dataset(ordinal), NEEDLE)
                internal = model_stamped_for_index(raw, {'book-other-public': 'other'})
                self.assertEqual(index_values(internal, 'tenant_id'), ['default'])
                self.assertEqual(index_values(internal, 'dataset'),
                                 [fixture_dataset(ordinal)])

    def test_stamping_preserves_existing_internal_tenant(self):
        raw = fixture('starintel:person:tenant-existing', fixture_dataset(4), NEEDLE)
        internal = dict(raw, tenant_id='explicit-internal')
        self.assertEqual(model_stamped_for_index(internal, {'book-other-public': 'other'}), internal)
        self.assertEqual(index_values(internal, 'tenant_id'), ['explicit-internal'])


if __name__ == '__main__':
    unittest.main()
