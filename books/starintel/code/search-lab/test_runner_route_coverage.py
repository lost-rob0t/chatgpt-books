"""Contract: the native standalone search-route Node regressions run in CI.

The two-checkout comparator is an additional optional experiment, not a
prerequisite for its eight self-contained native Node unit tests.
"""
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent


class RouteRegressionRegistrationTests(unittest.TestCase):
    def test_native_route_contract_is_part_of_standard_runner(self):
        script = (HERE / 'run-tests').read_text()
        self.assertEqual(script.count('node --test "$HERE/test_route_generation.js"'), 1)

    def test_pinned_server_sdk_checks_remain_before_native_node_suites(self):
        script = (HERE / 'run-tests').read_text()
        self.assertIn('require_pin(Path(sys.argv[2]), SERVER_PIN)', script)
        self.assertIn('require_pin(Path(sys.argv[3]), SDK_PIN)', script)
        self.assertLess(script.index('require_pin(Path(sys.argv[3]), SDK_PIN)'),
                        script.index('node --test "$HERE/test_route_generation.js"'))

    def test_two_checkout_comparator_not_in_single_checkout_runner(self):
        script = (HERE / 'run-tests').read_text()
        self.assertNotIn('test_index_generation_multiplicity.js', script)
        self.assertNotIn('node "$HERE/compare_search_route_generations.js"', script)


if __name__ == '__main__':
    unittest.main()
