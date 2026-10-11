"""BK10 dependency pins are candidates, not silently enabled providers."""
from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

from capstone import ContractError, require_component

MATRIX = json.loads((Path(__file__).parent / 'dependencies.json').read_text())
SHA = re.compile(r'[0-9a-f]{40}\Z')


class MatrixContractTest(unittest.TestCase):
    def test_version_scope(self):
        self.assertEqual(MATRIX['version'], 'bk10.dependency-matrix.v1')
        self.assertEqual(MATRIX['repository'], 'lost-rob0t/chatgpt-books')

    def test_all_worker_owners_present_once(self):
        rows = MATRIX['components']
        self.assertEqual([r['worker'] for r in rows], [f'BK{i:02}' for i in range(1, 10)])
        self.assertEqual([r['issue'] for r in rows], list(range(143, 152)))

    def test_candidate_shas_are_exact_refs(self):
        for r in MATRIX['components']:
            self.assertRegex(r['branch_head_sha'], SHA)
            if r['source_path']:
                self.assertRegex(r['commit_sha'], SHA)
                self.assertRegex(r['source_blob_sha'], SHA)
                self.assertNotEqual(r['branch_head_sha'], MATRIX['main_commit_sha'])
            else:
                self.assertIsNone(r['commit_sha'])
                self.assertIsNone(r['source_blob_sha'])

    def test_no_undocumented_contract_promotion(self):
        for r in MATRIX['components']:
            self.assertIsNone(r['contract'])
            self.assertFalse(r['integration_ready'])
            self.assertFalse(r['open_component_pr_verified'])
            self.assertFalse(r['independent_review_verified'])
            self.assertFalse(r['exact_head_pr_checks_verified'])

    def test_candidate_never_implicitly_loads(self):
        for r in MATRIX['components']:
            with self.subTest(r=r['worker']), self.assertRaisesRegex(ContractError, 'unavailable'):
                require_component({r['name']: r}, r['name'])

    def test_at_least_one_unready_candidate_and_one_unimplemented(self):
        states = {r['state'] for r in MATRIX['components']}
        self.assertIn('candidate-implementation-unreviewed', states)
        self.assertIn('no-current-feature-implementation-verified', states)


if __name__ == '__main__':
    unittest.main()
