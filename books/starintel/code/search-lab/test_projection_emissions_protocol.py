"""Chapter 15: JSON stdout is not automatically a valid index emission."""
import json
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import lab as module


def event(field='name', value='A synthetic value', store=True):
    return {'field': field, 'value': value, 'options': {'store': store}}


class ProjectionEnvelopeTests(unittest.TestCase):
    def call(self, value):
        completed = types.SimpleNamespace(stdout=json.dumps(value))
        with patch.object(module, 'require_pin') as pinned, patch.object(
                module.subprocess, 'run', return_value=completed) as runner:
            answer = module.projection(Path('/synthetic-pinned-root'), {'dtype': 'org'})
        pinned.assert_called_once_with(Path('/synthetic-pinned-root'), module.SERVER_PIN)
        self.assertEqual(runner.call_args.kwargs['timeout'], 30)
        self.assertFalse(runner.call_args.kwargs.get('shell', False))
        return answer

    def test_valid_scalar_events_preserve_false_zero_and_empty(self):
        data = [event(value=False), event('count', 0), event('title', '')]
        self.assertEqual(self.call(data), data)

    def test_empty_emissions_are_valid(self):
        self.assertEqual(self.call([]), [])

    def test_nonlist_is_not_an_emission_envelope(self):
        with self.assertRaisesRegex(ValueError, 'captured index emissions'):
            self.call({'rows': []})

    def test_emission_field_must_be_a_name(self):
        with self.assertRaisesRegex(ValueError, 'malformed captured index emission'):
            self.call([event(field=None)])

    def test_emission_must_be_stored(self):
        with self.assertRaisesRegex(ValueError, 'malformed captured index emission'):
            self.call([event(store=False)])

    def test_nested_emission_is_not_a_scalar(self):
        with self.assertRaisesRegex(ValueError, 'malformed captured index emission'):
            self.call([event(value={'nested': 'wrong'})])

    def test_null_value_is_not_an_emission(self):
        with self.assertRaisesRegex(ValueError, 'malformed captured index emission'):
            self.call([event(value=None)])

    def test_emission_must_be_a_mapping(self):
        with self.assertRaisesRegex(ValueError, 'malformed captured index emission'):
            self.call([['wrong', 'shape']])


if __name__ == '__main__':
    unittest.main()
