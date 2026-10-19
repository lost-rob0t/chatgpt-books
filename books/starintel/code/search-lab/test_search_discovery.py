"""Hermetic tests for the pinned HTTP registry-vs-handler discovery seam."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from compare_search_discovery import PINNED, _form, analyze, audit_checkout, blob_sha


def fragments():
    # Minimal *source-shaped* fixture snippets. These never masquerade as an
    # authentic server checkout. audit_checkout() enforces full Git blob SHAs.
    return {
        'cli/http-contract-final.lisp': '''(upsert-http-operation
 (make-http-operation
  :id "public.search.get"
  :client-name "public-search"
  :method :get
  :path "/api/v1/search"
  :authority :public
  :responses (list (response 200 "Public search result." (generic-object-schema)))))''',
        'cli/http-contract-documents.lisp': '''(defparameter +document-search-query-parameters+
 (list (list :name "q" :required t :schema (string-schema :min-length 1))
       (list :name "limit") (list :name "bookmark")
       (list :name "sort") (list :name "dataset") (list :name "tenant")))
(upsert-http-operation (make-http-operation
  :id "documents.search"
  :path "/api/v1/documents/search"
  :authority :authenticated
  :query-parameters +document-search-query-parameters+
  :responses (list (response 200 "Full-text search hits." (generic-object-schema)))))''',
        'source/frontends/http-contract-routes.lisp': '''(defun handle-public-search-route (params)
  (with-http-boundary ()
    (let* ((q (require-query-string params "q"))
           (limit (bounded-query-integer params "limit" :default 25)))
      (let ((bookmark (query-value params "bookmark")))
        (list q limit bookmark)))))''',
        'source/frontends/http-authorization-routes.lisp': '''(defun handle-authorized-search-route (params)
  (with-http-boundary ()
    (let* ((q (require-query-string params "q"))
           (limit (bounded-query-integer params "limit")))
      (list q limit))))''',
    }


class SearchDiscoveryTests(unittest.TestCase):
    def test_source_shaped_declaration_fragments_show_public_gap(self):
        result = analyze(fragments())
        self.assertTrue(result['public_discovery_q_gap'])
        self.assertTrue(result['public_route_requires_q'])
        self.assertFalse(result['public_registry_declares_query_parameters'])
        self.assertTrue(result['authenticated_registry_declares_required_q'])

    def test_authentic_pinned_checkout_when_runner_supplies_it(self):
        root = os.environ.get('STAR_SEARCH_LAB_SERVER')
        if not root:
            self.skipTest('authentic historical server checkout unavailable; pin audit NOT RUN')
        result = audit_checkout(Path(root))
        self.assertTrue(result['public_discovery_q_gap'])
        self.assertEqual(result['claim_class'], 'PINNED_SOURCE_DECLARATIONS_ONLY')

    def test_fixing_public_query_declaration_changes_gap_result(self):
        items = fragments()
        items['cli/http-contract-final.lisp'] = items['cli/http-contract-final.lisp'].replace(
            ':authority :public', ':authority :public\n  :query-parameters +document-search-query-parameters+')
        self.assertFalse(analyze(items)['public_discovery_q_gap'])

    def test_missing_public_required_query_rejected_not_misclassified(self):
        items = fragments()
        items['source/frontends/http-contract-routes.lisp'] = items[
            'source/frontends/http-contract-routes.lisp'].replace(
                '(require-query-string params "q")', '(query-value params "q")')
        with self.assertRaisesRegex(ValueError, 'source shapes changed'):
            analyze(items)

    def test_authenticated_required_q_declaration_drift_rejected(self):
        items = fragments()
        items['cli/http-contract-documents.lisp'] = items[
            'cli/http-contract-documents.lisp'].replace(':name "q" :required t', ':name "q"')
        with self.assertRaisesRegex(ValueError, 'source shapes changed'):
            analyze(items)

    def test_full_source_set_required(self):
        items = fragments()
        del items['cli/http-contract-final.lisp']
        with self.assertRaisesRegex(ValueError, 'all four'):
            analyze(items)

    def test_comments_and_strings_do_not_corrupt_balanced_forms(self):
        src = '''(defun proof (x) ; ignored ) and (
  (list "string ( ) \\"quoted\\"" (if x 1 2)))'''
        self.assertEqual(_form(src, '(defun proof'), src)

    def test_duplicate_declarations_fail_closed(self):
        src = '(defun proof () t)\n(defun proof () nil)'
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            _form(src, '(defun proof')

    def test_unterminated_form_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            _form('(defun proof (', '(defun proof')

    def test_no_arbitrary_source_is_accepted_as_historical(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, contents in fragments().items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(contents, encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Git blob mismatch'):
                audit_checkout(root)

    def test_git_blob_hash_uses_exact_content_bytes(self):
        self.assertEqual(blob_sha(b'hello world\n'),
                         '3b18e512dba79e4c8300dd08aeb37f8e728b8dad')
        self.assertEqual(len(PINNED), 4)


if __name__ == '__main__':
    unittest.main()
