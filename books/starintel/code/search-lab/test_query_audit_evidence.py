"""Native Python checks of logged search-query evidence at server source pin.

Synthetic structured attributes only; no live Lisp, logger, HTTP, or Clouseau.
"""
from hashlib import sha256
import unittest
from verify_query_audit import TEXT_BYTE_LIMIT, inspect_search_audit


def audit(original, truncated=False, logged=None):
    data = original.encode('utf-8')
    return {
        'event.name': 'search.query',
        'query.text': original if logged is None else logged,
        'query.sha256': sha256(data).hexdigest(),
        'query.bytes': len(data),
        'query.truncated': 'true' if truncated else 'false',
        'principal.id': 'synthetic-principal',
    }


class AuditEvidenceTests(unittest.TestCase):
    def test_untruncated_ascii_attests_internal_text_consistency(self):
        result = inspect_search_audit(audit('fname:synthetic'))
        self.assertEqual(result['logged_text'], 'complete')
        self.assertTrue(result['digest_consistent_with_logged_text'])
        self.assertFalse(result['original_query_digest_verified'])
        self.assertEqual(result['authorization_result'], 'not_established')
        self.assertEqual(result['backend_execution'], 'not_established')

    def test_multibyte_utf8_is_counted_as_bytes_not_characters(self):
        text = 'content:' + '\u2603' * 20
        result = inspect_search_audit(audit(text), original_query=text)
        self.assertEqual(result['logged_text'], 'complete')
        self.assertTrue(result['original_query_digest_verified'])

    def test_untruncated_digest_forgery_is_rejected(self):
        item = audit('fname:synthetic')
        item['query.sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'contradicts'):
            inspect_search_audit(item)

    def test_length_mismatch_rejected(self):
        item = audit('fname:synthetic')
        item['query.bytes'] += 1
        with self.assertRaises(ValueError):
            inspect_search_audit(item)

    def test_bool_is_not_a_valid_byte_count(self):
        item = audit('fname:synthetic')
        item['query.bytes'] = True
        with self.assertRaises(ValueError):
            inspect_search_audit(item)

    def test_truncated_event_does_not_claim_full_text(self):
        original = 'x' * (TEXT_BYTE_LIMIT + 11)
        item = audit(original, truncated=True, logged=original[:TEXT_BYTE_LIMIT])
        result = inspect_search_audit(item)
        self.assertEqual(result['logged_text'], 'truncated')
        self.assertFalse(result['digest_consistent_with_logged_text'])
        self.assertFalse(result['original_query_digest_verified'])

    def test_truncated_event_can_verify_separately_supplied_original(self):
        original = 'x' * (TEXT_BYTE_LIMIT + 11)
        item = audit(original, truncated=True, logged=original[:TEXT_BYTE_LIMIT])
        result = inspect_search_audit(item, original)
        self.assertTrue(result['original_query_digest_verified'])
        self.assertEqual(result['backend_execution'], 'not_established')

    def test_wrong_original_rejected_even_for_truncated_record(self):
        original = 'x' * (TEXT_BYTE_LIMIT + 11)
        item = audit(original, truncated=True, logged=original[:TEXT_BYTE_LIMIT])
        with self.assertRaises(ValueError):
            inspect_search_audit(item, 'y' + original[1:])

    def test_utf8_boundary_does_not_assume_prefix_survives_replacement(self):
        original = 'a' * (TEXT_BYTE_LIMIT - 1) + '\u2603' + 'tail'
        # Lisp's :errorp nil can replace/drop a partial UTF-8 terminal codepoint.
        # We validate original digest/length without asserting logged prefix bytes.
        item = audit(original, truncated=True, logged='a' * (TEXT_BYTE_LIMIT - 1))
        result = inspect_search_audit(item, original)
        self.assertTrue(result['original_query_digest_verified'])
        self.assertEqual(result['logged_text'], 'truncated')

    def test_bad_truncation_flag_rejected(self):
        item = audit('short', truncated=True, logged='sho')
        with self.assertRaisesRegex(ValueError, 'truncation flag'):
            inspect_search_audit(item)

    def test_overlong_retained_text_rejected(self):
        original = 'x' * (TEXT_BYTE_LIMIT + 10)
        with self.assertRaisesRegex(ValueError, 'retained query'):
            inspect_search_audit(audit(original, truncated=True, logged=original))

    def test_malformed_event_and_digest_rejected(self):
        item = audit('short')
        item['event.name'] = 'unrelated'
        with self.assertRaises(ValueError):
            inspect_search_audit(item)
        item = audit('short')
        item['query.sha256'] = 'not-a-hash'
        with self.assertRaises(ValueError):
            inspect_search_audit(item)

    def test_string_truncation_flag_required(self):
        item = audit('short')
        item['query.truncated'] = False
        with self.assertRaises(ValueError):
            inspect_search_audit(item)


if __name__ == '__main__':
    unittest.main()
