"""Direct use of the projection helper must not bypass the server source pin."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import lab


class ProjectionSourcePinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='search-pin-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        design = self.root / 'source/views/search.json'
        design.parent.mkdir(parents=True)
        design.write_text(json.dumps({
            'indexes': {'fts': {'index': 'function(doc){index("name",doc.name,{"store":true});}'}}
        }))

    def test_unrelated_source_cannot_execute_as_pinned_projection(self):
        # The directory contains a runnable index but is not a pinned checkout.
        with patch.object(lab.subprocess, 'run', wraps=subprocess.run) as calls:
            with self.assertRaises(subprocess.CalledProcessError):
                lab.projection(self.root, {'name': 'synthetic'})
        launched = [call for call in calls.call_args_list
                    if call.args and call.args[0][0] == 'node']
        self.assertEqual(launched, [])

    def test_pin_is_verified_before_node_executes(self):
        events = []

        def attest(root, pin):
            self.assertEqual(root, self.root)
            self.assertEqual(pin, lab.SERVER_PIN)
            events.append('attested')

        def execute(*args, **kwargs):
            events.append('executed')
            return subprocess.CompletedProcess(args, 0, stdout='[]', stderr='')

        with patch.object(lab, 'require_pin', side_effect=attest):
            with patch.object(lab.subprocess, 'run', side_effect=execute):
                self.assertEqual(lab.projection(self.root, {'name': 'synthetic'}), [])
        self.assertEqual(events, ['attested', 'executed'])

    def test_explicit_pin_failure_prevents_node(self):
        with patch.object(lab, 'require_pin', side_effect=ValueError('unverified')) as verify:
            with patch.object(lab.subprocess, 'run') as spawn:
                with self.assertRaisesRegex(ValueError, 'unverified'):
                    lab.projection(self.root, {'name': 'synthetic'})
        verify.assert_called_once_with(self.root, lab.SERVER_PIN)
        spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
