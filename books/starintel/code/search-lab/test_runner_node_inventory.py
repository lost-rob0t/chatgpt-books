"""Fail closed if a standalone Chapter 15 Node regression is omitted from CI.

Native Node tests requiring only the historical checked-out Server are run by
run-tests. The explicit two-generation experiment is NOT a single-checkout test.
This audit verifies registration; it does not claim a job actually executed.
"""
from collections import Counter
from pathlib import Path
import re
import unittest

HERE = Path(__file__).resolve().parent
OPTIONAL_TWO_CHECKOUT = frozenset({'test_index_generation_multiplicity.js'})
NODE_TEST_LINE = re.compile(
    r'^\s*(?:(?P<stats>STAR_SEARCH_STATS_DESIGN="\$STAR_SEARCH_LAB_SERVER/source/views/data\.json")\s+)?'
    r'node --test "\$HERE/(?P<name>test_[a-z0-9_]+\.js)"\s*$')


def check_inventory(runner: str, node_filenames: set[str]) -> None:
    """Require exactly one explicit invocation for each standard Node suite."""
    if not OPTIONAL_TWO_CHECKOUT <= node_filenames:
        raise AssertionError('declared two-checkout test is missing')
    registered = []
    for line in runner.splitlines():
        if line.lstrip().startswith('#') or not re.search(r'\bnode\s+--test\b', line):
            continue
        match = NODE_TEST_LINE.fullmatch(line)
        if not match:
            raise AssertionError(f'unrecognized Node test invocation: {line.strip()}')
        name = match.group('name')
        if bool(match.group('stats')) != (name == 'test_public_stats_scope_difference.js'):
            raise AssertionError(f'unexpected index-design environment binding for {name}')
        registered.append(name)
    duplicates = sorted(name for name, count in Counter(registered).items() if count != 1)
    if duplicates:
        raise AssertionError(f'duplicate Node suite registration: {duplicates}')
    expected = node_filenames - OPTIONAL_TWO_CHECKOUT
    missing = sorted(expected - set(registered))
    unexpected = sorted(set(registered) - expected)
    if missing or unexpected:
        raise AssertionError(f'Node regression inventory mismatch: missing={missing}, unexpected={unexpected}')
    if not registered:
        raise AssertionError('no standard Node suites were registered')


class NativeNodeInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = (HERE / 'run-tests').read_text(encoding='utf-8')
        cls.node_files = {p.name for p in HERE.glob('test_*.js')}

    def test_every_standard_node_suite_is_registered_exactly_once(self):
        check_inventory(self.runner, self.node_files)

    def test_two_generation_suite_is_deliberately_excluded(self):
        optional = (HERE / 'test_index_generation_multiplicity.js').read_text(encoding='utf-8')
        self.assertIn('files.length, 2', optional)
        self.assertNotIn('test_index_generation_multiplicity.js', self.runner)

    def test_runner_remains_fail_fast_and_source_pinned(self):
        self.assertIn('set -euo pipefail', self.runner)
        self.assertIn('require_pin(Path(sys.argv[2]), SERVER_PIN)', self.runner)
        self.assertIn('require_pin(Path(sys.argv[3]), SDK_PIN)', self.runner)
        self.assertLess(self.runner.index('require_pin(Path(sys.argv[3]), SDK_PIN)'),
                        self.runner.index('node --test'))

    def test_missing_registration_is_detected(self):
        victim = sorted(self.node_files - OPTIONAL_TWO_CHECKOUT)[0]
        line = f'node --test "$HERE/{victim}"'
        self.assertIn(line, self.runner)
        with self.assertRaisesRegex(AssertionError, 'missing='):
            check_inventory(self.runner.replace(line, '', 1), self.node_files)

    def test_duplicate_registration_is_detected(self):
        victim = sorted(self.node_files - OPTIONAL_TWO_CHECKOUT)[0]
        line = f'node --test "$HERE/{victim}"'
        with self.assertRaisesRegex(AssertionError, 'duplicate'):
            check_inventory(self.runner + '\n' + line + '\n', self.node_files)

    def test_new_unregistered_test_is_detected(self):
        with self.assertRaisesRegex(AssertionError, 'test_future_regression.js'):
            check_inventory(self.runner, self.node_files | {'test_future_regression.js'})

    def test_glob_or_indirect_command_does_not_fake_registration(self):
        with self.assertRaisesRegex(AssertionError, 'unrecognized Node test invocation'):
            check_inventory(self.runner + '\nnode --test "$HERE/test_*.js"\n', self.node_files)

    def test_removing_optional_test_requires_revisiting_the_exception(self):
        with self.assertRaisesRegex(AssertionError, 'two-checkout test is missing'):
            check_inventory(self.runner, self.node_files - OPTIONAL_TWO_CHECKOUT)


if __name__ == '__main__':
    unittest.main()
