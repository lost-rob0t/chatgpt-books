'use strict';
// Canonical Org.organizationType is not the historical/merged org_type/orgType alias.
// Original Git-blob-attested FTS projection only, NOT Lucene/CouchDB or SDK validation.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const PINNED = Object.freeze({
  historical: '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged: 'dd6336f3047982db2f0e3615fed1413ed1e58e13',
});
const historical = process.env.STAR_SEARCH_ORG_HISTORICAL_DESIGN ||
  (process.env.STAR_SEARCH_LAB_SERVER &&
    path.join(process.env.STAR_SEARCH_LAB_SERVER, 'source/views/search.json'));
if (!historical) throw Error('pinned historical search.json required');
const designs = [['historical', historical]];
if (process.env.STAR_SEARCH_ORG_MERGED_DESIGN) {
  designs.push(['merged', process.env.STAR_SEARCH_ORG_MERGED_DESIGN]);
}
function sourceFor(file, generation) {
  const bytes = fs.readFileSync(file);
  const blob = crypto.createHash('sha1')
    .update(Buffer.from('blob ' + bytes.length + '\0')).update(bytes).digest('hex');
  assert.equal(blob, PINNED[generation], generation + ': unexpected search design');
  const design = JSON.parse(bytes.toString('utf8'));
  assert.equal(design._id, '_design/search');
  return design.indexes.fts.index;
}
function capture(source, doc) {
  const emitted = [];
  const context = vm.createContext({index(field, value, options) {
    emitted.push({field, value, stored: options?.store === true});
  }});
  context.fn = new vm.Script('(' + source + ')').runInContext(context, {timeout: 1000});
  context.doc = structuredClone(doc);
  new vm.Script('fn(doc)').runInContext(context, {timeout: 1000});
  return emitted;
}
function values(emissions, field) {
  return emissions.filter(e => e.field === field).map(e => e.value);
}
const org = Object.freeze({
  id: 'starintel:org:fictional-educational-cooperative',
  rev: 'r1', dtype: 'org', schemaVersion: '0.10.1',
  dataset: 'book-synthetic', name: 'Fictional Educational Cooperative',
  legalName: 'Fictional Cooperative, Inc.',
  organizationType: 'nonprofit',
});
// Canonical StarLang 0.10.1 generated schema at
// 96d26c338078676ec1dc6928755901636c9f7ef0, Git blob
// 537163da436f67a973e280d1704e32bdba5b888b, defines
// Org.organizationType as string and does not define orgType/org_type.
// These synthetic values are NOT SDK-validated by this test.
for (const [generation, file] of designs) {
  const source = sourceFor(file, generation);
  test(generation + ': canonical organizationType mutation is absent from raw emissions', () => {
    const before = capture(source, org);
    const after = capture(source, {...org, organizationType: 'cooperative'});
    assert.deepEqual(before, after);
    assert.deepEqual(values(before, 'organizationType'), []);
    assert.deepEqual(values(before, 'dataset'), ['book-synthetic']);
    assert.deepEqual(values(before, 'dtype'), ['org']);
    assert.ok(before.every(e => e.stored));
  });
  test(generation + ': nested data.organizationType does not change FTS emissions', () => {
    const before = capture(source, {...org, data: {organizationType: 'nonprofit'}});
    const after = capture(source, {...org, data: {organizationType: 'cooperative'}});
    assert.deepEqual(before, after);
  });
  test(generation + ': indexed organization name remains a positive control', () => {
    const before = capture(source, org);
    const changed = capture(source, {...org, name: 'Another Fictional Cooperative'});
    assert.notDeepEqual(before, changed);
    assert.deepEqual(values(before, 'name'), ['Fictional Educational Cooperative']);
  });
  test(generation + ': migration aliases are not canonical organizationType', () => {
    const specimen = {...org, org_type: 'historical-alias', orgType: 'merged-alias'};
    const events = capture(source, specimen);
    assert.deepEqual(values(events, 'org_type'), ['historical-alias']);
    assert.deepEqual(values(events, 'orgType'), generation === 'merged' ? ['merged-alias'] : []);
    assert.deepEqual(values(events, 'organizationType'), []);
  });
  test(generation + ': mutated index exposes the missing organizationType distinction', () => {
    const anchor = "add('dtype',doc.dtype);";
    assert.equal(source.split(anchor).length, 2, 'original callback changed');
    const mutant = source.replace(anchor, anchor + "add('organizationType',doc.organizationType);");
    assert.notDeepEqual(capture(mutant, org),
      capture(mutant, {...org, organizationType: 'cooperative'}));
  });
}
