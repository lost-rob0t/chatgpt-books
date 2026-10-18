'use strict';
// Chapter 15: a File name hit does not attest bytes, safety or storage.
// Only the original historical/merged Server JavaScript index callbacks execute.
// Fictional values are canonical-shaped, NOT SDK-admitted or persisted.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const PINS = Object.freeze({
  historical: '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged: 'dd6336f3047982db2f0e3615fed1413ed1e58e13',
});
const historical = process.env.STAR_SEARCH_FILE_HISTORICAL_DESIGN ||
  (process.env.STAR_SEARCH_LAB_SERVER && path.join(
    process.env.STAR_SEARCH_LAB_SERVER, 'source/views/search.json'));
if (!historical) throw new Error('pinned historical Server search design required');
const sources = [['historical', historical]];
if (process.env.STAR_SEARCH_FILE_MERGED_DESIGN) {
  sources.push(['merged', process.env.STAR_SEARCH_FILE_MERGED_DESIGN]);
}

function readPinned(file, generation) {
  const bytes = fs.readFileSync(file);
  const sha = crypto.createHash('sha1').update(
    Buffer.from(`blob ${bytes.length}\0`)).update(bytes).digest('hex');
  assert.equal(sha, PINS[generation], `unpinned ${generation} design source`);
  const design = JSON.parse(bytes.toString('utf8'));
  assert.equal(design._id, '_design/search');
  assert.equal(typeof design.indexes?.fts?.index, 'string');
  return design.indexes.fts.index;
}
function emissions(source, document) {
  const rows = [];
  const sandbox = {doc: structuredClone(document), index(field, value, options) {
    assert.equal(options?.store, true);
    assert.equal(typeof field, 'string');
    assert.ok(['string', 'number', 'boolean'].includes(typeof value));
    if (rows.length >= 2048) throw new Error('course emission budget exceeded');
    rows.push([field, value]);
  }};
  vm.runInNewContext('(' + source + ')(doc)', sandbox, {timeout: 1000});
  return rows;
}

// StarLang org.starintel/core@1 version 0.10.1 File requires
// id, dataset, dtype, schemaVersion, bytesHash, bytesHashAlgorithm.
// Other named fields below are declared for File in the same generated schema.
const FILE = Object.freeze({
  id: 'file:fictional:lab-001',
  dataset: 'book-synthetic',
  dtype: 'file',
  schemaVersion: '0.10.1',
  name: 'Fictional Evidence Package',
  filename: 'fictional-package.zip',
  bytesHash: 'a'.repeat(64),
  bytesHashAlgorithm: 'sha256',
  storageUri: 'https://assets.example.invalid/files/package-001',
  path: '/virtual/fictional-package.zip',
  quarantined: true,
  executable: false,
  passwordProtected: false,
  encrypted: false,
  parseStatus: 'pending',
  mediaType: 'application/zip',
  archiveEntries: [{id: 'file:fictional:child-001'}],
});
const changed = Object.freeze({
  ...FILE,
  filename: 'changed-package.zip',
  bytesHash: 'b'.repeat(64),
  bytesHashAlgorithm: 'sha512',
  storageUri: 'https://assets.example.invalid/files/package-002',
  path: '/virtual/changed-package.zip',
  quarantined: false,
  executable: true,
  passwordProtected: true,
  encrypted: true,
  parseStatus: 'failed',
  mediaType: 'application/octet-stream',
  archiveEntries: [{id: 'file:fictional:child-002'}],
});
const unindexed = new Set([
  'filename', 'bytesHash', 'bytesHashAlgorithm', 'storageUri', 'path',
  'quarantined', 'executable', 'passwordProtected', 'encrypted',
  'parseStatus', 'mediaType', 'archiveEntries',
]);
function fieldValues(rows, field) {
  return rows.filter(row => row[0] === field).map(row => row[1]);
}
function mutant(indexSource) {
  const anchor = "add('title',doc.title);";
  assert.equal(indexSource.split(anchor).length, 2, 'source anchor changed');
  return indexSource.replace(anchor, anchor + "add('bytesHash',doc.bytesHash);");
}

for (const [generation, file] of sources) {
  const original = readPinned(file, generation);
  const callback = process.env.STAR_SEARCH_FILE_MUTANT === '1'
    ? mutant(original) : original;
  const baseline = emissions(callback, FILE);
  test(`${generation}: exact source Git blob and stable index anchor`, () => {
    assert.ok(original.includes("add('title',doc.title);"));
    assert.equal(typeof PINS[generation], 'string');
  });
  test(`${generation}: File fixture declares required schema keys`, () => {
    for (const key of ['id', 'dataset', 'dtype', 'schemaVersion',
      'bytesHash', 'bytesHashAlgorithm']) assert.ok(Object.hasOwn(FILE, key));
    assert.equal(FILE.schemaVersion, '0.10.1');
    assert.equal(FILE.bytesHashAlgorithm, 'sha256');
  });
  test(`${generation}: raw index contains scope, type, name only`, () => {
    assert.deepEqual(baseline, [
      ['tenant_id', 'default'],
      ['dataset', 'book-synthetic'],
      ['dtype', 'file'],
      ['name', 'Fictional Evidence Package'],
    ]);
  });
  test(`${generation}: changing storage, hash, quarantine and parse claims is FTS-invisible`, () => {
    assert.deepEqual(emissions(callback, changed), baseline);
  });
  test(`${generation}: no file bytes/safety fields emitted`, () => {
    for (const row of baseline) assert.equal(unindexed.has(row[0]), false, row[0]);
  });
  test(`${generation}: filename alone does not supply an indexed name`, () => {
    const unnamed = {...FILE};
    delete unnamed.name;
    assert.deepEqual(emissions(callback, unnamed), [
      ['tenant_id', 'default'], ['dataset', 'book-synthetic'], ['dtype', 'file'],
    ]);
  });
  test(`${generation}: changing indexed name changes raw emissions`, () => {
    const after = emissions(callback, {...FILE, name: 'Alternative fictional label'});
    assert.notDeepEqual(after, baseline);
    assert.deepEqual(fieldValues(after, 'name'), ['Alternative fictional label']);
  });
  test(`${generation}: changing dataset changes a scope emission, not authorization`, () => {
    const after = emissions(callback, {...FILE, dataset: 'another-synthetic-dataset'});
    assert.notDeepEqual(after, baseline);
    assert.deepEqual(fieldValues(after, 'dataset'), ['another-synthetic-dataset']);
  });
  test(`${generation}: deliberately altered disposable callback reveals hash-sensitive regression`, () => {
    const altered = mutant(original);
    const first = emissions(altered, FILE);
    const second = emissions(altered, changed);
    assert.notDeepEqual(first, second);
    assert.deepEqual(fieldValues(first, 'bytesHash'), [FILE.bytesHash]);
    assert.deepEqual(fieldValues(second, 'bytesHash'), [changed.bytesHash]);
  });
}
