'use strict';
// Chapter 15: findability of investigation work is not proof of lifecycle state.
// Original pinned FTS callbacks, not canonical SDK or deployed Lucene results.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const expected = Object.freeze({
  historical: '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged: 'dd6336f3047982db2f0e3615fed1413ed1e58e13',
});
const historical = process.env.STAR_SEARCH_WORK_HISTORICAL_DESIGN ||
  (process.env.STAR_SEARCH_LAB_SERVER &&
   path.join(process.env.STAR_SEARCH_LAB_SERVER, 'source/views/search.json'));
if (!historical) throw new Error('pinned historical search.json required');
const inputs = [['historical', historical]];
if (process.env.STAR_SEARCH_WORK_MERGED_DESIGN) {
  inputs.push(['merged', process.env.STAR_SEARCH_WORK_MERGED_DESIGN]);
}
function sourceFor(generation, filename) {
  const bytes = fs.readFileSync(filename);
  const blob = crypto.createHash('sha1')
    .update(Buffer.from(`blob ${bytes.length}\0`)).update(bytes).digest('hex');
  assert.equal(blob, expected[generation], `${generation}: index source changed`);
  const design = JSON.parse(bytes.toString('utf8'));
  assert.equal(design._id, '_design/search');
  assert.equal(typeof design.indexes.fts.index, 'string');
  return design.indexes.fts.index;
}
function capture(source, record) {
  const events = [];
  const context = vm.createContext({index(field, value, options) {
    events.push({field, value, stored: options?.store === true});
  }});
  context.indexer = new vm.Script(`(${source})`).runInContext(context, {timeout: 1000});
  context.record = structuredClone(record);
  new vm.Script('indexer(record)').runInContext(context, {timeout: 1000});
  return events;
}
function values(events, name) {
  return events.filter(e => e.field === name).map(e => e.value);
}

// StarLang org.starintel/core@1 0.10.1 generated schema at
// commit 96d26c338078676ec1dc6928755901636c9f7ef0;
// blob 537163da436f67a973e280d1704e32bdba5b888b.
// Synthetic schema-shaped examples only: no SDK validation is performed.
const investigationTarget = Object.freeze({
  id: 'starintel:investigation-target:fictional-demo',
  dataset: 'book-synthetic', dtype: 'investigation-target',
  schemaVersion: '0.10.1', rev: 'r1',
  target: 'fictional-example.example',
  query: 'example cooperative',
  status: 'pending',
  targetType: 'domain',
});
const operation = Object.freeze({
  id: 'starintel:operation:fictional-demo',
  dataset: 'book-synthetic', dtype: 'operation',
  schemaVersion: '0.10.1', rev: 'r1',
  mission: 'Inspect fictional example records',
  status: 'planned',
  phases: [{phaseId: 'research', objective: 'Inspect example', state: 'planned'}],
});
for (const [generation, filename] of inputs) {
  const source = sourceFor(generation, filename);
  test(`${generation}: investigation target exposes a target token but not work status`, () => {
    const events = capture(source, investigationTarget);
    assert.deepEqual(events.map(e => e.field),
      ['tenant_id', 'dataset', 'dtype', 'target']);
    assert.deepEqual(values(events, 'target'), ['fictional-example.example']);
    assert.deepEqual(values(events, 'status'), []);
    assert.deepEqual(values(events, 'query'), []);
    assert.ok(events.every(e => e.stored));
  });
  test(`${generation}: investigation status/query changes do not change raw emissions`, () => {
    const before = capture(source, investigationTarget);
    const after = capture(source, {...investigationTarget,
      status: 'completed', query: 'another fictional query'});
    assert.deepEqual(before, after);
  });
  test(`${generation}: investigation target changes do affect raw emissions`, () => {
    const after = capture(source, {...investigationTarget, target: 'second-fictional.example'});
    assert.notDeepEqual(capture(source, investigationTarget), after);
    assert.deepEqual(values(after, 'target'), ['second-fictional.example']);
  });
  test(`${generation}: operation status and mission are absent even with required phases`, () => {
    const before = capture(source, operation);
    assert.deepEqual(before.map(e => e.field), ['tenant_id', 'dataset', 'dtype']);
    assert.deepEqual(values(before, 'status'), []);
    assert.deepEqual(values(before, 'mission'), []);
    assert.deepEqual(values(before, 'phases'), []);
    assert.deepEqual(before, capture(source, {...operation, status: 'active',
      mission: 'Updated fictional mission',
      phases: [{phaseId: 'review', objective: 'Different objective', state: 'ready'}]}));
  });
  test(`${generation}: operation dataset/type remain positive scope controls`, () => {
    const before = capture(source, operation);
    const after = capture(source, {...operation, dataset: 'other-synthetic', dtype: 'other'});
    assert.notDeepEqual(before, after);
    assert.deepEqual(values(before, 'dataset'), ['book-synthetic']);
    assert.deepEqual(values(before, 'dtype'), ['operation']);
  });
  test(`${generation}: deliberately augmented status index detects changes`, () => {
    const anchor = "add('dtype',doc.dtype);";
    assert.equal(source.split(anchor).length, 2, 'mutation anchor drift');
    const augmented = source.replace(anchor, anchor + "add('status',doc.status);");
    assert.notDeepEqual(capture(augmented, operation),
      capture(augmented, {...operation, status: 'active'}));
    assert.deepEqual(values(capture(augmented, operation), 'status'), ['planned']);
  });
}
