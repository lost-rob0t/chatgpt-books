'use strict';
// BK13: a declared visibility field is not itself an FTS authorization clause.
// Execute the original pinned StarIntel Server JavaScript callback; NOT Clouseau.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const expectedGitBlob = '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a';
const designFile = process.env.STAR_SEARCH_INDEX_SOURCE ||
  path.join(process.env.STAR_SEARCH_LAB_SERVER || '', 'source/views/search.json');
assert.ok(designFile && fs.existsSync(designFile), 'exact historical source/views/search.json required');
const source = fs.readFileSync(designFile);
const gitBlob = crypto.createHash('sha1')
  .update(Buffer.from(`blob ${source.length}\0`)).update(source).digest('hex');
assert.equal(gitBlob, expectedGitBlob, 'refuse a substituted FTS design');
const fts = JSON.parse(source.toString('utf8')).indexes.fts;
function emit(doc, body=fts.index) {
  const calls = [];
  const context = vm.createContext({index: (field, value, options) => {
    calls.push({field, value, store: options?.store === true});
  }});
  context.fn = new vm.Script(`(${body})`).runInContext(context, {timeout: 1000});
  context.doc = structuredClone(doc);
  new vm.Script('fn(doc)').runInContext(context, {timeout: 1000});
  return calls;
}
function field(events, key) {
  return events.filter(e => e.field === key).map(e => e.value);
}
const specimen = {
  id: 'org:synthetic-visibility', dataset: 'book-public', dtype: 'org',
  schemaVersion: '0.10.1', name: 'Fictional Reading Room',
  content: 'synthetic open house', visibility: 'public',
  accessControl: {classification: 'demo'}
};

test('exact original historical search design is used', () => {
  assert.equal(gitBlob, expectedGitBlob);
  assert.equal(fts.analyzer.fields.dataset, 'keyword');
  assert.equal(fts.analyzer.fields.tenant_id, 'keyword');
});
test('public and private flags do not alter callback emissions at equal dataset and terms', () => {
  const changed = {...specimen, visibility: 'private'};
  assert.notEqual(specimen.visibility, changed.visibility);
  assert.deepEqual(emit(specimen), emit(changed));
});
test('the raw callback does not emit visibility as a stored search field', () => {
  assert.deepEqual(field(emit(specimen), 'visibility'), []);
  assert.deepEqual(field(emit({...specimen, visibility: 'private'}), 'visibility'), []);
});
test('altering record accessControl does not alter raw callback emissions', () => {
  const changed = {...specimen, accessControl: {classification: 'restricted'}};
  assert.deepEqual(emit(specimen), emit(changed));
  assert.deepEqual(field(emit(changed), 'accessControl'), []);
});
test('public dataset scope is a distinct indexed dimension', () => {
  const changed = {...specimen, dataset: 'book-private'};
  assert.notDeepEqual(emit(specimen), emit(changed));
  assert.deepEqual(field(emit(changed), 'dataset'), ['book-private']);
});
test('internal server-stamped tenant dimension changes index evidence', () => {
  const changed = {...specimen, tenant_id: 'other'};
  assert.notDeepEqual(emit(specimen), emit(changed));
  assert.deepEqual(field(emit(changed), 'tenant_id'), ['other']);
});
test('altered searchable text changes callback emissions', () => {
  const changed = {...specimen, content: 'different synthetic open house'};
  assert.notDeepEqual(emit(specimen), emit(changed));
});
test('negative control: a deliberately modified index would distinguish visibility', () => {
  const bad = fts.index.replace("add('dtype',doc.dtype);", "add('dtype',doc.dtype);add('visibility',doc.visibility);");
  assert.notEqual(bad, fts.index);
  assert.notDeepEqual(emit(specimen, bad), emit({...specimen, visibility: 'private'}, bad));
  assert.deepEqual(field(emit({...specimen, visibility: 'private'}, bad), 'visibility'), ['private']);
});
