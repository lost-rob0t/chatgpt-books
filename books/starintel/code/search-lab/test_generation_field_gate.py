"""Native tests of source-attested field preflight; no live server access."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from generation_field_gate import inspect, main, PINS

HERE = Path(__file__).parent
SERVER = Path(os.environ['STAR_SEARCH_LAB_SERVER'])
HISTORICAL = SERVER / 'source/views/search.json'
MERGED = Path(os.environ['STAR_SEARCH_FIELD_GATE_MERGED']) if os.environ.get('STAR_SEARCH_FIELD_GATE_MERGED') else None


class GenerationFieldGateTests(unittest.TestCase):
    def test_real_historical_source_reports_name_but_not_new_full_name(self):
        rows = inspect({'historical': HISTORICAL}, ['name', 'fullName', 'organizationType'])['fields']
        self.assertEqual([r['classification'] for r in rows], [
            'historical_observed_merged_unknown',
            'historical_not_observed_merged_unknown',
            'historical_not_observed_merged_unknown'])
        self.assertEqual(rows[0]['generations']['historical']['declared_analyzer'], 'keyword')

    def test_new_field_is_source_addition_not_retroactive_historical_coverage(self):
        if MERGED is None: self.skipTest('merged source requires independent pinned checkout')
        rows = inspect({'historical': HISTORICAL, 'merged': MERGED},
                       ['name', 'full_name', 'fullName', 'displayName', 'organizationType'])['fields']
        self.assertEqual([r['classification'] for r in rows], [
            'both_observed', 'both_observed', 'merged_only_observed',
            'merged_only_observed', 'neither_observed'])
        self.assertEqual(rows[2]['generations']['merged']['declared_analyzer'], 'standard')

    def test_migration_aliases_are_distinct_case_sensitive_field_names(self):
        if MERGED is None: self.skipTest('merged source requires independent pinned checkout')
        rows = inspect({'historical': HISTORICAL, 'merged': MERGED},
                       ['legal_name', 'legalName', 'org_type', 'orgType'])['fields']
        self.assertEqual([r['classification'] for r in rows], [
            'both_observed', 'merged_only_observed', 'both_observed', 'merged_only_observed'])

    def test_source_pins_independent_of_user_input(self):
        got = inspect({'historical': HISTORICAL}, ['name'])
        self.assertEqual(got['source_git_blobs'], {'historical': PINS['historical']})
        self.assertIn('not query matching', ' '.join(got['limits']))

    def test_fail_closed_on_modified_git_source(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'search.json'
            path.write_bytes(HISTORICAL.read_bytes().replace(b"'name'", b"'nickname'"))
            with self.assertRaisesRegex(ValueError, 'Git blob mismatch'):
                inspect({'historical': path}, ['name'])

    def test_reject_duplicate_invalid_or_excessive_probe_fields(self):
        for fields in ([], ['name', 'name'], ['name:evil'], ['f' * 65], ['name'] * 33):
            with self.subTest(fields=fields):
                with self.assertRaisesRegex(ValueError, 'fields|identifier'):
                    inspect({'historical': HISTORICAL}, fields)

    def test_missing_historical_source_rejected(self):
        with self.assertRaisesRegex(ValueError, 'historical'):
            inspect({}, ['name'])

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(HERE / 'generation_field_gate.py'),
                               str(HISTORICAL), *args], capture_output=True, text=True)

    def test_cli_require_historical_and_reject_omission(self):
        yes = self.run_cli('--field', 'name', '--require', 'historical')
        self.assertEqual(yes.returncode, 0, yes.stderr)
        self.assertTrue(json.loads(yes.stdout)['gate']['satisfied'])
        no = self.run_cli('--field', 'fullName', '--require', 'historical')
        self.assertEqual(no.returncode, 1, no.stderr)
        self.assertEqual(json.loads(no.stdout)['gate']['unobserved_fields'], ['fullName'])

    def test_cli_require_both_needs_actual_merged_source(self):
        bad = self.run_cli('--field', 'name', '--require', 'both')
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(bad.stdout, '')
        if MERGED is None: return
        good = self.run_cli('--merged', str(MERGED), '--field', 'name', '--require', 'both')
        self.assertEqual(good.returncode, 0, good.stderr)
        missing = self.run_cli('--merged', str(MERGED), '--field', 'fullName', '--require', 'both')
        self.assertEqual(missing.returncode, 1)

    def test_no_claim_of_canonical_validation_or_deployed_index(self):
        out = inspect({'historical': HISTORICAL}, ['title'])
        self.assertEqual(out['fields'][0]['classification'], 'historical_observed_merged_unknown')
        boundary = ' '.join(out['limits'])
        for phrase in ('canonical 0.10.1 admission', 'installed-index coverage',
                       'public/authenticated authorization', 'durable state'):
            self.assertIn(phrase, boundary)


if __name__ == '__main__':
    unittest.main()
