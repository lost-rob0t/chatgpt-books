'use strict';

// TESTED: original source index() emissions, not Clouseau tokenization or SDK validation.
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

function gitBlobSha(bytes) {
  return crypto.createHash('sha1')
    .update(Buffer.from(`blob ${bytes.length}\0`))
    .update(bytes)
    .digest('hex');
}

function loadIndex(file, generation) {
  const bytes = fs.readFileSync(file);
  assert.equal(gitBlobSha(bytes), PINS[generation],
    `${generation}: original server search design Git blob changed`);
  const design = JSON.parse(bytes.toString('utf8'));
  assert.equal(design._id, '_design/search');
  assert.equal(typeof design.indexes.fts.index, 'string');
  return design.indexes.fts.index;
}

function capture(source, document) {
  const emissions = [];
  const context = vm.createContext({index: (field, value, options) => {
    emissions.push({field, value, stored: options?.store === true});
  }});
  context.document = structuredClone(document);
  context.indexer = new vm.Script(`(${source})`).runInContext(context, {timeout: 1000});
  new vm.Script('indexer(document)').runInContext(context, {timeout: 1000});
  return emissions;
}

function sample(dtype, payload) {
  return {
    id: `starintel:synthetic:${dtype}:coverage`,
    rev: 'synthetic-r1',
    schemaVersion: '0.10.1',
    dataset: 'book-synthetic',
    dtype,
    ...payload,
  };
}

function valuesFor(emissions, field) {
  return emissions.filter(row => row.field === field).map(row => row.value);
}

// Confirmed fields on the canonical 0.10.1 generated schema at StarLang
// 96d26c338078676ec1dc6928755901636c9f7ef0, blob
// 537163da436f67a973e280d1704e32bdba5b888b.
// This fixture is shape-based; it does not run the canonical SDK validator.
const nonIndexedText = [
  {type: 'Message', dtype: 'message', key: 'message'},
  {type: 'EmailMessage', dtype: 'email-message', key: 'body'},
  {type: 'Transcript', dtype: 'transcript', key: 'text'},
  {type: 'Policy', dtype: 'policy', key: 'text'},
];

const historicalPath = process.env.STAR_SEARCH_TEXT_HISTORICAL_DESIGN
  || (process.env.STAR_SEARCH_LAB_SERVER && path.join(
    process.env.STAR_SEARCH_LAB_SERVER, 'source/views/search.json'));
if (!historicalPath) {
  throw new Error('set STAR_SEARCH_LAB_SERVER to the pinned historical checkout');
}
const inputs = [{generation: 'historical', file: historicalPath}];
if (process.env.STAR_SEARCH_TEXT_MERGED_DESIGN) {
  inputs.push({generation: 'merged', file: process.env.STAR_SEARCH_TEXT_MERGED_DESIGN});
}

for (const {generation, file} of inputs) {
  const source = loadIndex(file, generation);
  test(`${generation}: original index source is Git-blob-attested`, () => {
    assert.ok(source.startsWith('function(doc)'));
    assert.ok(source.includes('index(name,value'));
  });

  for (const {type, dtype, key} of nonIndexedText) {
    test(`${generation}: canonical ${type}.${key} is not a raw FTS emission`, () => {
      const a = capture(source, sample(dtype, {[key]: 'fictional-alpha'}));
      const b = capture(source, sample(dtype, {[key]: 'fictional-beta'}));
      assert.deepEqual(a, b, `${type}.${key} unexpectedly changes index emissions`);
      assert.deepEqual(valuesFor(a, key), []);
      assert.deepEqual(valuesFor(a, 'dataset'), ['book-synthetic']);
      assert.deepEqual(valuesFor(a, 'dtype'), [dtype]);
      assert.deepEqual(valuesFor(a, 'tenant_id'), ['default']);
      assert.ok(a.every(row => row.stored));
    });
  }

  test(`${generation}: SocialMediaPost.content changes raw FTS emissions`, () => {
    const a = capture(source, sample('social-media-post', {content: 'fictional-alpha'}));
    const b = capture(source, sample('social-media-post', {content: 'fictional-beta'}));
    assert.deepEqual(valuesFor(a, 'content'), ['fictional-alpha']);
    assert.deepEqual(valuesFor(b, 'content'), ['fictional-beta']);
    assert.notDeepEqual(a, b);
  });

  test(`${generation}: Policy.name remains a positive control`, () => {
    const a = capture(source, sample('policy', {name: 'Fictional Policy Alpha'}));
    const b = capture(source, sample('policy', {name: 'Fictional Policy Beta'}));
    assert.deepEqual(valuesFor(a, 'name'), ['Fictional Policy Alpha']);
    assert.deepEqual(valuesFor(b, 'name'), ['Fictional Policy Beta']);
    assert.notDeepEqual(a, b);
  });

  test(`${generation}: indexed content does not certify omitted text fields`, () => {
    const doc = sample('message', {message: 'fictional-hidden', content: 'fictional-visible'});
    const emitted = capture(source, doc);
    assert.deepEqual(valuesFor(emitted, 'content'), ['fictional-visible']);
    assert.deepEqual(valuesFor(emitted, 'message'), []);
  });
}


