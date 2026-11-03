'use strict';
// Chapter 15: canonical document version and historical FTS evidence differ.
// This executes the pinned original index callback, not CouchDB/Clouseau.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const server = process.env.STAR_SEARCH_LAB_SERVER;
assert.ok(server, 'STAR_SEARCH_LAB_SERVER must name the pinned historical server');
const source = path.join(server, 'source', 'views', 'search.json');
const bytes = fs.readFileSync(source);
const blob = crypto.createHash('sha1')
  .update(Buffer.from('blob '+bytes.length+'\0')).update(bytes).digest('hex');
const EXPECTED = '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a';
const design = JSON.parse(bytes.toString('utf8'));
const indexSource = design.indexes.fts.index;
const root = Object.freeze({
  id: 'org:version-teaching', dtype: 'org', dataset: 'book-synthetic',
  name: 'Version Example Cooperative', schemaVersion: '0.9.0',
  collector: 'book-example'
});
function emit(doc, sourceText=indexSource) {
  const emissions = [];
  const sandbox = vm.createContext({index(field, value, options) {
    emissions.push({field, value, store: options?.store === true});
  }});
  sandbox.document = structuredClone(doc);
  const fn = new vm.Script('('+sourceText+')').runInContext(sandbox, {timeout:1000});
  sandbox.indexer = fn;
  new vm.Script('indexer(document)').runInContext(sandbox, {timeout:1000});
  return emissions;
}
const fields = rows => rows.map(({field})=>field);

test('historical Git blob attestation', () => {
  assert.equal(blob, EXPECTED);
  assert.equal(design._id, '_design/search');
});
test('original index emits dataset, dtype and name but not schemaVersion', () => {
  const rows = emit(root);
  for(const key of ['dataset','dtype','name','tenant_id'])
    assert.ok(fields(rows).includes(key), key+' positive control missing');
  assert.ok(!fields(rows).includes('schemaVersion'));
  assert.ok(rows.every(r=>r.store === true));
});
test('version-only mutation is invisible in actual ordered FTS emissions', () => {
  assert.deepEqual(emit(root),emit({...root,schemaVersion:'0.10.1'}));
});
test('dataset change is visible to the very same index capture', () => {
  assert.notDeepEqual(emit(root),emit({...root,dataset:'book-other-public'}));
});
test('name change is visible to the very same index capture', () => {
  assert.notDeepEqual(emit(root),emit({...root,name:'Different Cooperative'}));
});
test('negative control detects an altered index that emits schemaVersion', () => {
  const mutant = indexSource.replace("add('dataset',doc.dataset);", "add('dataset',doc.dataset);add('schemaVersion',doc.schemaVersion);");
  assert.notEqual(mutant,indexSource,'mutation anchor missing');
  assert.notDeepEqual(emit(root,mutant),emit({...root,schemaVersion:'0.10.1'},mutant));
});
