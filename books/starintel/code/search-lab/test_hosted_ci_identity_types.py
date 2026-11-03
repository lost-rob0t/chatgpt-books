"""Fail-closed regression: bool is int in Python, but not a GitHub numeric ID."""
import copy
import unittest

from classify_hosted_ci import EvidenceError, classify_jobs
from test_classify_hosted_ci import ROOT, SHA


class HostedIdentityBoundaryTests(unittest.TestCase):
    def root(self):
        return copy.deepcopy(ROOT)

    def test_nonhex_sha_is_not_a_commit_identity(self):
        payload = self.root()
        payload['jobs'][0]['head_sha'] = 'z' * 40
        with self.assertRaisesRegex(EvidenceError, 'expected_exact_40_hex_head'):
            classify_jobs(payload, 'z' * 40)

    def test_boolean_job_id_is_invalid(self):
        payload = self.root()
        payload['jobs'][0]['id'] = True
        with self.assertRaisesRegex(EvidenceError, 'invalid_job_identity'):
            classify_jobs(payload, SHA)

    def test_boolean_total_count_is_not_a_complete_listing(self):
        payload = self.root()
        payload['total_count'] = True
        with self.assertRaisesRegex(EvidenceError, 'empty_or_partial_job_listing'):
            classify_jobs(payload, SHA)

    def test_missing_run_id_is_not_an_authenticated_run(self):
        payload = self.root()
        payload['jobs'][0]['run_id'] = None
        with self.assertRaisesRegex(EvidenceError, 'invalid_run_identity'):
            classify_jobs(payload, SHA)

    def test_boolean_runner_id_cannot_support_executed_success(self):
        payload = self.root()
        payload['jobs'][0].update(conclusion='success', runner_id=True,
                                  runner_name='synthetic', steps=[{'name': 'checkout'}])
        with self.assertRaisesRegex(EvidenceError, 'invalid_runner_identity'):
            classify_jobs(payload, SHA)

    def test_negative_runner_id_is_not_a_valid_unassigned_runner(self):
        payload = self.root()
        payload['jobs'][0]['runner_id'] = -1
        with self.assertRaisesRegex(EvidenceError, 'invalid_runner_identity'):
            classify_jobs(payload, SHA)

    def test_non_object_step_cannot_be_execution_evidence(self):
        payload = self.root()
        payload['jobs'][0].update(conclusion='success', runner_id=42,
                                  runner_name='synthetic', steps=['reported test'])
        with self.assertRaisesRegex(EvidenceError, 'invalid_step_identity'):
            classify_jobs(payload, SHA)

    def test_valid_observed_no_runner_still_classifies_conservatively(self):
        self.assertEqual(classify_jobs(self.root(), SHA)['classification'],
                         'FAILED_BEFORE_OBSERVED_RUNNER_OR_STEP')


if __name__ == '__main__':
    unittest.main()
