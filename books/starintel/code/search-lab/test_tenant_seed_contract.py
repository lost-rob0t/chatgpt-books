"""Hermetic contract for server-owned tenant adaptation of synthetic seeds."""
import unittest
from service_checks import fixture, fixture_dataset

# Required test-stack settings: STAR_TENANT_DATASET_MAP=book-other-public=other
# and STAR_PUBLIC_SEARCH_DATASETS=book-public,book-other-public.
# This model is not StarIntel's authorization compiler.
TENANT_DATASET_MAP = {'book-other-public': 'other'}
PUBLIC_DATASETS = {'book-public', 'book-other-public'}
READER_DATASETS = {'book-public'}


class TenantFixtureContractTests(unittest.TestCase):
    def test_all_five_datasets_have_distinct_scope_roles(self):
        self.assertEqual([fixture_dataset(i) for i in range(5)],
                         ['book-public'] * 3 + ['book-private', 'book-other-public'])

    def test_derived_tenants_distinguish_other_writer(self):
        adapted = [TENANT_DATASET_MAP.get(fixture_dataset(i), 'default') for i in range(5)]
        self.assertEqual(adapted, ['default'] * 4 + ['other'])

    def test_public_and_restricted_identity_sets_are_distinct(self):
        public_ids = {i for i in range(5) if fixture_dataset(i) in PUBLIC_DATASETS}
        private_ids = {i for i in range(5) if fixture_dataset(i) in READER_DATASETS
                       and TENANT_DATASET_MAP.get(fixture_dataset(i), 'default') == 'default'}
        self.assertEqual(public_ids, {0, 1, 2, 4})
        self.assertEqual(private_ids, {0, 1, 2})

    def test_legacy_fixture_does_not_accept_client_tenancy(self):
        for ordinal in range(5):
            doc = fixture('starintel:person:book-test-' + str(ordinal),
                          fixture_dataset(ordinal), 'needle')
            self.assertEqual(doc['schema_version'], '0.9.0')
            self.assertNotIn('tenant_id', doc)
            self.assertNotIn('tenant', doc)


if __name__ == '__main__':
    unittest.main()
