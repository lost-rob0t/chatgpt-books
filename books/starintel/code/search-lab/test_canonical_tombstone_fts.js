'use strict';
// BK13: canonical tombstone metadata vs raw FTS emissions (NOT live CouchDB).
// The only executable callback is the original, byte-attested Server FTS code.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const pins = Object.freeze({
  historical: '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged: 'dd6336f3047982db2f0e3615fed1413ed1e58e13',
});
const historical = process.env.STAR_SEARCH_TOMBSTONE_HISTORICAL_DESIGN ||
  (process.env.STAR_SEARCH_LAB_SERVER &&
   path.join(process.env.STAR_SEARCH_LAB_SERVER, 'source/views/search.json'));
if (!historical) throw new Error('pinned historical design path required');
const inputs = [['historical', historical]];
if (process.env.STAR_SEARCH_TOMBSTONE_MERGED_DESIGN)
  inputs.push(['merged', process.env.STAR_SEARCH_TOMBSTONE_MERGED_DESIGN]);
function originalCallback(file, generation) {
  const bytes = fs.readFileSync(file);
  const actual = crypto.createHash('sha1')
    .update(Buffer.from('blob ' + bytes.length + '\0')).update(bytes).digest('hex');
  assert.equal(actual, pins[generation], 'wrong upstream Git blob');
  const design = JSON.parse(bytes.toString('utf8'));
  assert.equal(design._id, '_design/search');
  return design.indexes.fts.index;
}
function capture(callback, record) {
  const events = [];
  const scope = vm.createContext({index(field, value, options) {
    events.push({field, value, stored: options?.store === true});
  }, record: structuredClone(record)});
  scope.callback = new vm.Script('(' + callback + ')').runInContext(scope, {timeout: 1000});
  new vm.Script('callback(record)').runInContext(scope, {timeout: 1000});
  return events;
}
const values = (events, name) => events.filter(e => e.field === name).map(e => e.value);
// Canonical 0.10.1 Person property definitions: deleted:boolean,
// tombstoneReason:string, validFrom/validUntil:UnixTime, retentionPolicy:string.
// A Person-shaped fixture is not a claim of SDK validation/admission.
const person = Object.freeze({
  id: 'starintel:person:fictional-course-record', rev: 'canonical-r1',
  dataset: 'book-synthetic', dtype: 'person', schemaVersion: '0.10.1',
  fname: 'Fictional', lname: 'Example', deleted: false, tombstoneReason: '',
  validFrom: 100, validUntil: 900, retentionPolicy: 'course-example',
});
for (const [generation, source] of inputs) {
  const callback = originalCallback(source, generation);
  const baseline = capture(callback, person);
  test(generation + ': fname, dataset, dtype and tenant are positive controls', () => {
    assert.deepEqual(values(baseline, 'fname'), ['Fictional']);
    assert.deepEqual(values(baseline, 'dataset'), ['book-synthetic']);
    assert.deepEqual(values(baseline, 'dtype'), ['person']);
    assert.deepEqual(values(baseline, 'tenant_id'), ['default']);
    assert.ok(baseline.every(event => event.stored));
  });
  test(generation + ': canonical deleted=false -> true does not alter raw emissions', () => {
    assert.deepEqual(capture(callback, {...person, deleted: true}), baseline);
    assert.deepEqual(values(baseline, 'deleted'), []);
  });
  test(generation + ': canonical tombstone reason does not alter raw emissions', () => {
    assert.deepEqual(capture(callback, {...person, tombstoneReason: 'synthetic-tombstone'}), baseline);
    assert.deepEqual(values(baseline, 'tombstoneReason'), []);
  });
  test(generation + ': canonical validity interval does not alter raw emissions', () => {
    assert.deepEqual(capture(callback, {...person, validFrom: 200, validUntil: 300}), baseline);
    assert.deepEqual(values(baseline, 'validUntil'), []);
  });
  test(generation + ': retention policy does not alter raw emissions', () => {
    assert.deepEqual(capture(callback, {...person, retentionPolicy: 'expire-after-lab'}), baseline);
    assert.deepEqual(values(baseline, 'retentionPolicy'), []);
  });
  test(generation + ': a source-level _deleted flag is not a canonical deleted field', () => {
    // This invokes an isolated callback explicitly. It does NOT imply that
    // CouchDB invokes FTS on a deletion tombstone or serves it in search.
    assert.deepEqual(capture(callback, {...person, _deleted: true}), baseline);
    assert.deepEqual(values(baseline, '_deleted'), []);
  });
  test(generation + ': indexed fname or dataset does change emissions', () => {
    assert.notDeepEqual(capture(callback, {...person, fname: 'Another'}), baseline);
    assert.notDeepEqual(capture(callback, {...person, dataset: 'book-other'}), baseline);
  });
  test(generation + ': altered callback would expose canonical deleted transitions', () => {
    const marker = "add('dtype',doc.dtype);";
    assert.ok(callback.includes(marker));
    const mutant = callback.replace(marker, marker + "add('deleted',doc.deleted);");
    assert.notDeepEqual(capture(mutant, person), capture(mutant, {...person, deleted: true}));
  });
}
