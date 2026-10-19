'use strict';
// Chapter 15: a Product result is not a software-bill-of-materials or support verdict.
// Executes exact, pinned historical and merged server FTS callbacks, not a replica.
// Fictional canonical-shaped Product values are NOT SDK-validated or persisted.
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
// Fields are declared in the StarLang org.starintel/core@1 0.10.1 Product
// definition, generated/schema.json Git blob 537163da436f67a973e280d1704e32bdba5b888b.
const PRODUCT = Object.freeze({
  id: 'starintel:product:fictional-library',
  rev: 'r1',
  dtype: 'product',
  dataset: 'fictional-software-catalog',
  schemaVersion: '0.10.1',
  name: 'Fictional Parser Toolkit',
  displayName: 'Fictional Parser Toolkit Community Edition',
  productType: 'software',
  versionName: '1.0.0',
  license: 'Fictional-Only',
  sbomFileIds: ['starintel:file:fictional-sbom-1'],
  dependencyIds: ['starintel:product:fictional-dependency-1'],
  securityAdvisoryIds: ['starintel:document:fictional-advisory-1'],
  supportEndAt: '2027-01-01T00:00:00Z',
  endOfLife: null,
  status: 'supported',
});
const ALTERNATE = Object.freeze({...PRODUCT,
  versionName: '2.0.0',
  license: 'Another-Fictional-License',
  sbomFileIds: ['starintel:file:fictional-sbom-2'],
  dependencyIds: ['starintel:product:fictional-dependency-2'],
  securityAdvisoryIds: [],
  supportEndAt: '2026-04-01T00:00:00Z',
  endOfLife: '2026-04-01T00:00:00Z',
  status: 'unsupported',
});
const COVERAGE_GAPS = Object.freeze([
  'productType', 'versionName', 'license', 'sbomFileIds',
  'dependencyIds', 'securityAdvisoryIds', 'supportEndAt',
  'endOfLife', 'status',
]);

const historical = process.env.STAR_SEARCH_PRODUCT_HISTORICAL_DESIGN ||
  (process.env.STAR_SEARCH_LAB_SERVER && path.join(
    process.env.STAR_SEARCH_LAB_SERVER, 'source/views/search.json'));
if (!historical) throw new Error('historical pinned Server search.json required');
const sources = [['historical', historical]];
if (process.env.STAR_SEARCH_PRODUCT_MERGED_DESIGN)
  sources.push(['merged', process.env.STAR_SEARCH_PRODUCT_MERGED_DESIGN]);

function readPinnedSource(file, generation) {
  const bytes = fs.readFileSync(file);
  const sha = crypto.createHash('sha1')
    .update(Buffer.from(`blob ${bytes.length}\0`)).update(bytes).digest('hex');
  assert.equal(sha, PINS[generation], `${generation}: unexpected Server Git blob`);
  const design = JSON.parse(bytes.toString('utf8'));
  assert.equal(design._id, '_design/search');
  assert.equal(design.indexes.fts.analyzer.fields.dataset, 'keyword');
  assert.equal(design.indexes.fts.analyzer.fields.tenant_id, 'keyword');
  return design.indexes.fts.index;
}
function capture(source, product) {
  const rows = [];
  const context = {doc: structuredClone(product), index(field, value, options) {
    assert.equal(options?.store, true);
    assert.equal(typeof field, 'string');
    assert.ok(['string', 'number', 'boolean'].includes(typeof value));
    if (rows.length >= 2048) throw new Error('bounded source execution exceeded');
    rows.push([field, value]);
  }};
  vm.runInNewContext('(' + source + ')(doc)', context, {timeout: 1000});
  return rows;
}
const fieldValues = (rows, field) => rows.filter(row => row[0] === field)
  .map(row => row[1]);
function mutant(source) {
  const anchor = "add('title',doc.title);";
  assert.equal(source.split(anchor).length, 2, 'pinned mutation anchor changed');
  return source.replace(anchor, anchor + "add('sbomFileIds',doc.sbomFileIds);");
}

for (const [generation, file] of sources) {
  const source = readPinnedSource(file, generation);
  const baseline = capture(source, PRODUCT);
  test(`${generation}: name and server-index scope fields are emitted`, () => {
    assert.deepEqual(fieldValues(baseline, 'name'), [PRODUCT.name]);
    assert.deepEqual(fieldValues(baseline, 'dtype'), ['product']);
    assert.deepEqual(fieldValues(baseline, 'dataset'), [PRODUCT.dataset]);
    assert.deepEqual(fieldValues(baseline, 'tenant_id'), ['default']);
  });
  test(`${generation}: displayName follows its exact source-generation projection`, () => {
    assert.deepEqual(fieldValues(baseline, 'displayName'),
      generation === 'merged' ? [PRODUCT.displayName] : []);
    const variant = capture(source, {...PRODUCT, displayName: 'Rebranded fictional edition'});
    if (generation === 'merged') assert.notDeepEqual(variant, baseline);
    else assert.deepEqual(variant, baseline);
  });
  test(`${generation}: dependency, SBOM, advisory, support claims do not change raw FTS`, () => {
    assert.deepEqual(capture(source, ALTERNATE), baseline);
    for (const field of COVERAGE_GAPS) assert.deepEqual(fieldValues(baseline, field), []);
  });
  test(`${generation}: an empty SBOM reference set cannot be diagnosed from an index row`, () => {
    assert.deepEqual(capture(source, {...PRODUCT,
      sbomFileIds: [], dependencyIds: [], securityAdvisoryIds: []}), baseline);
  });
  test(`${generation}: name is an indexed positive control`, () => {
    const changed = capture(source, {...PRODUCT, name: 'Other fictional toolkit'});
    assert.notDeepEqual(changed, baseline);
    assert.deepEqual(fieldValues(changed, 'name'), ['Other fictional toolkit']);
  });
  test(`${generation}: dataset emission is not a caller's authorization grant`, () => {
    const changed = capture(source, {...PRODUCT, dataset: 'fictional-other-catalog'});
    assert.notDeepEqual(changed, baseline);
    assert.deepEqual(fieldValues(changed, 'dataset'), ['fictional-other-catalog']);
  });
  test(`${generation}: tenant stamp affects scope emission, not supply-chain contents`, () => {
    const changed = capture(source, {...PRODUCT, tenant_id: 'fictional-other-tenant'});
    assert.notDeepEqual(changed, baseline);
    assert.deepEqual(fieldValues(changed, 'tenant_id'), ['fictional-other-tenant']);
    assert.deepEqual(fieldValues(changed, 'securityAdvisoryIds'), []);
  });
  test(`${generation}: missing name is not repaired by unrelated version metadata`, () => {
    const unnamed = {...PRODUCT};
    delete unnamed.name;
    const projection = capture(source, unnamed);
    assert.deepEqual(fieldValues(projection, 'name'), []);
    assert.deepEqual(fieldValues(projection, 'versionName'), []);
    assert.deepEqual(fieldValues(projection, 'displayName'),
      generation === 'merged' ? [PRODUCT.displayName] : []);
  });
  test(`${generation}: deliberately modified FTS callback triggers a falsifiable RED control`, () => {
    const altered = mutant(source);
    const result = capture(altered, PRODUCT);
    assert.deepEqual(fieldValues(result, 'sbomFileIds'), PRODUCT.sbomFileIds);
    assert.notDeepEqual(result, baseline);
    if (process.env.STAR_SEARCH_PRODUCT_RED === '1')
      assert.deepEqual(result, baseline, 'intentional RED: changed source emits SBOM reference');
  });
}
