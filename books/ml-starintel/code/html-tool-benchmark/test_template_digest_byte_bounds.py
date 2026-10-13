"""Native BK08 regression: direct template fingerprints obey page-byte bounds."""
from __future__ import annotations

import hashlib
import json
import unittest
from unittest.mock import patch

import html_template_split_audit as audit
from offline_html_trace_executor import MAX_PAGE_BYTES, TraceFailure


class TemplateDigestByteBounds(unittest.TestCase):
    def fails_with(self, payload, expected):
        with self.assertRaises(TraceFailure) as caught:
            audit.template_digest(payload)
        self.assertEqual(caught.exception.code, expected)

    def test_non_text_is_typed_invalid_record(self):
        self.fails_with(None, "invalid_record")

    def test_ascii_page_exact_byte_budget_allowed(self):
        self.assertEqual(len(audit.template_digest("x" * MAX_PAGE_BYTES)), 64)

    def test_ascii_byte_budget_plus_one_fails_before_parser(self):
        with patch.object(audit, "BoundedParser", side_effect=AssertionError("parser invoked")):
            self.fails_with("x" * (MAX_PAGE_BYTES + 1), "parse_bounds")

    def test_multibyte_characters_consume_encoded_bytes(self):
        self.assertEqual(len(audit.template_digest("é" * (MAX_PAGE_BYTES // 2))), 64)
        self.fails_with("é" * (MAX_PAGE_BYTES // 2 + 1), "parse_bounds")

    def test_four_byte_utf8_boundary(self):
        self.assertEqual(len(audit.template_digest("🧪" * (MAX_PAGE_BYTES // 4))), 64)
        self.fails_with("🧪" * (MAX_PAGE_BYTES // 4 + 1), "parse_bounds")

    def test_surrogate_is_typed_parse_bounds_not_unicode_error(self):
        self.fails_with("<p>broken \ud800</p>", "parse_bounds")

    def test_markup_with_exact_byte_budget_allowed(self):
        html = "<p>" + "z" * (MAX_PAGE_BYTES - len("<p></p>")) + "</p>"
        self.assertEqual(len(html.encode("utf-8")), MAX_PAGE_BYTES)
        self.assertEqual(len(audit.template_digest(html)), 64)

    def test_markup_one_byte_over_boundary_rejected(self):
        html = "<p>" + "z" * (MAX_PAGE_BYTES - len("<p></p>") + 1) + "</p>"
        self.fails_with(html, "parse_bounds")

    def test_existing_shape_equivalence_unchanged(self):
        self.assertEqual(audit.template_digest("<p id='a'>Ada</p>"),
                         audit.template_digest("<p id='b'>Grace</p>"))

    def test_comment_fragmentation_unchanged(self):
        self.assertEqual(audit.template_digest("<p>Grace</p>"),
                         audit.template_digest("<p>Gr<!-- note -->ace</p>"))

    def test_existing_shape_difference_unchanged(self):
        self.assertNotEqual(audit.template_digest("<p>x</p>"),
                            audit.template_digest("<section>x</section>"))

    def test_digest_is_repeatable(self):
        html = "<main class='thing'><a href='one.html'>Details</a></main>"
        self.assertEqual(audit.template_digest(html), audit.template_digest(html))


if __name__ == "__main__":
    unittest.main()
