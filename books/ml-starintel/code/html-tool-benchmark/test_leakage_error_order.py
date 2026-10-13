"""Native unittest: equivalent fixture dictionaries must give identical leakage evidence."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from html_template_split_audit import audit_and_evaluate, template_digest
from offline_html_trace_executor import TraceFailure

HTML_A = '<span id="target">Alpha</span>'
HTML_B = '<div id="target">Beta</div>'
HTML_C = '<article><p id="target">Gamma</p></article>'


def specimen(duplicate: bool=True, dev_reverse: bool=False):
    def row(id_, family, pages, start, value):
        actions=[{'op':'select','selector':'#target'},{'op':'extract','field':'value'}]
        return {'id':id_, 'family':family, 'pages':dict(pages), 'start':start,
                'gold_trace':copy.deepcopy(actions), 'candidate_trace':copy.deepcopy(actions),
                'gold_extractions':{'value':value},'gold_visited':[start]}
    train=[row('a_train','family_a',[('/a.html',HTML_A)],'/a.html','Alpha'),
           row('b_train','family_b',[('/b.html',HTML_B)],'/b.html','Beta')]
    dev_pages=[('/a.html',HTML_A.replace('Alpha','Anne')),
               ('/b.html',HTML_B.replace('Beta','Bob'))]
    if not duplicate:
        dev_pages=[('/a.html','<h1 id="target">Anne</h1>'),
                   ('/b.html','<h2 id="target">Bob</h2>')]
    if dev_reverse: dev_pages.reverse()
    dev=[row('c_dev','family_dev',dev_pages,'/a.html','Anne')]
    test=[row('d_test','family_test',[('/c.html',HTML_C)],'/c.html','Gamma')]
    return {'train':train,'dev':dev,'test':test}


def failure(rows):
    try:audit_and_evaluate(rows)
    except TraceFailure as exc:
        return exc.code,str(exc)
    return None,None

class StableLeakageAttribution(unittest.TestCase):
    def test_actual_multiple_cross_split_templates_exist(self):
        self.assertNotEqual(template_digest(HTML_A),template_digest(HTML_B))
        self.assertEqual(template_digest(HTML_A),template_digest(HTML_A.replace('Alpha','Anne')))
        self.assertEqual(template_digest(HTML_B),template_digest(HTML_B.replace('Beta','Bob')))
    def test_forward_dev_order_blames_canonical_page(self):
        code,detail=failure(specimen())
        self.assertEqual(code,'split_leakage')
        self.assertIn('a_train/c_dev',detail)
    def test_reverse_dev_order_blames_same_canonical_page(self):
        self.assertEqual(failure(specimen()),failure(specimen(dev_reverse=True)))
    def test_all_permutations_of_crossing_pages_are_stable(self):
        base=failure(specimen())
        for reverse in [False,True]:
            with self.subTest(reverse=reverse):
                rows=specimen(dev_reverse=reverse)
                rows['train'].reverse()
                self.assertEqual(failure(rows),base)
    def test_crossing_detection_remains_before_scoring(self):
        rows=specimen();original_evaluate=__import__('html_template_split_audit').evaluate
        def never(*args,**kwargs):raise AssertionError('scorer must not run on leaked partition')
        __import__('html_template_split_audit').evaluate=never
        try:self.assertEqual(failure(rows)[0],'split_leakage')
        finally:__import__('html_template_split_audit').evaluate=original_evaluate
    def test_mutating_text_only_does_not_hide_overlap(self):
        rows=specimen();rows['dev'][0]['pages']['/a.html']='<span id="changed">Anne</span>'
        rows['dev'][0]['gold_trace'][0]['selector']='#changed'
        rows['dev'][0]['candidate_trace'][0]['selector']='#changed'
        self.assertEqual(failure(rows)[0],'split_leakage')
    def test_no_overlap_keeps_clean_split_report(self):
        rows=specimen(duplicate=False)
        result=audit_and_evaluate(rows)
        self.assertEqual(result['samples'],4)
        self.assertEqual(result['family_count'],4)
    def test_no_overlap_order_reversal_keeps_report(self):
        a=audit_and_evaluate(specimen(duplicate=False))
        b=audit_and_evaluate(specimen(duplicate=False,dev_reverse=True))
        self.assertEqual(a,b)
    def test_only_one_overlapping_template_is_unchanged(self):
        rows=specimen();rows['dev'][0]['pages']['/b.html']='<h2 id="target">Bob</h2>'
        self.assertEqual(failure(rows)[0],'split_leakage')
        self.assertIn('a_train/c_dev',failure(rows)[1])
    def test_attribute_value_changes_keep_shape_overlap(self):
        rows=specimen();rows['dev'][0]['pages']['/a.html']='<span class="fresh" id="target">Anne</span>'
        # A changed attribute KEY changes shape, so B is first shared shape.
        self.assertIn('b_train/c_dev',failure(rows)[1])
    def test_families_with_identical_names_still_fail(self):
        rows=specimen(duplicate=False);rows['dev'][0]['family']='family_a'
        self.assertEqual(failure(rows)[0],'split_leakage')
    def test_duplicate_id_still_fails_before_template_walk(self):
        rows=specimen(duplicate=False);rows['dev'][0]['id']='a_train'
        self.assertEqual(failure(rows)[0],'split_leakage')

if __name__=='__main__':unittest.main()
