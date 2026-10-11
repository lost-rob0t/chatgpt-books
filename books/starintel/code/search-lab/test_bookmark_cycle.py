"""Network-free pagination-cycle checks for the opt-in Chapter 15 HTTP lab."""
import unittest
from unittest.mock import patch
import service_checks


def page(identity, bookmark):
    if identity is None:
        return {'rows': [], 'bookmark': bookmark}
    return {'rows': [{'id': identity, 'doc': {'_id': identity}}], 'bookmark': bookmark}


class BookmarkCycleTests(unittest.TestCase):
    def test_nonadjacent_bookmark_cycle_fails_on_third_page(self):
        bookmarks = ('opaque-a', 'opaque-b', 'opaque-a')
        calls = []

        def respond(base, path, token):
            calls.append(path)
            ordinal = len(calls)
            return 200, page('synthetic-' + str(ordinal), bookmarks[(ordinal - 1) % 3])

        with patch.object(service_checks, 'request', side_effect=respond):
            with self.assertRaisesRegex(ValueError, 'bookmark cycle across pages'):
                service_checks.collect('http://127.0.0.1', 'authenticated', 'name:synthetic', 'dummy')
        self.assertEqual(len(calls), 3, 'fail before re-submitting the first opaque bookmark')

    def test_unique_continuations_and_empty_terminal_page_succeed(self):
        responses = (page('one', 'opaque-a'), page('two', 'opaque-b'), page(None, 'opaque-c'))
        calls = []

        def respond(base, path, token):
            calls.append(path)
            return 200, responses[len(calls) - 1]

        with patch.object(service_checks, 'request', side_effect=respond):
            self.assertEqual(service_checks.collect('http://127.0.0.1', 'public', 'name:synthetic'),
                             {'one', 'two'})
        self.assertEqual(len(calls), 3)

    def test_adjacent_bookmark_repeat_remains_rejected(self):
        responses = (page('one', 'opaque-a'), page('two', 'opaque-a'))
        calls = []

        def respond(base, path, token):
            calls.append(path)
            return 200, responses[len(calls) - 1]

        with patch.object(service_checks, 'request', side_effect=respond):
            with self.assertRaisesRegex(ValueError, 'missing/repeated bookmark'):
                service_checks.collect('http://127.0.0.1', 'public', 'name:synthetic')
        self.assertEqual(len(calls), 2)

    def test_duplicate_identity_remains_rejected(self):
        responses = (page('one', 'opaque-a'), page('one', 'opaque-b'))
        calls = []

        def respond(base, path, token):
            calls.append(path)
            return 200, responses[len(calls) - 1]

        with patch.object(service_checks, 'request', side_effect=respond):
            with self.assertRaisesRegex(ValueError, 'duplicate identity'):
                service_checks.collect('http://127.0.0.1', 'public', 'name:synthetic')
        self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
