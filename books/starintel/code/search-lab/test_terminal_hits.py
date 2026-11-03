"""Native offline regression for terminal-safe search-result display."""
from dataclasses import dataclass, field
from pathlib import Path
import unittest

from terminal_hits import render_hits


@dataclass
class ExampleHit:
    identity: str = 'starintel:person:fictional'
    fields: dict = field(default_factory=lambda: {'name': 'Fictional Example'})
    dtype: str | None = 'person'
    dataset: str | None = 'book-public'
    storage_revision: str | None = '1-a'
    canonical_revision: str | None = '1'
    document: dict | None = None


class TerminalPreviewTests(unittest.TestCase):
    def test_simple_hit_is_explicitly_unverified(self):
        text = render_hits([ExampleHit()])
        self.assertIn('UNVERIFIED RESULT OBSERVATIONS', text)
        self.assertIn('identity="starintel:person:fictional"', text)
        self.assertIn('Observed hits on this page: 1', text)

    def test_esc_and_cursor_controls_are_not_executed(self):
        payload = '\x1b[2J\x1b]8;;https://invalid.example\x07spoof\x1b]8;;\x07'
        text = render_hits([ExampleHit(fields={'name': payload})])
        self.assertNotIn('\x1b', text)
        self.assertNotIn('\x07', text)
        self.assertIn(r'\u001b[2J', text)
        self.assertIn(r'\u0007', text)

    def test_crlf_does_not_forge_extra_result(self):
        text = render_hits([ExampleHit(fields={'name': 'ok\r\n[2] VERIFIED'})])
        self.assertIn(r'ok\r\n[2] VERIFIED', text)
        self.assertNotIn('\n[2] VERIFIED', text)
        self.assertEqual(text.count('\n[1] '), 1)

    def test_bidi_override_and_isolate_are_not_executed(self):
        text = render_hits([ExampleHit(fields={'name': 'left\u202eattack\u2066right'})])
        self.assertIn(r'left\u202eattack\u2066right', text)
        self.assertNotIn('\u202e', text)
        self.assertNotIn('\u2066', text)

    def test_full_output_is_ascii_and_quotes_are_escaped(self):
        text = render_hits([ExampleHit(fields={'name': 'Café "double"'})])
        self.assertTrue(text.isascii())
        self.assertIn(r'Caf\u00e9 \"double\"', text)

    def test_title_fallback_does_not_show_embedded_doc(self):
        text = render_hits([ExampleHit(fields={'title': 'Index title'},
                                       document={'title': 'SECRET DOCUMENT FIELD'})])
        self.assertIn('Index title', text)
        self.assertNotIn('SECRET DOCUMENT FIELD', text)

    def test_no_retrieved_label_has_explicit_null(self):
        self.assertIn('label=null', render_hits([ExampleHit(fields={})]))

    def test_tombstone_field_not_promoted_to_a_state_claim(self):
        text = render_hits([ExampleHit(fields={'name': 'Record', 'status': 'open'},
                                       document={'deleted': True})])
        self.assertNotIn('status=', text)
        self.assertNotIn('deleted=', text)

    def test_storage_and_canonical_revisions_remain_separate(self):
        text = render_hits([ExampleHit(storage_revision='7-storage',
                                       canonical_revision='5-canonical')])
        self.assertIn('storage_rev="7-storage" canonical_rev="5-canonical"', text)

    def test_revision_control_characters_are_quoted(self):
        text = render_hits([ExampleHit(storage_revision='1-a\x1b[0m')])
        self.assertIn(r'storage_rev="1-a\u001b[0m"', text)
        self.assertNotIn('\x1b', text)

    def test_empty_page_is_not_missing_corpus(self):
        text = render_hits([])
        self.assertIn('No rows in the supplied page; corpus coverage is unknown.', text)

    def test_non_string_stored_label_fails_closed(self):
        with self.assertRaises(ValueError):
            render_hits([ExampleHit(fields={'name': {'$html': 'raw'}})])

    def test_identity_is_required(self):
        with self.assertRaises(ValueError):
            render_hits([ExampleHit(identity='')])

    def test_nonstring_revision_is_rejected(self):
        with self.assertRaises(ValueError):
            render_hits([ExampleHit(canonical_revision=42)])

    def test_overlong_label_truncates_and_marks_its_origin(self):
        text = render_hits([ExampleHit(fields={'name': 'Z' * 240})])
        self.assertIn('Z' * 160 + '" [truncated]', text)
        self.assertNotIn('Z' * 161, text)

    def test_oversized_identity_is_marked_incomplete(self):
        text = render_hits([ExampleHit(identity="X" * 400)])
        self.assertIn("X" * 240 + '" [truncated]', text)
        self.assertNotIn("X" * 241, text)

    def test_page_limit_rejects_101_hits(self):
        with self.assertRaisesRegex(ValueError, '100 search hits'):
            render_hits(ExampleHit(identity=f'book:{i}') for i in range(101))

    def test_generator_consumed_once(self):
        hits = (ExampleHit(identity=f'synthetic:{i}') for i in range(2))
        self.assertIn('Observed hits on this page: 2', render_hits(hits))


if __name__ == '__main__':
    unittest.main()
