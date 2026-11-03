'use strict';
// Chapter 15: finding a MapLayer name is not evidence of rendering or feature coverage.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const PINS = {historical: '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged: 'dd6336f3047982db2f0e3615fed1413ed1e58e13'};
const historical = process.env.STAR_SEARCH_MAP_HISTORICAL_DESIGN ||
  (process.env.STAR_SEARCH_LAB_SERVER &&
    path.join(process.env.STAR_SEARCH_LAB_SERVER, 'source/views/search.json'));
if (!historical) throw new Error('pinned historical search design required');
const generations = [['historical', historical]];
if (process.env.STAR_SEARCH_MAP_MERGED_DESIGN)
  generations.push(['merged', process.env.STAR_SEARCH_MAP_MERGED_DESIGN]);
function source(file, generation) {
  const bytes = fs.readFileSync(file);
  const sha = crypto.createHash('sha1')
    .update(Buffer.from('blob ' + bytes.length + '\0')).update(bytes).digest('hex');
  assert.equal(sha, PINS[generation], 'original Git blob changed');
  const design = JSON.parse(bytes.toString('utf8'));
  assert.equal(design._id, '_design/search');
  assert.equal(design.indexes.fts.analyzer.fields.dataset, 'keyword');
  assert.equal(design.indexes.fts.analyzer.fields.tenant_id, 'keyword');
  return design.indexes.fts.index;
}
function capture(fn, doc) {
  const rows = [];
  const scope = vm.createContext({index(field, value, options) {
    rows.push({field, value, stored: options && options.store === true});
  }});
  scope.callback = new vm.Script('(' + fn + ')').runInContext(scope, {timeout: 1000});
  scope.doc = structuredClone(doc);
  new vm.Script('callback(doc)').runInContext(scope, {timeout: 1000});
  return rows;
}
const values = (rows, field) => rows.filter(row => row.field === field)
  .map(row => row.value);
// Fictional canonical-shaped MapLayer; SDK admission and actual rendering are NOT run.
const original = {id: 'starintel:map-layer:fictional-grid', rev: 'r1',
  schemaVersion: '0.10.1', dtype: 'map-layer', dataset: 'fictional-map-demo',
  name: 'Fictional grid overlay', kind: 'vector',
  sourceDataset: 'fictional-features', visible: true, readOnly: true,
  minimumZoom: 1, maximumZoom: 15,
  features: [{id: 'fictional-feature-1'}],
  style: {stroke: 'solid'}, query: 'synthetic query only'};
const invisible = ['kind', 'sourceDataset', 'visible', 'readOnly',
  'minimumZoom', 'maximumZoom', 'features', 'style', 'query'];
for (const [generation, file] of generations) {
  const fn = source(file, generation);
  const base = capture(fn, original);
  test(generation + ': indexes label and scope, not a rendered map', () => {
    assert.deepEqual(values(base, 'name'), [original.name]);
    assert.deepEqual(values(base, 'dtype'), ['map-layer']);
    assert.deepEqual(values(base, 'dataset'), ['fictional-map-demo']);
    assert.deepEqual(values(base, 'tenant_id'), ['default']);
    assert.ok(base.every(row => row.stored));
    for (const key of invisible) assert.deepEqual(values(base, key), []);
  });
  test(generation + ': changing feature inventory leaves projection unchanged', () => {
    assert.deepEqual(capture(fn, {...original, features: []}), base);
    assert.deepEqual(capture(fn, {...original, features: [
      {id: 'fictional-feature-9'}, {id: 'fictional-feature-10'}]}), base);
  });
  test(generation + ': visibility and read-only flags are not index admission', () => {
    assert.deepEqual(capture(fn, {...original, visible: false, readOnly: false}), base);
  });
  test(generation + ': switching sourceDataset or query does not change label', () => {
    assert.deepEqual(capture(fn, {...original, sourceDataset: 'another-synthetic-source',
      query: 'another fictional query'}), base);
  });
  test(generation + ': style and zoom changes cannot demonstrate renderer behavior', () => {
    assert.deepEqual(capture(fn, {...original, style: {stroke: 'dashed'},
      minimumZoom: 0, maximumZoom: 4}), base);
  });
  test(generation + ': kind changes do not become typed renderer evidence', () => {
    assert.deepEqual(capture(fn, {...original, kind: 'imaginary'}), base);
    assert.deepEqual(values(base, 'kind'), []);
  });
  test(generation + ': indexed name is a positive control', () => {
    const changed = capture(fn, {...original, name: 'Another fictional overlay'});
    assert.notDeepEqual(changed, base);
    assert.deepEqual(values(changed, 'name'), ['Another fictional overlay']);
  });
  test(generation + ': dataset is search scope metadata, not authorization', () => {
    const changed = capture(fn, {...original, dataset: 'fictional-private'});
    assert.notDeepEqual(changed, base);
    assert.deepEqual(values(changed, 'dataset'), ['fictional-private']);
    assert.deepEqual(values(changed, 'sourceDataset'), []);
  });
  test(generation + ': in-memory feature indexing mutation fails the RED control', () => {
    const anchor = "add('title',doc.title);";
    assert.equal(fn.split(anchor).length, 2, 'source mutation anchor changed');
    const mutant = fn.replace(anchor, anchor + "add('features',doc.features);");
    // Arrays of objects do not emit; use a scalar proxy to test the actual add() path.
    const mutated = capture(mutant, {...original, features: ['fictional-feature-1']});
    assert.deepEqual(values(mutated, 'features'), ['fictional-feature-1']);
    assert.notDeepEqual(mutated, base);
    if (process.env.STAR_SEARCH_MAP_RED === '1')
      assert.deepEqual(mutated, base, 'intentional RED: feature labels became indexed');
  });
}
