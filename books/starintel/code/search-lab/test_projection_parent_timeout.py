"""Hermetic parent-process deadline contract for the historical index capture."""
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import lab
from lab import projection


class ParentProcessDeadlineTests(unittest.TestCase):
    def test_capture_has_parent_process_timeout(self):
        with patch.object(lab, 'require_pin'), patch.object(lab.subprocess, 'run') as run:
            run.return_value.stdout = '[]'
            self.assertEqual(projection(Path('/synthetic/pin'), {'dtype': 'person'}), [])
            kwargs = run.call_args.kwargs
            self.assertEqual(kwargs.get('timeout'), 30)
            self.assertTrue(kwargs['check'])
            self.assertTrue(kwargs['capture_output'])
            self.assertEqual(kwargs['input'], '{"dtype": "person"}')

    def test_failure_does_not_become_empty_projection(self):
        with patch.object(lab, 'require_pin'), patch.object(lab.subprocess, 'run',
                side_effect=subprocess.CalledProcessError(2, 'node')):
            with self.assertRaises(subprocess.CalledProcessError):
                projection(Path('/synthetic/pin'), {})

    def test_timeout_does_not_become_empty_projection(self):
        with patch.object(lab, 'require_pin'), patch.object(lab.subprocess, 'run',
                side_effect=subprocess.TimeoutExpired('node', 30)):
            with self.assertRaises(subprocess.TimeoutExpired):
                projection(Path('/synthetic/pin'), {})

    def test_invalid_root_is_rejected_before_launch(self):
        with patch.object(lab, 'require_pin'), patch.object(lab.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'JSON document object'):
                projection(Path('/synthetic/pin'), [])
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
