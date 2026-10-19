'use strict';
// BK13: raw FTS callback input-shape behavior; never a canonical admission test.
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
const historical = process.env.STAR_SEARCH_SHAPE_HISTORICAL_DESIGN ||
  (process.env.STAR_SEARCH_LAB_SERVER &&
   path.join(process.env.STAR_SEARCH_LAB_SERVER, 'source/views/search.json'));
if (!historical) throw new Error('pinned historical FTS design path is required');
const designs = [['historical', historical]];
if (process.env.STAR_SEARCH_SHAPE_MERGED_DESIGN) {
  designs.push(['merged', process.env.STAR_SEARCH_SHAPE_MERGED_DESIGN]);
}
function load(file, generation) {
  const bytes = fs.readFileSync(file);
  const blob = crypto.createHash('sha1')
    .update(Buffer.from('blob ' + bytes.length + '\0')).update(bytes).digest('hex');
  assert.equal(blob, PINS[generation], generation + ': source Git blob mismatch');
  const design = JSON.parse(bytes.toString('utf8'));
  assert.equal(design._id, '_design/search');
  assert.equal(design.indexes.fts.analyzer.fields.content, 'standard');
  return design.indexes.fts.index;
}
function capture(callback, record) {
  const emissions = [];
  const scope = vm.createContext({index(field, value, options) {
    emissions.push({field, value, stored: options?.store === true});
  }});
  scope.callback = new vm.Script('(' + callback + ')').runInContext(scope, {timeout: 1000});
  scope.record = structuredClone(record);
  new vm.Script('callback(record)').runInContext(scope, {timeout: 1000});
  return emissions;
}
function values(emissions, field) {
  return emissions.filter(event => event.field === field).map(event => event.value);
}
// The pinned canonical 0.10.1 SocialMediaPost schema defines content:string.
// Array/object content in these probes is INTENTIONALLY NOT a canonical record.
const specimen = Object.freeze({
  id: 'starintel:social-media-post:fictional-shape', rev: 'r1',
  dtype: 'social-media-post', dataset: 'book-synthetic',
  schemaVersion: '0.10.1', content: 'synthetic alpha',
});
for (const [generation, file] of designs) {
  const callback = load(file, generation);
  const baseline = capture(callback, specimen);

  test(generation + ': canonical-shaped string content emits one stored value', () => {
    assert.deepEqual(values(baseline, 'content'), ['synthetic alpha']);
    assert.deepEqual(values(baseline, 'dataset'), ['book-synthetic']);
    assert.deepEqual(values(baseline, 'dtype'), ['social-media-post']);
    assert.deepEqual(values(baseline, 'tenant_id'), ['default']);
    assert.ok(baseline.every(event => event.stored));
  });
  test(generation + ': invalid array content emits individual strings, not a validation error', () => {
    const captured = capture(callback, {...specimen, content: ['alpha', 'beta']});
    assert.deepEqual(values(captured, 'content'), ['alpha', 'beta']);
    assert.deepEqual(values(captured, 'dataset'), ['book-synthetic']);
  });
  test(generation + ': invalid nested arrays flatten recursively in original order', () => {
    const captured = capture(callback, {...specimen, content: [['alpha'], ['beta', ['gamma']]]});
    assert.deepEqual(values(captured, 'content'), ['alpha', 'beta', 'gamma']);
  });
  test(generation + ': invalid object content is not traversed or stringified', () => {
    const captured = capture(callback, {...specimen, content: {text: 'not-a-token'}});
    assert.deepEqual(values(captured, 'content'), []);
    assert.deepEqual(values(captured, 'dtype'), ['social-media-post']);
  });
  test(generation + ': invalid mixed array skips nested object and null', () => {
    const captured = capture(callback, {...specimen,
      content: ['alpha', {text: 'not-a-token'}, null, ['beta']]});
    assert.deepEqual(values(captured, 'content'), ['alpha', 'beta']);
  });
  test(generation + ': null and absent content both omit the raw field', () => {
    const absent = {...specimen};
    delete absent.content;
    assert.deepEqual(values(capture(callback, {...specimen, content: null}), 'content'), []);
    assert.deepEqual(values(capture(callback, absent), 'content'), []);
  });
  test(generation + ': empty string emits a raw value; query tokenization is untested', () => {
    assert.deepEqual(values(capture(callback, {...specimen, content: ''}), 'content'), ['']);
  });
  test(generation + ': object-stringification mutant is caught by the control', () => {
    const original = capture(callback, {...specimen, content: {text: 'not-a-token'}});
    const target = "if(typeof value==='string'||typeof value==='number'||typeof value==='boolean'){";
    assert.equal(callback.split(target).length, 2, 'upstream index callback shape changed');
    const mutant = callback.replace(target,
      "if(value&&typeof value==='object'){index(name,JSON.stringify(value),{'store':true});return;}" + target);
    const changed = capture(mutant, {...specimen, content: {text: 'not-a-token'}});
    assert.deepEqual(values(original, 'content'), []);
    assert.deepEqual(values(changed, 'content'), ['{"text":"not-a-token"}']);
  });
}
