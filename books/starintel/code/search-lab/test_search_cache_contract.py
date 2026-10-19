"""Source-pinned Chapter 15 response-cache contract, not a wire-header test."""
import hashlib
import os
from pathlib import Path
import unittest

PUBLIC_SHA = '572e78602c2b273f7ed8b45ffaa8d939ce7ce88c'
AUTH_SHA = 'eac4f1d38973cbbe3d19e9ed5e7b1b3c520919a5'
MANUSCRIPT = Path(__file__).resolve().parents[2] / 'manuscript/search-15.org'


def git_blob_sha(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def attest(raw, expected):
    if git_blob_sha(raw) != expected:
        raise ValueError('historical HTTP route source Git blob mismatch')
    return raw.decode('utf-8')


def definition(source, name, next_name):
    begin = '(defun ' + name
    end = '(defun ' + next_name
    if source.count(begin) != 1 or source.count(end) != 1:
        raise ValueError('pinned route definition not found exactly once')
    start = source.index(begin)
    stop = source.index(end, start + len(begin))
    return source[start:stop]


class SearchCacheContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(os.environ['STAR_SEARCH_LAB_SERVER'])
        cls.public = attest((root / 'source/frontends/http-contract-routes.lisp').read_bytes(), PUBLIC_SHA)
        cls.auth = attest((root / 'source/frontends/http-authorization-routes.lisp').read_bytes(), AUTH_SHA)

    def test_public_search_disallows_response_storage_at_handler(self):
        route = definition(self.public, 'handle-public-search-route', 'reduced-view-value')
        self.assertIn('(set-cache-control "no-store")', route)
        self.assertIn('cl-couch:fts-search', route)

    def test_stats_declares_a_fifteen_second_public_cache(self):
        self.assertIn('(defparameter +public-stats-cache-seconds+ 15)', self.public)
        route = definition(self.public, 'handle-public-stats-route', 'handle-openapi-route')
        self.assertIn('(format nil "public, max-age=~d" +public-stats-cache-seconds+)', route)
        self.assertIn('"count_by_dtype"', route)
        self.assertIn('"total"', route)

    def test_authenticated_handler_does_not_set_cache_control_directly(self):
        route = definition(self.auth, 'handle-authorized-search-route', 'handle-authorized-document-get-route')
        self.assertIn('cl-couch:fts-search', route)
        self.assertNotIn('set-cache-control', route)

    def test_mutated_contract_is_rejected_before_interpretation(self):
        raw = self.public.encode('utf-8').replace(b'(set-cache-control "no-store")', b'(set-cache-control "public")')
        self.assertNotEqual(git_blob_sha(raw), PUBLIC_SHA)
        with self.assertRaisesRegex(ValueError, 'Git blob mismatch'):
            attest(raw, PUBLIC_SHA)

    def test_exported_chapter_teaches_cache_not_index_truth(self):
        manuscript = MANUSCRIPT.read_text(encoding='utf-8')
        self.assertEqual(manuscript.count('** Response caching is not search freshness'), 1)
        for phrase in ('=no-store=', '=public, max-age=15=',
                       'not establish that a search index is complete',
                       'does not prove final wire headers'):
            self.assertIn(phrase, manuscript)


if __name__ == '__main__':
    unittest.main()
