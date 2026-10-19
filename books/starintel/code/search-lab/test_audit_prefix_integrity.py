"""Network-free regression: a matching full-query digest cannot excuse a changed retained prefix.

All inputs are fictional and local. The pinned Lisp source emits search.query before
authorization; these tests neither execute Lisp nor authenticate any event.
"""
from hashlib import sha256
import unittest

from verify_query_audit import TEXT_BYTE_LIMIT, inspect_search_audit


def record(original, retained):
    raw = original.encode('utf-8')
    return {
        'event.name': 'search.query',
        'query.text': retained,
        'query.sha256': sha256(raw).hexdigest(),
        'query.bytes': len(raw),
        'query.truncated': 'true',
    }


class PrefixIntegrityTests(unittest.TestCase):
    def test_ascii_matching_prefix_is_accepted(self):
        original = 'a' * (TEXT_BYTE_LIMIT + 30)
        result = inspect_search_audit(record(original, original[:TEXT_BYTE_LIMIT]), original)
        self.assertTrue(result['original_query_digest_verified'])
        self.assertTrue(result['retained_prefix_consistent_with_original'])
        self.assertEqual(result['authorization_result'], 'not_established')

    def test_unrelated_full_length_prefix_rejected_despite_verified_digest(self):
        original = 'a' * (TEXT_BYTE_LIMIT + 30)
        with self.assertRaisesRegex(ValueError, 'logged prefix'):
            inspect_search_audit(record(original, 'z' * TEXT_BYTE_LIMIT), original)

    def test_single_changed_character_in_middle_rejected(self):
        original = 'a' * (TEXT_BYTE_LIMIT + 30)
        altered = 'a' * 6000 + 'Z' + 'a' * (TEXT_BYTE_LIMIT - 6001)
        with self.assertRaisesRegex(ValueError, 'logged prefix'):
            inspect_search_audit(record(original, altered), original)

    def test_empty_retained_text_rejected_even_without_original(self):
        original = 'a' * (TEXT_BYTE_LIMIT + 30)
        with self.assertRaisesRegex(ValueError, 'retained query'):
            inspect_search_audit(record(original, ''))

    def test_short_retained_text_rejected_even_without_original(self):
        original = 'a' * (TEXT_BYTE_LIMIT + 30)
        with self.assertRaisesRegex(ValueError, 'retained query'):
            inspect_search_audit(record(original, 'a' * (TEXT_BYTE_LIMIT - 4)))

    def test_inflated_retained_text_rejected(self):
        original = 'a' * (TEXT_BYTE_LIMIT + 30)
        with self.assertRaisesRegex(ValueError, 'retained query'):
            inspect_search_audit(record(original, 'a' * (TEXT_BYTE_LIMIT + 3)))

    def test_complete_two_byte_boundary_is_exact(self):
        original = 'a' * (TEXT_BYTE_LIMIT - 2) + 'é' + 'tail'
        cut = original[:TEXT_BYTE_LIMIT - 1]
        result = inspect_search_audit(record(original, cut), original)
        self.assertTrue(result['retained_prefix_consistent_with_original'])

    def test_complete_utf8_boundary_rejects_added_suffix(self):
        original = 'a' * (TEXT_BYTE_LIMIT - 2) + 'é' + 'tail'
        cut = 'a' * (TEXT_BYTE_LIMIT - 2) + 'é'
        with self.assertRaisesRegex(ValueError, 'truncation suffix'):
            inspect_search_audit(record(original, cut + 'X'), original)

    def test_partial_three_byte_boundary_accepts_dropped_tail(self):
        original = 'a' * (TEXT_BYTE_LIMIT - 1) + '☃' + 'tail'
        retained = 'a' * (TEXT_BYTE_LIMIT - 1)
        result = inspect_search_audit(record(original, retained), original)
        self.assertTrue(result['retained_prefix_consistent_with_original'])

    def test_partial_three_byte_boundary_accepts_one_replacement(self):
        original = 'a' * (TEXT_BYTE_LIMIT - 1) + '☃' + 'tail'
        retained = 'a' * (TEXT_BYTE_LIMIT - 1) + '\ufffd'
        result = inspect_search_audit(record(original, retained), original)
        self.assertTrue(result['retained_prefix_consistent_with_original'])

    def test_partial_four_byte_boundary_accepts_one_replacement(self):
        original = 'a' * (TEXT_BYTE_LIMIT - 1) + '😀' + 'tail'
        retained = 'a' * (TEXT_BYTE_LIMIT - 1) + '\ufffd'
        result = inspect_search_audit(record(original, retained), original)
        self.assertTrue(result['retained_prefix_consistent_with_original'])

    def test_partial_unicode_prefix_mutation_rejected(self):
        original = 'a' * (TEXT_BYTE_LIMIT - 1) + '😀' + 'tail'
        altered = 'A' + 'a' * (TEXT_BYTE_LIMIT - 2) + '\ufffd'
        with self.assertRaisesRegex(ValueError, 'logged prefix'):
            inspect_search_audit(record(original, altered), original)

    def test_partial_tail_cannot_append_multiple_pseudo_replacements(self):
        original = 'a' * (TEXT_BYTE_LIMIT - 1) + '☃' + 'tail'
        with self.assertRaisesRegex(ValueError, 'truncation suffix'):
            inspect_search_audit(record(original, 'a' * (TEXT_BYTE_LIMIT - 1) + '??'), original)

    def test_no_original_does_not_claim_prefix_verified(self):
        original = 'a' * (TEXT_BYTE_LIMIT + 30)
        result = inspect_search_audit(record(original, original[:TEXT_BYTE_LIMIT]))
        self.assertIsNone(result['retained_prefix_consistent_with_original'])
        self.assertFalse(result['original_query_digest_verified'])

    def test_untruncated_still_checks_hash_and_length(self):
        original = 'synthetic:alpha'
        attributes = record(original, original)
        attributes['query.truncated'] = 'false'
        result = inspect_search_audit(attributes, original)
        self.assertTrue(result['digest_consistent_with_logged_text'])
        self.assertTrue(result['retained_prefix_consistent_with_original'])

    def test_observation_never_becomes_authorization_or_backend_proof(self):
        original = 'a' * (TEXT_BYTE_LIMIT + 30)
        result = inspect_search_audit(record(original, original[:TEXT_BYTE_LIMIT]), original)
        self.assertEqual(result['authorization_result'], 'not_established')
        self.assertEqual(result['backend_execution'], 'not_established')


if __name__ == '__main__':
    unittest.main()
