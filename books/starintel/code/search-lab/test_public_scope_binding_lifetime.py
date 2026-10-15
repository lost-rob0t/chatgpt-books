"""Pinned source contract: public dataset scope is a Lisp binding, not request getenv."""
import hashlib
import os
from pathlib import Path
import unittest

PINNED_ROUTE_SHA = '572e78602c2b273f7ed8b45ffaa8d939ce7ce88c'
MANUSCRIPT = Path(__file__).resolve().parents[2] / 'manuscript/search-15.org'
README = Path(__file__).resolve().parent / 'README.org'


def git_blob_sha(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\\0' + raw).hexdigest()


def section(source, begin, end):
    if source.count(begin) != 1 or source.count(end) != 1:
        raise ValueError('pinned public-route source structure changed')
    return source[source.index(begin):source.index(end, source.index(begin) + len(begin))]


def verify_binding_lifetime(source):
    binding = section(source, '(defparameter *public-search-datasets*',
                      '(defparameter +public-search-path+')
    scopes = section(source, '(defun public-search-scopes', '(defun public-search-context')
    context = section(source, '(defun public-search-context',
                      '(defun public-search-authorized-query')
    query = section(source, '(defun public-search-authorized-query',
                    '(defun reject-public-scope-overrides')
    if binding.count('(uiop:getenv "STAR_PUBLIC_SEARCH_DATASETS")') != 1:
        raise ValueError('expected startup-time environment binding')
    if not ("'(\"*\")" in binding or "'(*" in binding):
        raise ValueError('historical wildcard default has changed')
    if 'uiop:getenv' in scopes or '*public-search-datasets*' not in scopes:
        raise ValueError('request-time public scope binding changed')
    if '(public-search-scopes)' not in context or '(public-search-context)' not in query:
        raise ValueError('public trusted-query context chain changed')
    return binding, scopes


class PublicScopeBindingLifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(os.environ['STAR_SEARCH_LAB_SERVER'])
        raw = (root / 'source/frontends/http-contract-routes.lisp').read_bytes()
        if git_blob_sha(raw) != PINNED_ROUTE_SHA:
            raise ValueError('pinned public route Git blob mismatch')
        cls.source = raw.decode('utf-8')

    def test_environment_is_read_at_definition_evaluation(self):
        binding, _ = verify_binding_lifetime(self.source)
        self.assertIn('(defparameter *public-search-datasets*', binding)

    def test_scope_construction_reads_binding_not_environment(self):
        _, scopes = verify_binding_lifetime(self.source)
        self.assertIn('"dataset:~a"', scopes)
        self.assertNotIn('getenv', scopes)

    def test_trusted_context_uses_current_bound_scopes(self):
        verify_binding_lifetime(self.source)
        self.assertIn(':principal context', section(
            self.source, '(defun public-search-authorized-query',
            '(defun reject-public-scope-overrides'))

    def test_deliberate_request_time_getenv_mutation_is_detected(self):
        original = '           *public-search-datasets*)))'
        self.assertEqual(self.source.count(original), 1)
        mutated = self.source.replace(
            original, '           (uiop:getenv "STAR_PUBLIC_SEARCH_DATASETS"))))')
        with self.assertRaisesRegex(ValueError, 'request-time public scope'):
            verify_binding_lifetime(mutated)

    def test_exported_chapter_warns_about_live_environment_changes(self):
        chapter = MANUSCRIPT.read_text(encoding='utf-8')
        self.assertEqual(chapter.count('Changing a supervisor environment variable after the process started does not update that bound value.'), 1)
        self.assertIn('=public-search-scopes=', chapter)

    def test_lab_readme_marks_runtime_policy_observation_unverified(self):
        readme = README.read_text(encoding='utf-8')
        self.assertIn('* Public dataset scope binding lifetime', readme)
        self.assertIn('not a native reload or live authorization test', readme)


if __name__ == '__main__':
    unittest.main()
