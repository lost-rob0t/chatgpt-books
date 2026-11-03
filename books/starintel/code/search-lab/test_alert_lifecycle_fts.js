'use strict';
// Runs byte-attested original JavaScript FTS callbacks, not Lucene or an SDK.
// Synthetic canonical-shaped Alert; no canonical validation or HTTP claim.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const pins = {
  historical: '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged: 'dd6336f3047982db2f0e3615fed1413ed1e58e13',
};
const original = process.env.STAR_SEARCH_ALERT_HISTORICAL_DESIGN ||
  (process.env.STAR_SEARCH_LAB_SERVER &&
   path.join(process.env.STAR_SEARCH_LAB_SERVER, 'source/views/search.json'));
if (!original) throw new Error('pinned historical search.json required');
const inputs = [['historical', original]];
if (process.env.STAR_SEARCH_ALERT_MERGED_DESIGN)
  inputs.push(['merged', process.env.STAR_SEARCH_ALERT_MERGED_DESIGN]);
function sourceFrom(file, generation) {
  const bytes = fs.readFileSync(file);
  const sha = crypto.createHash('sha1').update(Buffer.from('blob ' + bytes.length + '\0'))
    .update(bytes).digest('hex');
  assert.equal(sha, pins[generation], 'source Git blob changed');
  const design = JSON.parse(bytes.toString('utf8'));
  assert.equal(design._id, '_design/search');
  return design.indexes.fts.index;
}
function capture(source, doc) {
  const out = [];
  const context = vm.createContext({index(field, value, options) {
    out.push({field, value, stored: options && options.store === true});
  }});
  context.doc = structuredClone(doc);
  context.fn = new vm.Script('(' + source + ')').runInContext(context, {timeout: 1000});
  new vm.Script('fn(doc)').runInContext(context, {timeout: 1000});
  return out;
}
const values = (events, name) => events.filter(e => e.field === name).map(e => e.value);
// Names and types checked against StarLang 0.10.1 generated Alert definition
// at commit 96d26c338078676ec1dc6928755901636c9f7ef0.
const alert = {
  id: 'starintel:alert:fictional-drill', rev: 'synthetic-r1',
  dtype: 'alert', dataset: 'book-synthetic', schemaVersion: '0.10.1',
  status: 'open', severity: '0.75', triggeredAt: '2026-10-01T10:00:00Z',
  resolvedAt: null, acknowledgedBy: [], suppressedUntil: '2026-10-02T10:00:00Z',
  subjectIds: ['starintel:asset:fictional-beacon'], ruleId: 'fictional-training-rule',
};
for (const [generation, file] of inputs) {
  const src = sourceFrom(file, generation);
  const base = capture(src, alert);
  test(generation + ': original callback emits only scope/type', () => {
    assert.deepEqual(base.map(e => e.field), ['tenant_id', 'dataset', 'dtype']);
    assert.deepEqual(values(base, 'tenant_id'), ['default']);
    assert.deepEqual(values(base, 'dataset'), ['book-synthetic']);
    assert.deepEqual(values(base, 'dtype'), ['alert']);
    assert.ok(base.every(e => e.stored));
  });
  test(generation + ': severity does not affect emissions', () => {
    assert.deepEqual(capture(src, {...alert, severity: '0.01'}), base);
    assert.deepEqual(values(base, 'severity'), []);
  });
  test(generation + ': status is not an FTS lifecycle predicate', () => {
    assert.deepEqual(capture(src, {...alert, status: 'resolved'}), base);
    assert.deepEqual(values(base, 'status'), []);
  });
  test(generation + ': triggering and resolution times are omitted', () => {
    assert.deepEqual(capture(src, {...alert, triggeredAt: '2026-10-03T10:00:00Z',
      resolvedAt: '2026-10-03T11:00:00Z'}), base);
    assert.deepEqual(values(base, 'triggeredAt'), []);
    assert.deepEqual(values(base, 'resolvedAt'), []);
  });
  test(generation + ': acknowledgement and suppression are omitted', () => {
    assert.deepEqual(capture(src, {...alert, acknowledgedBy: ['fictional-operator'],
      suppressedUntil: '2026-10-04T00:00:00Z'}), base);
    assert.deepEqual(values(base, 'acknowledgedBy'), []);
    assert.deepEqual(values(base, 'suppressedUntil'), []);
  });
  test(generation + ': rule and subject references are not FTS joins', () => {
    assert.deepEqual(capture(src, {...alert, ruleId: 'other-fictional-rule',
      subjectIds: ['starintel:asset:other-fictional-beacon']}), base);
    assert.deepEqual(values(base, 'ruleId'), []);
    assert.deepEqual(values(base, 'subjectIds'), []);
  });
  test(generation + ': dataset is a positive scope control', () => {
    const changed = capture(src, {...alert, dataset: 'book-other'});
    assert.notDeepEqual(changed, base);
    assert.deepEqual(values(changed, 'dataset'), ['book-other']);
  });
  test(generation + ': dtype is a positive type control', () => {
    const changed = capture(src, {...alert, dtype: 'observation'});
    assert.notDeepEqual(changed, base);
    assert.deepEqual(values(changed, 'dtype'), ['observation']);
  });
}
