"""BK08 implicit embedded browsing-context preflight, fully offline.

A static gold trace cannot represent automatic navigation in an iframe/frame.
The tests exercise byte-exact published preflight/parser excerpts locally.
"""
from __future__ import annotations
import unittest

from preflight_stub import TraceFailure, _preflight_parsed_pages


class EmbeddedContextPreflightTests(unittest.TestCase):
    def assert_unsafe(self, pages: dict[str, str], page: str = "/") -> None:
        with self.assertRaises(TraceFailure) as failure:
            _preflight_parsed_pages(pages)
        self.assertEqual(failure.exception.code, "unsafe_navigation")
        self.assertIn(page, str(failure.exception))

    def test_relative_iframe_src_is_implicit_navigation(self):
        self.assert_unsafe({"/": '<div>safe</div><iframe src="/detail"></iframe>'})

    def test_cross_origin_iframe_src_cannot_hide_in_static_fixture(self):
        self.assert_unsafe({"/": '<iframe src="https://external.invalid/embed"></iframe>'})

    def test_present_empty_iframe_src_is_not_silently_ignored(self):
        self.assert_unsafe({"/": '<iframe src=""></iframe>'})

    def test_srcdoc_embeds_unmodeled_nested_document(self):
        self.assert_unsafe({"/": '<iframe srcdoc="&lt;h1&gt;title&lt;/h1&gt;"></iframe>'})

    def test_frame_src_is_same_browsing_context_failure(self):
        self.assert_unsafe({"/": '<frameset><frame src="/detail"></frameset>'})

    def test_html_case_folding_cannot_evade_detection(self):
        self.assert_unsafe({"/": '<IFRAME SRC="/detail"></IFRAME>'})

    def test_unvisited_page_is_preflight_checked(self):
        self.assert_unsafe({"/": '<p>start</p>', "/unvisited": '<iframe src="/detail"></iframe>'}, "/unvisited")

    def test_plain_anchor_is_explicit_follow_only_and_allowed(self):
        parsed = _preflight_parsed_pages({"/": '<a href="/detail">Details</a>', "/detail": '<p>value</p>'})
        self.assertEqual(set(parsed), {"/", "/detail"})

    def test_image_subresource_does_not_claim_document_navigation(self):
        parsed = _preflight_parsed_pages({"/": '<img src="/photo.png" alt="photo">'})
        self.assertIn("/", parsed)

    def test_template_descendant_iframe_remains_inert(self):
        parsed = _preflight_parsed_pages({"/": '<template><iframe src="/detail"></iframe></template><p>live</p>'})
        self.assertIn("/", parsed)

    def test_script_style_markup_text_stays_inert(self):
        parsed = _preflight_parsed_pages({"/": '<script>"<iframe src=/other>"</script><style>/* <frame src=/other> */</style>'})
        self.assertIn("/", parsed)

    def test_iframe_without_navigation_attributes_is_not_a_url_claim(self):
        parsed = _preflight_parsed_pages({"/": '<iframe title="empty"></iframe>'})
        self.assertIn("/", parsed)

    def test_published_active_meta_refresh_remains_rejected(self):
        self.assert_unsafe({"/": '<meta http-equiv="refresh" content="0;url=/detail">'})

    def test_duplicate_html_attributes_still_fail_closed(self):
        with self.assertRaises(TraceFailure) as failure:
            _preflight_parsed_pages({"/": '<iframe src="/one" src="/two"></iframe>'})
        self.assertEqual(failure.exception.code, "parse_bounds")


if __name__ == "__main__":
    unittest.main()
