"""Native Chapter 15 regression: false, unknown, and unreported are not synonyms."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from diagnose_search_evidence import CHECKS, SERVER_GENERATIONS, diagnose

TOOL = Path(__file__).with_name('diagnose_search_evidence.py')


def case(**checks):
    return {'generation': 'historical', 'surface': 'public', 'checks': checks}


class ObservationStatesTests(unittest.TestCase):
    def test_false_null_and_missing_have_distinct_reported_states(self):
        out = diagnose(case(target_search_hit=False, durable_by_id=None))
        states = out['observation_states']
        self.assertEqual(states['target_search_hit'], 'reported_false')
        self.assertEqual(states['durable_by_id'], 'reported_inconclusive')
        self.assertEqual(states['field_emitted'], 'not_reported')
        self.assertEqual(len(states), len(CHECKS))

    def test_true_is_reported_not_independently_verified(self):
        out = diagnose(case(target_search_hit=True, durable_by_id=True))
        states = out['observation_states']
        self.assertEqual(states['target_search_hit'], 'reported_true')
        self.assertEqual(states['durable_by_id'], 'reported_true')
        self.assertEqual(out['next_check'], 'validate_document_and_provenance')
        self.assertIn('No network', ' '.join(out['limits']))

    def test_not_reported_is_not_conflated_with_explicit_unknown(self):
        absent = diagnose(case())
        inconclusive = diagnose(case(field_emitted=None))
        self.assertEqual(absent['observation_states']['field_emitted'], 'not_reported')
        self.assertEqual(inconclusive['observation_states']['field_emitted'],
                         'reported_inconclusive')
        self.assertEqual(absent['next_check'], inconclusive['next_check'])

    def test_false_input_is_preserved_without_promoting_to_durable_claim(self):
        out = diagnose(case(write_accepted=True, durable_by_id=False,
                            field_emitted=False, target_search_hit=False))
        self.assertEqual(out['observation_states']['durable_by_id'], 'reported_false')
        self.assertEqual(out['observation_states']['field_emitted'], 'reported_false')
        self.assertEqual(out['next_check'], 'authorized_by_id_read')
        self.assertEqual(out['established_observations'], ['write_accepted'])

    def test_merged_generation_changes_source_pin_not_observation_meaning(self):
        base = case(field_emitted=False, target_search_hit=None)
        previous = diagnose(base)
        merged = diagnose({**base, 'generation': 'merged', 'surface': 'authenticated'})
        self.assertNotEqual(previous['server_pin'], merged['server_pin'])
        self.assertEqual(merged['server_pin'], SERVER_GENERATIONS['merged'])
        self.assertEqual(previous['observation_states'], merged['observation_states'])

    def test_all_supported_check_names_are_reported_in_stable_order(self):
        out = diagnose(case(**dict.fromkeys(CHECKS, False)))
        self.assertEqual(list(out['observation_states']), list(CHECKS))
        self.assertTrue(all(value == 'reported_false'
                            for value in out['observation_states'].values()))

    def test_cli_json_preserves_explicit_and_missing_observation_states(self):
        request = case(target_search_hit=False, durable_by_id=None)
        proc = subprocess.run([sys.executable, str(TOOL), '-'],
                              input=json.dumps(request), text=True,
                              capture_output=True, check=True)
        parsed = json.loads(proc.stdout)
        self.assertEqual(parsed['observation_states']['target_search_hit'], 'reported_false')
        self.assertEqual(parsed['observation_states']['durable_by_id'],
                         'reported_inconclusive')
        self.assertEqual(parsed['observation_states']['write_accepted'], 'not_reported')


if __name__ == '__main__':
    unittest.main()
