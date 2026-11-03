'use strict';
// Chapter 15: time fields in canonical Event/Observation are not FTS date filters.
// Original pinned index callbacks only; synthetic schema-shaped, not SDK-validated.
const A = require('node:assert/strict');
const C = require('node:crypto');
const F = require('node:fs');
const P = require('node:path');
const T = require('node:test');
const V = require('node:vm');
const blobs = {historical: '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged: 'dd6336f3047982db2f0e3615fed1413ed1e58e13'};
const historical = process.env.STAR_SEARCH_TIME_HISTORICAL_DESIGN ||
  (process.env.STAR_SEARCH_LAB_SERVER &&
   P.join(process.env.STAR_SEARCH_LAB_SERVER, 'source/views/search.json'));
if (!historical) throw Error('pinned historical design required');
const inputs = [['historical', historical]];
if (process.env.STAR_SEARCH_TIME_MERGED_DESIGN)
  inputs.push(['merged', process.env.STAR_SEARCH_TIME_MERGED_DESIGN]);
function original(name, filename) {
  const bytes = F.readFileSync(filename);
  const sha = C.createHash('sha1').update(Buffer.from('blob ' + bytes.length + '\0'))
    .update(bytes).digest('hex');
  A.equal(sha, blobs[name], name + ': Git blob pin changed');
  const design = JSON.parse(bytes.toString('utf8'));
  A.equal(design._id, '_design/search');
  A.equal(typeof design.indexes.fts.index, 'string');
  return design.indexes.fts.index;
}
function emit(fn, doc) {
  const rows = [];
  const ctx = V.createContext({index(k, v, opts) {
    rows.push({field: k, value: v, stored: opts?.store === true});
  }});
  ctx.fn = new V.Script('(' + fn + ')').runInContext(ctx, {timeout: 1000});
  ctx.doc = structuredClone(doc);
  new V.Script('fn(doc)').runInContext(ctx, {timeout: 1000});
  return rows;
}
function values(rows, key) { return rows.filter(x => x.field === key).map(x => x.value); }
// Fields checked against StarLang 0.10.1 generated schema at commit
// 96d26c338078676ec1dc6928755901636c9f7ef0, Git blob
// 537163da436f67a973e280d1704e32bdba5b888b.
const event = Object.freeze({
  id: 'starintel:event:fictional-library-training', rev: 'fictional-r1',
  dataset: 'book-synthetic', dtype: 'event', schemaVersion: '0.10.1',
  name: 'Fictional Library Open Day', eventKind: 'training', status: 'planned',
  startAt: '2026-10-16T09:00:00Z', endAt: '2026-10-16T10:00:00Z',
  observedAt: 1792166400,
});
const obs = Object.freeze({
  id: 'starintel:observation:fictional-calendar-notice', rev: 'fictional-r1',
  dataset: 'book-synthetic', dtype: 'observation', schemaVersion: '0.10.1',
  observationType: 'calendar-notice', subjectId: event.id,
  observedAt: 1792166400, payloadObservedAt: '2026-10-16T08:00:00Z',
  description: 'Fictional notice examined', value: 'open', status: 'reviewed',
});
for (const [name, file] of inputs) {
  const fn = original(name, file);
  T(name + ': two canonical time representations', () => {
    A.equal(event.dtype, 'event'); A.equal(obs.dtype, 'observation');
    A.equal(typeof event.startAt, 'string');
    A.equal(typeof event.endAt, 'string');
    A.ok(Number.isInteger(event.observedAt));
    A.ok(Number.isInteger(obs.observedAt));
    A.equal(typeof obs.payloadObservedAt, 'string');
  });
  T(name + ': event name indexed but time and lifecycle absent', () => {
    const rows = emit(fn, event);
    A.deepEqual(rows.map(x => x.field), ['tenant_id', 'dataset', 'dtype', 'name']);
    A.deepEqual(values(rows, 'name'), [event.name]);
    for (const key of ['startAt', 'endAt', 'observedAt', 'eventKind', 'status'])
      A.deepEqual(values(rows, key), []);
    A.ok(rows.every(x => x.stored));
  });
  T(name + ': rescheduling event does not change FTS emissions', () => {
    const changed = {...event, startAt: '2027-11-12T09:00:00Z',
      endAt: '2027-11-12T10:00:00Z', observedAt: 1826006400, status: 'rescheduled'};
    A.notEqual(event.startAt, changed.startAt);
    A.deepEqual(emit(fn, event), emit(fn, changed));
  });
  T(name + ': changing event name does change FTS emissions', () => {
    const changed = {...event, name: 'Another Fictional Library Session'};
    A.notDeepEqual(emit(fn, event), emit(fn, changed));
    A.deepEqual(values(emit(fn, changed), 'name'), [changed.name]);
  });
  T(name + ': observation timestamp and measurement not indexed', () => {
    const rows = emit(fn, obs);
    A.deepEqual(rows.map(x => x.field), ['tenant_id', 'dataset', 'dtype']);
    for (const key of ['observedAt', 'payloadObservedAt', 'observationType',
      'subjectId', 'description', 'value', 'status']) A.deepEqual(values(rows, key), []);
  });
  T(name + ': modifying observation time/value does not change raw FTS', () => {
    const changed = {...obs, observedAt: 1826006400,
      payloadObservedAt: '2027-11-12T08:00:00Z', description: 'Another fiction',
      value: 'closed', subjectId: 'starintel:event:another-fictional-event'};
    A.notEqual(obs.observedAt, changed.observedAt);
    A.deepEqual(emit(fn, obs), emit(fn, changed));
  });
  T(name + ': dataset and dtype remain visible raw fields', () => {
    const first = emit(fn, obs), second = emit(fn, {...obs, dataset: 'other-synthetic'});
    A.notDeepEqual(first, second);
    A.deepEqual(values(first, 'dataset'), ['book-synthetic']);
    A.deepEqual(values(first, 'dtype'), ['observation']);
    A.deepEqual(values(emit(fn, event), 'dtype'), ['event']);
  });
  T(name + ': augmented callback proves time-field sensitivity', () => {
    const anchor = "add('dtype',doc.dtype);";
    A.equal(fn.split(anchor).length, 2, 'mutation anchor drift');
    const mutant = fn.replace(anchor, anchor + "add('startAt',doc.startAt);" +
      "add('observedAt',doc.observedAt);");
    A.notDeepEqual(emit(mutant, event), emit(mutant,
      {...event, startAt: '2027-11-12T09:00:00Z'}));
    A.deepEqual(values(emit(mutant, event), 'startAt'), [event.startAt]);
    A.deepEqual(values(emit(mutant, obs), 'observedAt'), [obs.observedAt]);
  });
}
