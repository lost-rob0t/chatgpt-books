'use strict';
const assert = require('node:assert/strict');
const {test} = require('node:test');
const {gitBlob, namedDefuns, compareForms, PUBLIC_FORMS, AUTH_FORMS, PINS} = require('./compare_search_route_generations');

test('pins three independent immutable Git blobs', () => {
  assert.match(PINS.historicalPublic, /^[a-f0-9]{40}$/);
  assert.match(PINS.mergedPublic, /^[a-f0-9]{40}$/);
  assert.match(PINS.authorization, /^[a-f0-9]{40}$/);
  assert.notEqual(PINS.historicalPublic, PINS.mergedPublic);
});
test('real Git blob encoding includes byte count and NUL', () => {
  assert.equal(gitBlob(Buffer.from('test\n')), '9daeafb9864cf43055ae93beb0afd6c7d144bfa4');
});
test('recognize named top-level defuns', () => {
  const m=namedDefuns('(defun alpha () 1)\n\n(defun beta () 2)\n');
  assert.equal(m.get('alpha'), '(defun alpha () 1)');
  assert.equal(m.get('beta'), '(defun beta () 2)');
});
test('invariant accepts matching source bodies without evaluating Lisp', () => {
  const a='(defun handle-authorized-search-route (x) x)\n';
  assert.equal(compareForms(a,a,AUTH_FORMS).length, 1);
});
test('negative control catches an actual semantic body change', () => {
  const a='(defun public-search-context () (scopes old))\n';
  const b='(defun public-search-context () (scopes wildcard))\n';
  assert.throws(()=>compareForms(a,b,['public-search-context']), /pinned defun changed/);
});
test('missing function fails closed', () => {
  assert.throws(()=>compareForms('(defun foo () 1)', '(defun foo () 1)', ['bar']), /required defun missing/);
});
test('duplicate named defun fails rather than picking an arbitrary version', () => {
  assert.throws(()=>namedDefuns('(defun foo () 1)\n(defun foo () 2)'), /duplicate defun/);
});
test('compares public and authenticated named functions independently', () => {
  assert.ok(PUBLIC_FORMS.includes('handle-public-search-route'));
  assert.ok(AUTH_FORMS.includes('handle-authorized-search-route'));
});
