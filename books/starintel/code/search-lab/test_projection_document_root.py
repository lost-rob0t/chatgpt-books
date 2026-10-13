"""A search projection emission requires an object root, not a JSON scalar."""
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import lab

SERVER = Path(os.environ['STAR_SEARCH_LAB_SERVER'])


class ProjectionDocumentRootTests(unittest.TestCase):
    def test_non_document_roots_fail_before_node(self):
        for value in (None, [], 'synthetic', 42, False):
            with self.subTest(value=value):
                with patch.object(lab.subprocess, 'run', wraps=subprocess.run) as run:
                    with self.assertRaisesRegex(ValueError, 'JSON document object'):
                        lab.projection(SERVER, value)
                    run.assert_not_called()

    def test_mapping_still_emits_real_pinned_index_fields(self):
        emitted = lab.projection(SERVER, {
            'dataset': 'book-public', 'dtype': 'person',
            'data': {'name': 'Synthetic Example'},
        })
        self.assertEqual([(row['field'], row['value']) for row in emitted],
                         [('tenant_id', 'default'), ('dataset', 'book-public'),
                          ('dtype', 'person'), ('name', 'Synthetic Example')])

    def test_nonfinite_member_still_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'Out of range float'):
            lab.projection(SERVER, {'name': float('nan')})


if __name__ == '__main__':
    unittest.main()
