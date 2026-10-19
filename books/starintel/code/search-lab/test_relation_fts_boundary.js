'use strict';
// Chapter 15: an FTS projection is not a canonical Relation edge index.
// Executes byte-attested original StarIntel callbacks, never a surrogate index.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const designs = [
  ['historical', process.env.STAR_SEARCH_RELATION_HISTORICAL_DESIGN ||
    (process.env.STAR_SEARCH_LAB_SERVER &&
     path.join(process.env.STAR_SEARCH_LAB_SERVER, 'source/views/search.json')),
   '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a'],
];
if (process.env.STAR_SEARCH_RELATION_MERGED_DESIGN) {
  designs.push(['merged', process.env.STAR_SEARCH_RELATION_MERGED_DESIGN,
    'dd6336f3047982db2f0e3615fed1413ed1e58e13']);
}
if (!designs[0][1]) {
  throw new Error('STAR_SEARCH_LAB_SERVER or historical design file is required');
}
const relation = Object.freeze({
  id: 'starintel:relation:synthetic-has-device',
  rev: 'synthetic-r1',
  schemaVersion: '0.10.1',
  dtype: 'relation',
  dataset: 'book-synthetic',
  source: {schema: 'org.starintel/core@1', id: 'starintel:org:synthetic-lab'},
  destination: {schema: 'org.starintel/core@1', id: 'starintel:asset:synthetic-device'},
  predicate: 'owns-device',
  direction: 'directed',
  provenance: {method: 'fictional-training-example'},
});
function gitBlob(raw) {
  return crypto.createHash('sha1')
    .update(Buffer.from(`blob ${raw.length}\0`)).update(raw).digest('hex');
}
function capture(source, document) {
  const values = [];
  const context = vm.createContext({index(field, value, options) {
    values.push({field, value, stored: options?.store === true});
  }});
  context.fn = new vm.Script(`(${source})`).runInContext(context, {timeout: 1000});
  context.doc = structuredClone(document);
  new vm.Script('fn(doc)').runInContext(context, {timeout: 1000});
  return values;
}
function valuesFor(events, name) {
  return events.filter(event => event.field === name).map(event => event.value);
}
for (const [generation, sourcePath, expected] of designs) {
  const raw = fs.readFileSync(sourcePath);
  assert.equal(gitBlob(raw), expected, `${generation}: original FTS source bytes required`);
  const design = JSON.parse(raw.toString('utf8'));
  assert.equal(design._id, '_design/search');
  const source = design.indexes.fts.index;
  test(`${generation}: canonical relation shape is explicit, not inferred`, () => {
    // Canonical shape was checked against generated StarLang 0.10.1 Relation
    // definition; this test does NOT run the canonical SDK validator.
    assert.equal(relation.dtype, 'relation');
    assert.equal(relation.schemaVersion, '0.10.1');
    assert.equal(relation.direction, 'directed');
    assert.notEqual(relation.source.id, relation.destination.id);
    assert.equal(relation.predicate, 'owns-device');
  });
  test(`${generation}: the original index emits only the relation's scope/type`, () => {
    const events = capture(source, relation);
    assert.deepEqual(events.map(({field}) => field), ['tenant_id', 'dataset', 'dtype']);
    assert.deepEqual(valuesFor(events, 'tenant_id'), ['default']);
    assert.deepEqual(valuesFor(events, 'dataset'), ['book-synthetic']);
    assert.deepEqual(valuesFor(events, 'dtype'), ['relation']);
    assert.ok(events.every(event => event.stored));
  });
  test(`${generation}: changing predicate or endpoints does not change emissions`, () => {
    const before = capture(source, relation);
    const after = capture(source, {...relation, predicate: 'operates-device',
      source: {...relation.source, id: 'starintel:org:other-lab'},
      destination: {...relation.destination, id: 'starintel:asset:other-device'},
    });
    assert.deepEqual(before, after);
    for (const field of ['predicate', 'source', 'destination', 'direction']) {
      assert.deepEqual(valuesFor(after, field), []);
    }
  });
  test(`${generation}: dataset mutation changes the same original emissions`, () => {
    assert.notDeepEqual(capture(source, relation),
      capture(source, {...relation, dataset: 'book-other-synthetic'}));
  });
  test(`${generation}: directed/symmetric flag alone cannot implement graph traversal`, () => {
    assert.deepEqual(capture(source, relation),
      capture(source, {...relation, direction: 'symmetric'}));
  });
  test(`${generation}: deliberately added predicate index detects changed edge values`, () => {
    const anchor = "add('dtype',doc.dtype);";
    assert.equal(source.split(anchor).length, 2, 'source mutation anchor drift');
    const mutant = source.replace(anchor, anchor + "add('predicate',doc.predicate);");
    assert.notDeepEqual(capture(mutant, relation),
      capture(mutant, {...relation, predicate: 'operates-device'}));
  });
}
