"""Conflicting opt-in search-lab modes must be rejected before HTTP."""
import contextlib
import io
import json
import os
import sys
import unittest
from unittest.mock import patch
import service_checks


ENV = {
    'STAR_SEARCH_LAB_URL': 'http://127.0.0.1',
    'STAR_SEARCH_LAB_DISPOSABLE': '1',
    'STAR_SEARCH_LAB_WRITER': 'dummy-writer',
    'STAR_SEARCH_LAB_OTHER_WRITER': 'dummy-other-writer',
    'STAR_SEARCH_LAB_READER': 'dummy-reader',
    'STAR_SEARCH_LAB_NOSEARCH': 'dummy-nosearch',
}


class SearchLabModesTests(unittest.TestCase):
    def test_conflicting_flags_rejected_before_http(self):
        with (
            patch.dict(os.environ, ENV),
            patch.object(sys, 'argv', ['service_checks.py', '--seed', '--expect-backend-failure']),
            patch.object(service_checks, 'request',
                         side_effect=AssertionError('ambiguous mode reached HTTP')) as request,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as caught:
                service_checks.main()
        self.assertEqual(caught.exception.code, 2)
        request.assert_not_called()

    def test_backend_failure_mode_uses_read_only_probe(self):
        output = io.StringIO()
        with (
            patch.dict(os.environ, ENV),
            patch.object(sys, 'argv', ['service_checks.py', '--expect-backend-failure']),
            patch.object(service_checks, 'request', return_value=(503, {})) as request,
            contextlib.redirect_stdout(output),
        ):
            service_checks.main()
        self.assertEqual(json.loads(output.getvalue()),
                         {'backend_fault': 'TESTED', 'http_status': 503})
        request.assert_called_once_with('http://127.0.0.1',
                                        '/api/v1/search?q=fname%3Asynthetic')

    def test_missing_mode_fails_before_http(self):
        with (
            patch.dict(os.environ, ENV),
            patch.object(sys, 'argv', ['service_checks.py']),
            patch.object(service_checks, 'request') as request,
        ):
            with self.assertRaisesRegex(ValueError, 'requires --seed'):
                service_checks.main()
        request.assert_not_called()

    def test_seed_mode_begins_with_authentication_check(self):
        with (
            patch.dict(os.environ, ENV),
            patch.object(sys, 'argv', ['service_checks.py', '--seed']),
            patch.object(service_checks, 'request',
                         side_effect=RuntimeError('intentional no-network boundary')) as request,
        ):
            with self.assertRaisesRegex(RuntimeError, 'intentional no-network'):
                service_checks.main()
        request.assert_called_once_with('http://127.0.0.1', '/auth/context',
                                        'dummy-writer')


if __name__ == '__main__':
    unittest.main()
