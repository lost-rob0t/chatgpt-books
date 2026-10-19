"""Network-free rendering tests; all inputs are fictional search observations."""
import re
from types import SimpleNamespace
import unittest
from render_search_hits import render_hits, MAX_LABEL_CHARS


def hit(**overrides):
    row = dict(identity='org:demo', fields={'name': 'Example Cooperative'},
               dtype='org', dataset='book-synthetic',
               storage_revision='1-storage', canonical_revision='2-canonical',
               document=None)
    row.update(overrides)
    return SimpleNamespace(**row)


class SearchHitRenderingTests(unittest.TestCase):
    def test_valid_search_hit_label_and_identity(self):
        html = render_hits([hit()])
        self.assertIn('<strong>Example Cooperative</strong>', html)
        self.assertIn('<code class="hit-id">org:demo</code>', html)

    def test_identity_and_field_html_are_escaped(self):
        html = render_hits([hit(identity='<img src=x onerror=alert(1)>',
                                fields={'name': '<script>alert("demo")</script> & source'})])
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', html)
        self.assertIn('&lt;script&gt;alert(&quot;demo&quot;)&lt;/script&gt; &amp; source', html)
        self.assertNotIn('<script>', html)
        self.assertNotIn('<img', html)

    def test_scope_and_both_revision_namespaces_are_escaped(self):
        html = render_hits([hit(dataset='demo&private', dtype='org<test>',
                                storage_revision='rev"1', canonical_revision="rev'2")])
        for safe in ('demo&amp;private', 'org&lt;test&gt;', 'rev&quot;1', 'rev&#x27;2'):
            self.assertIn(safe, html)
        self.assertIn('storage revision:', html)
        self.assertIn('canonical revision:', html)

    def test_document_data_is_not_conflated_with_search_fields(self):
        html = render_hits([hit(fields={}, document={'name':'<script>doc secret</script>'})])
        self.assertIn('Unnamed search hit', html)
        self.assertNotIn('doc secret', html)

    def test_title_fallback_uses_stored_field_only(self):
        self.assertIn('<strong>Stored title</strong>',
                      render_hits([hit(fields={'title':'Stored title'})]))

    def test_empty_page_means_supplied_page_only(self):
        html = render_hits([])
        self.assertIn('No rows in this supplied page.', html)
        self.assertNotIn('No matching documents', html)

    def test_non_string_identity_and_fields_fail_closed(self):
        for bad in (hit(identity=7), hit(identity=''), hit(fields=[]),
                    hit(fields={'name':['unexpected']}),
                    hit(fields={'title':{'html':'bad'}}), hit(dtype=42)):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError): render_hits([bad])

    def test_truncation_is_bounded_before_escaping(self):
        html = render_hits([hit(fields={'name': '&' * (MAX_LABEL_CHARS + 100)})])
        self.assertIn('&amp;' * MAX_LABEL_CHARS, html)
        self.assertNotIn('&amp;' * (MAX_LABEL_CHARS + 1), html)

    def test_url_like_identity_is_never_made_a_clickable_link(self):
        html = render_hits([hit(identity='javascript:alert(1)')])
        self.assertIn('javascript:alert(1)', html)
        self.assertIsNone(re.search(r'<a\b', html, flags=re.I))
        self.assertIsNone(re.search(r'\b(href|src)\s*=', html, flags=re.I))

    def test_caller_objects_are_not_mutated(self):
        original=hit(fields={'name':'Preexisting'})
        render_hits([original])
        self.assertEqual(original.fields, {'name':'Preexisting'})
        self.assertEqual(original.identity, 'org:demo')

    def test_a_generator_of_hits_is_supported(self):
        html = render_hits(hit(identity=f'org:{i}') for i in range(3))
        self.assertEqual(html.count('<li>'), 3)
        self.assertEqual(html.count('</li>'), 3)

    def test_html_structure_is_closed_and_no_dynamic_elements(self):
        html = render_hits([hit()])
        self.assertEqual(html.count('<section'), html.count('</section>'))
        self.assertEqual(html.count('<ol>'), html.count('</ol>'))
        self.assertNotIn('<iframe', html)
        self.assertNotIn('<form', html)


    def test_overlong_name_declares_lossy_display(self):
        source = 'A' * MAX_LABEL_CHARS + 'TAMPERED_SUFFIX'
        rendered = render_hits([hit(fields={'name': source})])
        self.assertIn('<strong>' + 'A' * MAX_LABEL_CHARS + '</strong>', rendered)
        self.assertIn('<span class="label-truncation">[display truncated]</span>', rendered)
        self.assertNotIn('TAMPERED_SUFFIX', rendered)

    def test_overlong_title_fallback_declares_truncation(self):
        title = 'B' * (MAX_LABEL_CHARS + 1)
        rendered = render_hits([hit(fields={'name': '', 'title': title})])
        self.assertIn('label-truncation', rendered)
        self.assertNotIn('B' * (MAX_LABEL_CHARS + 1), rendered)

    def test_boundary_and_short_labels_are_not_called_truncated(self):
        for size in (0, 1, MAX_LABEL_CHARS - 1, MAX_LABEL_CHARS):
            with self.subTest(size=size):
                rendered = render_hits([hit(fields={'name': 'X' * size})])
                self.assertNotIn('label-truncation', rendered)

    def test_marker_is_literal_and_never_exposes_embedded_document(self):
        name = '<svg onload=alert(1)>' + ('Z' * MAX_LABEL_CHARS)
        rendered = render_hits([hit(fields={'name': name},
                                    document={'title': 'UNRETRIEVED_SECRET'})])
        self.assertIn('label-truncation', rendered)
        self.assertIn('&lt;svg onload=alert(1)&gt;', rendered)
        self.assertNotIn('<svg ', rendered)
        self.assertNotIn('UNRETRIEVED_SECRET', rendered)
        self.assertNotIn('<a ', rendered)

    def test_marker_is_per_row_not_per_page(self):
        rendered = render_hits([hit(identity='first', fields={'name': 'x' * 161}),
                                hit(identity='second', fields={'name': 'Safe'})])
        self.assertEqual(rendered.count('label-truncation'), 1)
        self.assertEqual(rendered.count('<li>'), 2)


if __name__ == '__main__':
    unittest.main()
