'use strict';
// Chapter 15: a source-pinned search emission is not WebCapture provenance.
// No HTTP, screenshot read, canonical SDK admission, or live search occurs.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const {readIndex, emissions, PINS} = require('./projection_delta');

const historical = process.env.STAR_SEARCH_WEBCAPTURE_HISTORICAL_DESIGN ||
  (process.env.STAR_SEARCH_LAB_SERVER &&
    path.join(process.env.STAR_SEARCH_LAB_SERVER, 'source/views/search.json'));
if (!historical) throw new Error('pinned historical search design is required');
const sources = [['historical', historical]];
if (process.env.STAR_SEARCH_WEBCAPTURE_MERGED_DESIGN) {
  sources.push(['merged', process.env.STAR_SEARCH_WEBCAPTURE_MERGED_DESIGN]);
}

// Synthetic, reserved example-only URLs and made-up hashes.
// Required fields are from StarLang 0.10.1 WebCapture's generated JSON Schema.
const CAPTURE = Object.freeze({
  id: 'webcapture:fictional:preview-001',
  dataset: 'book-synthetic',
  dtype: 'web-capture',
  schemaVersion: '0.10.1',
  captureId: 'capture-fictional-001',
  url: 'https://lab.example.invalid/page',
  title: 'Fictional captured page',
  screenshotUri: 'https://lab.example.invalid/artifacts/screen-001.png',
  screenshotHash: 'sha256:' + 'a'.repeat(64),
  screenshotMediaType: 'image/png',
  screenshotSizeBytes: 2048,
  capturedAt: '2026-10-01T12:00:00Z',
  domArtifactUri: 'https://lab.example.invalid/artifacts/dom-001.html',
  domArtifactHash: 'sha256:' + 'c'.repeat(64),
  statusCode: 200,
  challengeStatus: 'no-challenge-observed',
});
const changedProvenance = Object.freeze({
  ...CAPTURE,
  captureId: 'capture-fictional-002',
  screenshotUri: 'https://lab.example.invalid/artifacts/screen-002.png',
  screenshotHash: 'sha256:' + 'b'.repeat(64),
  screenshotSizeBytes: 8192,
  capturedAt: '2026-10-02T17:00:00Z',
  domArtifactUri: 'https://lab.example.invalid/artifacts/dom-002.html',
  domArtifactHash: 'sha256:' + 'd'.repeat(64),
  statusCode: 503,
  challengeStatus: 'unresolved-challenge',
});
const capturedFields = new Set([
  'captureId', 'screenshotUri', 'screenshotHash', 'screenshotMediaType',
  'screenshotSizeBytes', 'capturedAt', 'domArtifactUri', 'domArtifactHash',
  'statusCode', 'challengeStatus',
]);
function values(rows, field) {
  return rows.filter(row => row.field === field).map(row => row.value);
}
function mutate(indexSource) {
  const anchor = "add('title',doc.title);";
  assert.equal(indexSource.split(anchor).length, 2, 'expected pin-specific mutation anchor');
  return indexSource.replace(anchor, anchor + "add('screenshotHash',doc.screenshotHash);");
}

for (const [generation, file] of sources) {
  const original = readIndex(file, generation);
  // A deliberate local RED control, never a substitute for the original callback.
  const callback = process.env.STAR_SEARCH_WEBCAPTURE_MUTANT === '1'
    ? mutate(original) : original;
  const baseline = emissions(callback, CAPTURE);
  test(generation + ': byte-attested original source (' + PINS[generation] + ')', () => {
    assert.equal(typeof original, 'string');
    assert.ok(original.includes("add('title',doc.title);"));
  });
  test(generation + ': WebCapture fixture declares required canonical-shaped keys', () => {
    for (const key of ['id', 'dataset', 'dtype', 'schemaVersion',
      'captureId', 'url', 'screenshotUri', 'screenshotHash']) {
      assert.ok(Object.hasOwn(CAPTURE, key), key);
    }
    assert.equal(CAPTURE.schemaVersion, '0.10.1');
    assert.equal(CAPTURE.dataset, 'book-synthetic');
  });
  test(generation + ': raw emitted search fields select URL/title and scope', () => {
    assert.deepEqual(baseline.map(row => row.field),
      ['tenant_id', 'dataset', 'dtype', 'title', 'url']);
    assert.deepEqual(values(baseline, 'url'), [CAPTURE.url]);
    assert.deepEqual(values(baseline, 'title'), [CAPTURE.title]);
    assert.deepEqual(values(baseline, 'tenant_id'), ['default']);
  });
  test(generation + ': changing screenshot and DOM evidence leaves raw search unchanged', () => {
    assert.deepEqual(emissions(callback, changedProvenance), baseline);
  });
  test(generation + ': no capture proof is emitted as an FTS field', () => {
    for (const row of baseline) assert.equal(capturedFields.has(row.field), false);
  });
  test(generation + ': changing the searched URL is an independent positive control', () => {
    const alternate = emissions(callback, {...CAPTURE,
      url: 'https://lab.example.invalid/different-page'});
    assert.notDeepEqual(alternate, baseline);
    assert.deepEqual(values(alternate, 'url'), ['https://lab.example.invalid/different-page']);
  });
  test(generation + ': changing the title is a separate positive control', () => {
    const alternate = emissions(callback, {...CAPTURE,
      title: 'Another fictional title'});
    assert.notDeepEqual(alternate, baseline);
    assert.deepEqual(values(alternate, 'title'), ['Another fictional title']);
  });
  test(generation + ': mutant demonstrates the hash-sensitive detector', () => {
    const attacker = mutate(original);
    const one = emissions(attacker, CAPTURE);
    const two = emissions(attacker, changedProvenance);
    assert.notDeepEqual(one, two);
    assert.deepEqual(values(one, 'screenshotHash'), [CAPTURE.screenshotHash]);
    assert.deepEqual(values(two, 'screenshotHash'), [changedProvenance.screenshotHash]);
  });
}
