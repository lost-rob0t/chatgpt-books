"""BK08 native regressions: implicit meta refresh cannot be gold-trace evidence.

The bounded offline executor implements *explicit* select/extract/follow actions,
never autonomous document refreshes. Active refresh metadata is fail-closed;
inert templates and ordinary metadata remain legal synthetic fixtures.
"""
from __future__ import annotations
import unittest
from offline_html_trace_executor import TraceFailure, _preflight_parsed_pages


class ImplicitMetaRefreshPreflightTests(unittest.TestCase):
    @staticmethod
    def parse(html: str):
        return _preflight_parsed_pages({"/p.html": html})

    def deny(self, html: str):
        with self.assertRaises(TraceFailure) as caught:
            self.parse(html)
        self.assertEqual(caught.exception.code, "unsafe_navigation")

    def test_simple_automatic_reload_is_rejected(self):
        self.deny('<meta http-equiv="refresh" content="0">')

    def test_absolute_external_redirect_is_rejected(self):
        self.deny('<meta http-equiv="refresh" content="0;url=https://elsewhere.invalid/">')

    def test_same_origin_redirect_is_still_implicit_and_rejected(self):
        self.deny('<meta http-equiv="refresh" content="3;url=/next.html">')

    def test_refresh_case_insensitive(self):
        self.deny('<META HTTP-EQUIV="ReFrEsH" CONTENT="0">')

    def test_refresh_attribute_value_padding(self):
        self.deny('<meta http-equiv=" \tREFRESH  " content="0">')

    def test_refresh_without_content_rejected_conservatively(self):
        self.deny('<meta http-equiv="refresh">')

    def test_refresh_in_body_rejected(self):
        self.deny('<body><div>visible</div><meta http-equiv="refresh" content="0"></body>')

    def test_refresh_in_nested_container_rejected(self):
        self.deny('<main><article><meta http-equiv="refresh" content="0"></article></main>')

    def test_unvisited_page_is_preflighted(self):
        with self.assertRaises(TraceFailure) as caught:
            _preflight_parsed_pages({"/ok.html": "<p>ok</p>", "/unvisited.html": '<meta http-equiv="refresh" content="0">'})
        self.assertEqual(caught.exception.code, "unsafe_navigation")

    def test_multiple_pages_dont_hide_refresh(self):
        with self.assertRaises(TraceFailure) as caught:
            _preflight_parsed_pages({"/ok.html": "<p>ok</p>", "/bad.html": '<meta http-equiv="refresh">', "/later.html": "<p>x</p>"})
        self.assertEqual(caught.exception.code, "unsafe_navigation")

    def test_template_refresh_is_inert(self):
        self.parse('<template><meta http-equiv="refresh" content="0"></template><p>ok</p>')

    def test_nested_template_refresh_is_inert(self):
        self.parse('<div><template><div><meta http-equiv="refresh" content="0"></div></template><p>ok</p></div>')

    def test_script_like_markup_is_not_active_element(self):
        self.parse('<script>const x = `<meta http-equiv="refresh" content="0">`;</script><p>ok</p>')

    def test_content_type_metadata_is_not_refresh(self):
        self.parse('<meta http-equiv="content-type" content="text/html"><p>ok</p>')

    def test_data_bk08_decoration_remains_legal(self):
        self.parse('<meta data-bk08="head_variant_0"><p>ok</p>')

    def test_refresh_in_name_without_http_equiv_is_legal(self):
        self.parse('<meta name="refresh" content="not an HTTP refresh"><p>ok</p>')

    def test_refresh_word_in_content_without_http_equiv_is_legal(self):
        self.parse('<meta name="description" content="refresh your knowledge"><p>ok</p>')

    def test_empty_http_equiv_value_is_legal(self):
        self.parse('<meta http-equiv="" content="0"><p>ok</p>')

    def test_duplicate_http_equiv_still_uses_existing_parse_bounds(self):
        with self.assertRaises(TraceFailure) as caught:
            self.parse('<meta http-equiv="refresh" http-equiv="content-type">')
        self.assertEqual(caught.exception.code, "parse_bounds")


if __name__ == "__main__":
    unittest.main()