// Canonical Unicode equivalence is a string-level fact, not evidence that
// the raw FTS callback, Lucene analyzer, and authorized query are equivalent.
// Person.fname and Person.notes are strings in the pinned StarLang 0.10.1 schema.
for (const {generation, file} of inputs) {
  const source = loadIndex(file, generation);
  const equivalents = [
    ['acute', 'Caf\u00e9', 'Cafe\u0301'],
    ['ring', '\u00c5sa', 'A\u030asa'],
  ];
  for (const [label, composed, decomposed] of equivalents) {
    test(generation + ': ' + label + ' canonical-equivalent text has distinct raw fname emissions', () => {
      assert.notEqual(composed, decomposed);
      assert.equal(composed.normalize('NFC'), decomposed.normalize('NFC'));
      const left = capture(source, sample('person', {fname: composed}));
      const right = capture(source, sample('person', {fname: decomposed}));
      assert.deepEqual(valuesFor(left, 'fname'), [composed]);
      assert.deepEqual(valuesFor(right, 'fname'), [decomposed]);
      assert.notDeepEqual(left, right);
      for (const key of ['tenant_id', 'dataset', 'dtype']) {
        assert.deepEqual(valuesFor(left, key), valuesFor(right, key));
      }
      assert.ok(left.every(row => row.stored));
    });
  }
  test(generation + ': the keyword name analyzer declaration is not a Lucene test', () => {
    const design = JSON.parse(fs.readFileSync(file, 'utf8'));
    assert.equal(design.indexes.fts.analyzer.name, 'perfield');
    assert.equal(design.indexes.fts.analyzer.default, 'standard');
    assert.equal(design.indexes.fts.analyzer.fields.name, 'keyword');
    const a = capture(source, sample('person', {name: 'Caf\u00e9'}));
    const b = capture(source, sample('person', {name: 'Cafe\u0301'}));
    assert.deepEqual(valuesFor(a, 'name'), ['Caf\u00e9']);
    assert.deepEqual(valuesFor(b, 'name'), ['Cafe\u0301']);
    assert.notDeepEqual(a, b);
  });
  test(generation + ': raw index carries neither canonical identity nor revision', () => {
    const a = sample('person', {fname: 'Caf\u00e9'});
    const b = sample('person', {fname: 'Cafe\u0301'});
    assert.equal(a.id, b.id);
    assert.equal(a.rev, b.rev);
    assert.deepEqual(valuesFor(capture(source, a), 'id'), []);
    assert.deepEqual(valuesFor(capture(source, a), 'rev'), []);
    assert.notDeepEqual(capture(source, a), capture(source, b));
  });
  test(generation + ': omitted canonical notes are independent of indexed fname', () => {
    const a = capture(source, sample('person', {fname: 'Fictional', notes: 'Caf\u00e9'}));
    const b = capture(source, sample('person', {fname: 'Fictional', notes: 'Cafe\u0301'}));
    assert.deepEqual(a, b);
    assert.deepEqual(valuesFor(a, 'notes'), []);
    assert.notDeepEqual(a, capture(source, sample('person', {fname: 'Different'})));
  });
}
