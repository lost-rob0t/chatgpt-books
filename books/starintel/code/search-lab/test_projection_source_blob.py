"""Attest exact historical FTS design bytes, not only a clean-looking Git index."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import lab
from verify_installed_design import git_blob_sha, HISTORICAL_GIT_BLOB

SERVER = Path(os.environ['STAR_SEARCH_LAB_SERVER'])
SOURCE = (SERVER / 'source/views/search.json').read_bytes()


class ProjectionSourceBlobTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='book-search-source-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.path = self.root / 'source/views/search.json'
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(SOURCE)

    def run_projection(self):
        # Runner verifies HEAD/cleanliness; this seam isolates source bytes.
        with patch.object(lab, 'require_pin') as pin:
            result = lab.projection(self.root, {'name': 'Synthetic Book'})
            pin.assert_called_once_with(self.root, lab.SERVER_PIN)
            return result

    def test_official_historical_source_bytes(self):
        self.assertEqual(git_blob_sha(SOURCE), HISTORICAL_GIT_BLOB)

    def test_exact_index_runs_native_node_capture(self):
        events = self.run_projection()
        self.assertEqual([x['value'] for x in events if x['field'] == 'name'],
                         ['Synthetic Book'])
        self.assertEqual([x['value'] for x in events if x['field'] == 'tenant_id'],
                         ['default'])

    def test_modified_function_is_not_pinned_evidence(self):
        text = self.path.read_text()
        self.assertIn("var tenant='default'", text)
        self.path.write_text(text.replace("var tenant='default'", "var tenant='altered'"))
        with self.assertRaisesRegex(ValueError, 'Git blob mismatch'):
            self.run_projection()

    def test_changed_analyzer_is_not_pinned_evidence(self):
        text = self.path.read_text()
        self.assertIn('"default":"standard"', text)
        self.path.write_text(text.replace('"default":"standard"', '"default":"whitespace"'))
        with self.assertRaisesRegex(ValueError, 'Git blob mismatch'):
            self.run_projection()

    def test_absent_design_fails_before_node(self):
        self.path.unlink()
        with self.assertRaisesRegex(ValueError, 'source is unavailable'):
            self.run_projection()

    def test_git_skip_worktree_can_hide_a_tracked_change(self):
        # Disposable local repo; no remote checkout or product writes.
        repo = self.root / 'demo'
        repo.mkdir()
        def git(*args):
            return subprocess.check_output(['git', '-C', str(repo), *args],
                                           text=True, stderr=subprocess.DEVNULL).strip()
        git('init', '-q')
        git('config', 'user.name', 'book-test')
        git('config', 'user.email', 'book-test@example.invalid')
        design = repo / 'search.json'
        design.write_bytes(SOURCE)
        git('add', 'search.json')
        git('commit', '-qm', 'synthetic')
        git('update-index', '--skip-worktree', 'search.json')
        design.write_text('{"changed":true}')
        self.assertEqual(git('status', '--porcelain', '--untracked-files=no'), '')
        self.assertTrue(git('ls-files', '-v', 'search.json').startswith('S '))
        self.assertNotEqual(git_blob_sha(design.read_bytes()), HISTORICAL_GIT_BLOB)


if __name__ == '__main__':
    unittest.main()
