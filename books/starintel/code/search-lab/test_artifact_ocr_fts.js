'use strict';
// Original pinned Server index functions only; no SDK, HTTP, or Lucene execution.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const historical = process.env.STAR_SEARCH_ARTIFACT_HISTORICAL_DESIGN ||
  (process.env.STAR_SEARCH_LAB_SERVER && path.join(
    process.env.STAR_SEARCH_LAB_SERVER, 'source/views/search.json'));
assert.ok(historical, 'provide a pinned historical Server checkout');
const sources = [['historical', historical,
  '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a']];
if (process.env.STAR_SEARCH_ARTIFACT_MERGED_DESIGN) {
  sources.push(['merged', process.env.STAR_SEARCH_ARTIFACT_MERGED_DESIGN,
    'dd6336f3047982db2f0e3615fed1413ed1e58e13']);
}

function readPinned(file, pin) {
  const raw = fs.readFileSync(file);
  const digest = crypto.createHash('sha1').update(
    Buffer.from('blob ' + raw.length + '\0')).update(raw).digest('hex');
  assert.equal(digest, pin, 'unpinned source design');
  const fts = JSON.parse(raw.toString('utf8')).indexes.fts;
  assert.equal(fts.analyzer.fields.name, 'keyword');
  assert.equal(fts.analyzer.fields.dataset, 'keyword');
  return fts.index;
}

function capture(indexSource, doc) {
  const emissions = [];
  const scope = { doc: structuredClone(doc), index(name, value, options) {
    assert.equal(options.store, true);
    emissions.push([name, value]);
  }};
  vm.runInNewContext('(' + indexSource + ')(doc)', scope, { timeout: 1000 });
  return emissions;
}

function artifact(overrides = {}) {
  // Fictional canonical-shaped Artifact. Does not claim SDK admission.
  return { id: 'art:fictional-demo', dataset: 'book-public', dtype: 'artifact',
    schemaVersion: '0.10.1', name: 'Example scan', filename: 'example.pdf',
    ocrText: 'FICTIONAL OCR ALPHA', extractedText: 'FICTIONAL TEXT BETA',
    rawContent: 'FICTIONAL RAW GAMMA', mediaType: 'application/pdf',
    contentHash: 'not-a-real-digest', sizeBytes: 123, ...overrides };
}

for (const [generation, file, pin] of sources) {
  const indexSource = readPinned(file, pin);
  test(generation + ': Artifact OCR, extraction, filename are not indexed', () => {
    const output = capture(indexSource, artifact());
    assert.deepEqual(output, [['tenant_id', 'default'],
      ['dataset', 'book-public'], ['dtype', 'artifact'], ['name', 'Example scan']]);
    for (const field of ['filename', 'ocrText', 'extractedText', 'rawContent',
      'mediaType', 'contentHash', 'sizeBytes']) {
      assert.equal(output.some(([key]) => key === field), false);
    }
  });
  test(generation + ': OCR changes do not alter raw index emissions', () => {
    assert.deepEqual(capture(indexSource, artifact()), capture(indexSource,
      artifact({ocrText: 'ANOTHER OCR', extractedText: 'ANOTHER EXTRACTION',
        rawContent: 'ANOTHER RAW VALUE'})));
  });
  test(generation + ': filename alone cannot stand in for indexed name', () => {
    assert.deepEqual(capture(indexSource, artifact({name: undefined})),
      [['tenant_id', 'default'], ['dataset', 'book-public'], ['dtype', 'artifact']]);
  });
  test(generation + ': indexed name and dataset changes are positive controls', () => {
    const before = capture(indexSource, artifact());
    assert.notDeepEqual(before, capture(indexSource,
      artifact({name: 'Changed scan'})));
    assert.notDeepEqual(before, capture(indexSource,
      artifact({dataset: 'book-private'})));
  });
  test(generation + ': unvalidated content alias is not canonical OCR', () => {
    const output = capture(indexSource,
      artifact({content: 'UNVALIDATED ALIAS'}));
    assert.ok(output.some(([name, value]) =>
      name === 'content' && value === 'UNVALIDATED ALIAS'));
    assert.equal(output.some(([name]) => name === 'ocrText'), false);
  });
}
