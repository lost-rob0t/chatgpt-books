'use strict';
// Execute both exact source-pinned FTS callbacks; no Clouseau or ranking is claimed.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const oldSHA = '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a';
const newSHA = 'dd6336f3047982db2f0e3615fed1413ed1e58e13';
const source = fs.readFileSync(path.join(process.env.STAR_SEARCH_LAB_SERVER || '', 'source/views/search.json'));
const blob = raw => crypto.createHash('sha1').update(Buffer.from('blob ' + raw.length + '\0')).update(raw).digest('hex');
assert.equal(blob(source), oldSHA, 'historical source must be byte-identical');
let merged = source.toString('utf8');
for (const [old, next] of [
  ["'full_name','content'", "'full_name','fullName','content'"],
  ["'display_name','legal_name','group'", "'display_name','displayName','legal_name','legalName','group'"],
  ["'org_type'];", "'org_type','orgType'];"]
]) {
  assert.equal(merged.split(old).length - 1, 1, 'source generation drift');
  merged = merged.replace(old, next);
}
assert.equal(blob(Buffer.from(merged)), newSHA, 'merged source must be byte-identical');
const fts = [JSON.parse(source).indexes.fts, JSON.parse(merged).indexes.fts];
function emit(code, doc) {
  const events = [];
  const context = vm.createContext({index(field, value, options) {
    events.push({field, value, stored: options.store === true});
  }});
  context.fn = new vm.Script('(' + code + ')').runInContext(context, {timeout: 1000});
  context.doc = structuredClone(doc);
  new vm.Script('fn(doc)').runInContext(context, {timeout: 1000});
  return events;
}
const a = {id: 'org:synthetic-confidence', dataset: 'book-public', dtype: 'org',
  name: 'Fictional Reading Room', content: 'synthetic evidence',
  confidence: '0.25', verificationStatus: 'unreviewed'};
const b = {...a, confidence: '0.95', verificationStatus: 'verified'};
test('both historical and merged Git blobs match the pinned authorities', () => {
  assert.equal(blob(source), oldSHA);
  assert.equal(blob(Buffer.from(merged)), newSHA);
});
test('historical raw FTS emissions ignore evidence-quality metadata', () => {
  assert.notEqual(a.confidence, b.confidence);
  assert.notEqual(a.verificationStatus, b.verificationStatus);
  assert.deepEqual(emit(fts[0].index, a), emit(fts[0].index, b));
});
test('merged raw FTS emissions also ignore evidence-quality metadata', () => {
  assert.deepEqual(emit(fts[1].index, a), emit(fts[1].index, b));
});
test('neither generation stores confidence or verificationStatus in FTS', () => {
  for (const design of fts) {
    const events = emit(design.index, b);
    assert.deepEqual(events.filter(e => ['confidence', 'verificationStatus'].includes(e.field)), []);
    assert.ok(events.every(e => e.stored));
  }
});
test('indexed content change distinguishes records in both generations', () => {
  for (const design of fts)
    assert.notDeepEqual(emit(design.index, a), emit(design.index, {...a, content: 'different evidence'}));
});
test('mutated callback is detected as a negative control, not upstream behavior', () => {
  for (const design of fts) {
    const marker = "add('dtype',doc.dtype);";
    assert.equal(design.index.split(marker).length, 2);
    const mutant = design.index.replace(marker, marker + "add('confidence',doc.confidence);");
    assert.notDeepEqual(emit(mutant, a), emit(mutant, b));
    assert.deepEqual(emit(mutant, b).filter(e => e.field === 'confidence').map(e => e.value), ['0.95']);
  }
});
