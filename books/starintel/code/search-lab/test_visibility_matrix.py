"""Network-free truth-table tests for a bounded fictional search cohort."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

from visibility_matrix import evaluate


PREFIX = 'starintel:person:bookneedle-evaluation-'
IDS = [PREFIX + str(i) for i in range(5)]


def plan():
    return {
        'universe': IDS[:],
        'expected': {'public': IDS[:3] + IDS[4:],
                     'authenticated': IDS[:3]},
        'observed': {'public': IDS[:3] + IDS[4:],
                     'authenticated': IDS[:3]},
    }


class ControlledEvaluationTests(unittest.TestCase):
    def test_exact_sets_have_perfect_controlled_precision_and_recall(self):
        result = evaluate(plan())
        self.assertTrue(result['all_expected_matches'])
        self.assertEqual(result['surfaces']['public']['true_positives'], 4)
        self.assertEqual(result['surfaces']['public']['true_negatives'], 1)
        self.assertEqual(result['surfaces']['authenticated']['true_negatives'], 2)
        self.assertEqual(result['surfaces']['public']['precision'], 1)
        self.assertEqual(result['surfaces']['authenticated']['recall'], 1)

    def test_missing_allowed_control_is_not_a_security_success(self):
        p = plan()
        p['observed']['authenticated'].remove(IDS[1])
        result = evaluate(p)
        self.assertFalse(result['all_expected_matches'])
        self.assertEqual(result['surfaces']['authenticated']['missing'], [IDS[1]])
        self.assertEqual(result['surfaces']['authenticated']['false_negatives'], 1)
        self.assertEqual(result['surfaces']['authenticated']['recall'], 2 / 3)

    def test_public_forbidden_control_is_explicit_false_positive(self):
        p = plan()
        p['observed']['public'].append(IDS[3])
        result = evaluate(p)
        self.assertEqual(result['surfaces']['public']['unexpected'], [IDS[3]])
        self.assertEqual(result['surfaces']['public']['false_positives'], 1)
        self.assertEqual(result['surfaces']['public']['precision'], 4 / 5)

    def test_authenticated_other_tenant_control_is_false_positive(self):
        p = plan()
        p['observed']['authenticated'].append(IDS[4])
        self.assertEqual(evaluate(p)['surfaces']['authenticated']['unexpected'], [IDS[4]])

    def test_empty_page_does_not_claim_perfect_precision(self):
        p = plan()
        p['observed']['public'] = []
        result = evaluate(p)['surfaces']['public']
        self.assertIsNone(result['precision'])
        self.assertEqual(result['recall'], 0.0)
        self.assertEqual(result['false_negatives'], 4)

    def test_empty_expected_set_has_undefined_recall(self):
        p = plan()
        p['expected']['authenticated'] = []
        p['observed']['authenticated'] = []
        result = evaluate(p)['surfaces']['authenticated']
        self.assertIsNone(result['precision'])
        self.assertIsNone(result['recall'])
        self.assertTrue(result['matches_expected'])

    def test_unknown_observation_is_not_silently_ignored(self):
        p = plan()
        p['observed']['public'].append(PREFIX + 'unknown')
        with self.assertRaisesRegex(ValueError, 'outside the declared cohort'):
            evaluate(p)

    def test_duplicate_observation_rejected(self):
        p = plan()
        p['observed']['public'].append(IDS[0])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            evaluate(p)

    def test_oracle_is_required_for_both_surfaces(self):
        p = plan()
        del p['expected']['authenticated']
        with self.assertRaisesRegex(ValueError, 'both surfaces'):
            evaluate(p)

    def test_non_synthetic_identity_rejected(self):
        p = plan()
        p['universe'][0] = 'person-real'
        with self.assertRaisesRegex(ValueError, 'synthetic bookneedle'):
            evaluate(p)

    def test_non_list_identity_sets_rejected(self):
        p = plan()
        p['observed']['public'] = 'misleading'
        with self.assertRaisesRegex(ValueError, 'JSON array'):
            evaluate(p)

    def test_cli_exit_zero_only_for_exact_match(self):
        cmd = [sys.executable, str(Path(__file__).with_name('visibility_matrix.py'))]
        good = subprocess.run(cmd, input=json.dumps(plan()), text=True,
                              capture_output=True, check=False)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertTrue(json.loads(good.stdout)['all_expected_matches'])
        p = plan()
        p['observed']['public'].remove(IDS[0])
        mismatch = subprocess.run(cmd, input=json.dumps(p), text=True,
                                  capture_output=True, check=False)
        self.assertEqual(mismatch.returncode, 1)
        self.assertFalse(json.loads(mismatch.stdout)['all_expected_matches'])

    def test_cli_rejects_missing_oracle(self):
        cmd = [sys.executable, str(Path(__file__).with_name('visibility_matrix.py'))]
        p = plan()
        del p['expected']['public']
        rejected = subprocess.run(cmd, input=json.dumps(p), text=True,
                                  capture_output=True, check=False)
        self.assertEqual(rejected.returncode, 2)
        self.assertEqual(rejected.stdout, '')
        self.assertIn('input rejected:', rejected.stderr)

    def test_cohort_bounded(self):
        p = plan()
        p['universe'] = [PREFIX + str(i) for i in range(21)]
        with self.assertRaisesRegex(ValueError, 'bounded synthetic cohort'):
            evaluate(p)


if __name__ == '__main__':
    unittest.main()
