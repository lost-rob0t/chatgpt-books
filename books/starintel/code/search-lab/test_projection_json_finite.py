"""Reject non-finite Python float values before passing JSON to the pinned index."""
import os
from pathlib import Path
import unittest
from lab import projection

SERVER = Path(os.environ['STAR_SEARCH_LAB_SERVER'])


class ProjectionFiniteJSONTests(unittest.TestCase):
    def test_nan_rejected_before_node(self):
        with self.assertRaisesRegex(ValueError, 'Out of range float'):
            projection(SERVER, {'data': {'content': float('nan')}})

    def test_infinities_rejected_before_node(self):
        for value in (float('inf'), float('-inf')):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, 'Out of range float'):
                    projection(SERVER, {'data': {'content': value}})

    def test_nonfinite_nested_value_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Out of range float'):
            projection(SERVER, {'extra': [None, {'value': float('nan')}]})

    def test_finite_number_reaches_pinned_index(self):
        emissions = projection(SERVER, {'data': {'content': 1.5}})
        self.assertEqual([row['value'] for row in emissions
                          if row['field'] == 'content'], [1.5])

    def test_boolean_remains_a_valid_scalar(self):
        emissions = projection(SERVER, {'data': {'content': False}})
        self.assertEqual([row['value'] for row in emissions
                          if row['field'] == 'content'], [False])


if __name__ == '__main__':
    unittest.main()
