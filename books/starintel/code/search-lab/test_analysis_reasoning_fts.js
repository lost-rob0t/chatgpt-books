'use strict';
// Chapter 15: a matching Analysis label does not establish an inference verdict.
// Execute exact historical and merged Server search callback Git blobs.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const PINS = Object.freeze({
  historical: '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged: 'dd6336f3047982db2f0e3615fed1413ed1e58e13',
});
const root = process.env.STAR_SEARCH_LAB_SERVER;
const historical = process.env.STAR_SEARCH_ANALYSIS_HISTORICAL_DESIGN ||
  (root && path.join(root, 'source/views/search.json'));
if (!historical) throw new Error('original historical search.json is required');
const inputs = [['historical', historical]];
if (process.env.STAR_SEARCH_ANALYSIS_MERGED_DESIGN)
  inputs.push(['merged', process.env.STAR_SEARCH_ANALYSIS_MERGED_DESIGN]);

function sourceFor(file, generation) {
  const bytes = fs.readFileSync(file);
  const sha = crypto.createHash('sha1')
    .update(Buffer.from(`blob ${bytes.length}\0`)).update(bytes).digest('hex');
  assert.equal(sha, PINS[generation], `${generation}: original Git blob drift`);
  const design = JSON.parse(bytes.toString('utf8'));
  assert.equal(design._id, '_design/search');
  assert.equal(design.indexes.fts.analyzer.fields.dataset, 'keyword');
  assert.equal(design.indexes.fts.analyzer.fields.tenant_id, 'keyword');
  return design.indexes.fts.index;
}

function capture(callback, record) {
  const events = [];
  const context = vm.createContext({index(field, value, options) {
    events.push({field, value, stored: options?.store === true});
  }});
  context.callback = new vm.Script(`(${callback})`).runInContext(context, {timeout: 1000});
  context.record = structuredClone(record);
  new vm.Script('callback(record)').runInContext(context, {timeout: 1000});
  return events;
}
const values = (events, field) => events.filter(e => e.field === field).map(e => e.value);

// Canonical-shaped fictional Analysis. This test does NOT claim SDK admission.
const original = Object.freeze({
  id: 'starintel:analysis:training-001', rev: 'r1', dtype: 'analysis',
  dataset: 'training-reasoning', schemaVersion: '0.10.1',
  title: 'Fictional bridge closure assessment',
  question: 'Was the test bridge closed at noon?',
  hypotheses: ['Bridge closed', 'Bridge open'],
  conclusions: ['Insufficient evidence'],
  counterarguments: ['Archive timestamp may be stale'],
  limitations: ['No independently verified primary observation'],
  uncertaintySources: ['Conflicting fictional timestamps'],
  inputIds: ['starintel:event:training-a'],
  reasoningArtifactIds: ['starintel:file:training-proof-a'],
  reviewIds: ['starintel:review:training-001'],
  status: 'draft',
});
const unsupported = [
  'question', 'hypotheses', 'conclusions', 'counterarguments', 'limitations',
  'uncertaintySources', 'inputIds', 'reasoningArtifactIds', 'reviewIds', 'status',
];

for (const [generation, file] of inputs) {
  const source = sourceFor(file, generation);
  const baseline = capture(source, original);

  test(`${generation}: searchable Analysis title and scope are emitted`, () => {
    assert.deepEqual(values(baseline, 'title'), [original.title]);
    assert.deepEqual(values(baseline, 'dtype'), ['analysis']);
    assert.deepEqual(values(baseline, 'dataset'), ['training-reasoning']);
    assert.deepEqual(values(baseline, 'tenant_id'), ['default']);
    assert.ok(baseline.every(e => e.stored));
  });
  test(`${generation}: opposing hypotheses and conclusions have identical index emissions`, () => {
    const changed = {...original, hypotheses: ['Bridge always open'],
      conclusions: ['Definitely open']};
    assert.deepEqual(capture(source, changed), baseline);
    for (const field of ['hypotheses', 'conclusions'])
      assert.deepEqual(values(baseline, field), []);
  });
  test(`${generation}: counterarguments and uncertainty never imply adjudication`, () => {
    const changed = {...original, counterarguments: [], limitations: [],
      uncertaintySources: [], status: 'reviewed'};
    assert.deepEqual(capture(source, changed), baseline);
    for (const field of ['counterarguments', 'limitations', 'uncertaintySources', 'status'])
      assert.deepEqual(values(baseline, field), []);
  });
  test(`${generation}: referenced inputs, reviews, artifacts and question are not indexed`, () => {
    const changed = {...original, question: 'Entirely different question',
      inputIds: ['starintel:event:training-b'],
      reasoningArtifactIds: [], reviewIds: []};
    assert.deepEqual(capture(source, changed), baseline);
    for (const field of ['question', 'inputIds', 'reasoningArtifactIds', 'reviewIds'])
      assert.deepEqual(values(baseline, field), []);
  });
  test(`${generation}: nested data cannot certify a reasoning outcome`, () => {
    const a = capture(source, {...original, data: {conclusions: ['Unknown'], status: 'draft'}});
    const b = capture(source, {...original, data: {conclusions: ['Confirmed'], status: 'reviewed'}});
    assert.deepEqual(a, b);
    assert.deepEqual(a, baseline);
  });
  test(`${generation}: title is a positive-control indexed field`, () => {
    const changed = capture(source, {...original, title: 'Another fictional assessment'});
    assert.notDeepEqual(changed, baseline);
    assert.deepEqual(values(changed, 'title'), ['Another fictional assessment']);
  });
  test(`${generation}: dataset affects indexed scope but never grants authorization`, () => {
    const changed = capture(source, {...original, dataset: 'training-private'});
    assert.notDeepEqual(changed, baseline);
    assert.deepEqual(values(changed, 'dataset'), ['training-private']);
    for (const field of unsupported) assert.deepEqual(values(changed, field), []);
  });
  test(`${generation}: in-memory conclusion-indexing mutant is detected`, () => {
    const needle = "add('title',doc.title);";
    assert.equal(source.split(needle).length, 2, 'mutation anchor changed');
    const mutant = source.replace(needle, needle + "add('conclusions',doc.conclusions);");
    const changed = capture(mutant, {...original, conclusions: ['Definitely open']});
    assert.deepEqual(values(changed, 'conclusions'), ['Definitely open']);
    assert.notDeepEqual(changed, baseline);
    if (process.env.STAR_SEARCH_ANALYSIS_RED === '1')
      assert.deepEqual(changed, baseline, 'intentional RED: mutant indexed conclusions');
  });
}
