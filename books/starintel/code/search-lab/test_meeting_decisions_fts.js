'use strict';
// Chapter 15: indexed meeting names do not certify decisions, minutes or attendance.
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
const historical = process.env.STAR_SEARCH_MEETING_HISTORICAL_DESIGN ||
  (process.env.STAR_SEARCH_LAB_SERVER &&
    path.join(process.env.STAR_SEARCH_LAB_SERVER, 'source/views/search.json'));
if (!historical) throw new Error('historical pinned design path required');
const generations = [['historical', historical]];
if (process.env.STAR_SEARCH_MEETING_MERGED_DESIGN) {
  generations.push(['merged', process.env.STAR_SEARCH_MEETING_MERGED_DESIGN]);
}

function readPinnedIndex(file, generation) {
  const bytes = fs.readFileSync(file);
  const actual = crypto.createHash('sha1')
    .update(Buffer.from('blob ' + bytes.length + '\0')).update(bytes).digest('hex');
  assert.equal(actual, PINS[generation], 'immutable Server Git blob changed');
  const design = JSON.parse(bytes.toString('utf8'));
  assert.equal(design._id, '_design/search');
  assert.equal(design.indexes.fts.analyzer.fields.dataset, 'keyword');
  assert.equal(design.indexes.fts.analyzer.fields.tenant_id, 'keyword');
  return design.indexes.fts.index;
}

function capture(source, doc) {
  const emitted = [];
  const scope = vm.createContext({index(field, value, opts) {
    emitted.push({field, value, stored: opts?.store === true});
  }});
  scope.callback = new vm.Script('(' + source + ')').runInContext(scope, {timeout: 1000});
  scope.doc = structuredClone(doc);
  new vm.Script('callback(doc)').runInContext(scope, {timeout: 1000});
  return emitted;
}

const values = (emitted, field) => emitted.filter(item => item.field === field)
  .map(item => item.value);
const fictional = Object.freeze({
  id: 'starintel:meeting:fictional-council', rev: 'r1',
  schemaVersion: '0.10.1', dtype: 'meeting', dataset: 'fictional-open-meetings',
  name: 'Fictional equipment committee',
  startAt: '2026-03-10T12:00:00Z', endAt: '2026-03-10T13:00:00Z',
  status: 'draft', chairIds: ['fictional-chair'],
  participantIds: ['fictional-member-a'], attendeeRoles: [{role: 'observer'}],
  agenda: ['Approve fictional test fixtures'], agendaItemIds: ['fictional-agenda-1'],
  minuteFileIds: ['fictional-minutes-draft'],
  decisions: ['Proposal deferred'], decisionIds: ['fictional-decision-1'],
  actions: ['Review test equipment'], actionItemIds: ['fictional-action-1'],
  outcome: 'No binding decision',
});
const notIndexFields = [
  'startAt', 'endAt', 'status', 'chairIds', 'participantIds', 'attendeeRoles',
  'agenda', 'agendaItemIds', 'minuteFileIds', 'decisions', 'decisionIds',
  'actions', 'actionItemIds', 'outcome',
];
for (const [generation, file] of generations) {
  const source = readPinnedIndex(file, generation);
  const base = capture(source, fictional);
  test(generation + ': meeting name and server search scope are emitted', () => {
    assert.deepEqual(values(base, 'name'), [fictional.name]);
    assert.deepEqual(values(base, 'dataset'), [fictional.dataset]);
    assert.deepEqual(values(base, 'dtype'), ['meeting']);
    assert.deepEqual(values(base, 'tenant_id'), ['default']);
    assert.ok(base.every(item => item.stored));
    for (const field of notIndexFields) assert.deepEqual(values(base, field), []);
  });
  test(generation + ': decisions and minutes can change without index changes', () => {
    assert.deepEqual(capture(source, {...fictional, decisions: ['Approved'],
      decisionIds: ['fictional-decision-2'], minuteFileIds: ['final-minutes']}), base);
  });
  test(generation + ': attendance and chairs are not established by a hit', () => {
    assert.deepEqual(capture(source, {...fictional, chairIds: [],
      participantIds: ['other-member'], attendeeRoles: [{role: 'voter'}]}), base);
  });
  test(generation + ': agenda and action items do not alter raw projection', () => {
    assert.deepEqual(capture(source, {...fictional, agenda: ['New agenda'],
      agendaItemIds: [], actions: ['New action'], actionItemIds: []}), base);
  });
  test(generation + ': dates, status and outcome are not timeline evidence', () => {
    assert.deepEqual(capture(source, {...fictional,
      startAt: '2026-03-11T09:00:00Z', endAt: '2026-03-11T09:05:00Z',
      status: 'cancelled', outcome: 'Cancelled'}), base);
  });
  test(generation + ': renaming the meeting is an indexed positive control', () => {
    const changed = capture(source, {...fictional, name: 'Revised fictional name'});
    assert.notDeepEqual(changed, base);
    assert.deepEqual(values(changed, 'name'), ['Revised fictional name']);
  });
  test(generation + ': dataset is a projection field, not permission proof', () => {
    const changed = capture(source, {...fictional, dataset: 'fictional-private'});
    assert.notDeepEqual(changed, base);
    assert.deepEqual(values(changed, 'dataset'), ['fictional-private']);
  });
  test(generation + ': server tenant stamp affects emitted scope, not attendance', () => {
    const changed = capture(source, {...fictional, tenant_id: 'synthetic-other'});
    assert.notDeepEqual(changed, base);
    assert.deepEqual(values(changed, 'tenant_id'), ['synthetic-other']);
    assert.deepEqual(values(changed, 'participantIds'), []);
  });
  test(generation + ': an in-memory decision-indexing mutation is detectable', () => {
    const anchor = "add('title',doc.title);";
    assert.equal(source.split(anchor).length, 2, 'source mutation anchor drift');
    const mutant = source.replace(anchor, anchor + "add('decisions',doc.decisions);");
    const result = capture(mutant, fictional);
    assert.deepEqual(values(result, 'decisions'), fictional.decisions);
    assert.notDeepEqual(result, base);
    if (process.env.STAR_SEARCH_MEETING_RED === '1') {
      assert.deepEqual(result, base, 'intentional RED: decision text entered index');
    }
  });
}
