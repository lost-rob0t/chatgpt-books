'use strict';
// Chapter 15: finding a Port by label does not establish an open socket.
// Executes only pinned Server source callbacks with fictional, canonical-shaped input.
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
// StarLang org.starintel/core@1 v0.10.1 Port requires id/dataset/dtype/
// schemaVersion/number; number, protocol, state, host, lastOpenAt and banner
// are canonical properties, NOT automatically indexed search fields.
const PORT = Object.freeze({
  id: 'starintel:port:fictional-demo', rev: 'rev-fictional-1',
  dtype: 'port', dataset: 'fictional-network-inventory', schemaVersion: '0.10.1',
  name: 'Fictional service endpoint', number: 8443, protocol: 'tcp',
  transport: 'tcp', state: 'open', reason: 'fictional test observation',
  banner: 'fictional-service/1.0', firstOpenAt: 1760000000,
  lastOpenAt: 1760000100,
  host: {schema: 'org.starintel/core@1', id: 'starintel:host:fictional'},
});
const NONINDEXED = Object.freeze([
  'number', 'protocol', 'transport', 'state', 'reason', 'banner',
  'firstOpenAt', 'lastOpenAt', 'host',
]);
const historical = process.env.STAR_SEARCH_PORT_HISTORICAL_DESIGN ||
  (process.env.STAR_SEARCH_LAB_SERVER && path.join(
    process.env.STAR_SEARCH_LAB_SERVER, 'source/views/search.json'));
if (!historical) throw new Error('pinned historical Server search.json required');
const sources = [['historical', historical]];
if (process.env.STAR_SEARCH_PORT_MERGED_DESIGN)
  sources.push(['merged', process.env.STAR_SEARCH_PORT_MERGED_DESIGN]);

function originalIndex(file, generation) {
  const bytes = fs.readFileSync(file);
  const actual = crypto.createHash('sha1')
    .update(Buffer.from(`blob ${bytes.length}\0`)).update(bytes).digest('hex');
  assert.equal(actual, PINS[generation], `${generation} Git source blob mismatch`);
  const design = JSON.parse(bytes.toString('utf8'));
  assert.equal(design._id, '_design/search');
  assert.equal(design.indexes.fts.analyzer.fields.dataset, 'keyword');
  assert.equal(design.indexes.fts.analyzer.fields.tenant_id, 'keyword');
  return design.indexes.fts.index;
}
function emissions(callback, document) {
  const rows = [];
  const context = vm.createContext({doc: structuredClone(document),
    index(field, value, options) {
      assert.equal(options?.store, true);
      if (rows.length >= 2048) throw new Error('bounded test budget exceeded');
      rows.push({field, value});
    },
  });
  new vm.Script(`(${callback})(doc)`).runInContext(context, {timeout: 1000});
  return rows;
}
const values = (rows, field) => rows.filter(row => row.field === field)
  .map(row => row.value);
const variant = Object.freeze({...PORT, number: 9443, protocol: 'udp',
  transport: 'udp', state: 'closed', reason: 'fictional new observation',
  banner: 'fictional-other/2.0', firstOpenAt: 1760000200,
  lastOpenAt: 1760000300,
  host: {schema: 'org.starintel/core@1', id: 'starintel:host:another-fictional'},
});

for (const [generation, file] of sources) {
  const source = originalIndex(file, generation);
  const baseline = emissions(source, PORT);
  test(`${generation}: label and server search scope are raw emitted fields`, () => {
    assert.deepEqual(values(baseline, 'name'), [PORT.name]);
    assert.deepEqual(values(baseline, 'dtype'), ['port']);
    assert.deepEqual(values(baseline, 'dataset'), [PORT.dataset]);
    assert.deepEqual(values(baseline, 'tenant_id'), ['default']);
  });
  test(`${generation}: state, transport, banner and port number are not emitted`, () => {
    for (const field of NONINDEXED) assert.deepEqual(values(baseline, field), []);
  });
  test(`${generation}: changing only reachability assertions preserves raw FTS`, () => {
    assert.deepEqual(emissions(source, variant), baseline);
  });
  test(`${generation}: no state or missing state cannot be distinguished by FTS`, () => {
    const absent = {...PORT};
    delete absent.state;
    assert.deepEqual(emissions(source, absent), baseline);
  });
  test(`${generation}: a port label change is observable`, () => {
    const changed = emissions(source, {...PORT, name: 'Fictional alternate label'});
    assert.deepEqual(values(changed, 'name'), ['Fictional alternate label']);
    assert.notDeepEqual(changed, baseline);
  });
  test(`${generation}: dataset emission changes without granting dataset access`, () => {
    const changed = emissions(source, {...PORT, dataset: 'another-fictional-dataset'});
    assert.deepEqual(values(changed, 'dataset'), ['another-fictional-dataset']);
    assert.notDeepEqual(changed, baseline);
  });
  test(`${generation}: tenant stamping changes only raw scope emissions`, () => {
    const changed = emissions(source, {...PORT, tenant_id: 'fictional-lab-tenant'});
    assert.deepEqual(values(changed, 'tenant_id'), ['fictional-lab-tenant']);
    for (const field of NONINDEXED) assert.deepEqual(values(changed, field), []);
  });
  test(`${generation}: no name means no label, regardless of port state`, () => {
    const unnamed = {...PORT};
    delete unnamed.name;
    assert.deepEqual(values(emissions(source, unnamed), 'name'), []);
  });
  test(`${generation}: deliberate state-indexing mutation is detected (RED control)`, () => {
    const anchor = "add('dtype',doc.dtype);";
    assert.equal(source.split(anchor).length, 2, 'source mutation anchor drifted');
    const mutant = source.replace(anchor, anchor + "add('state',doc.state);");
    const mutated = emissions(mutant, PORT);
    assert.deepEqual(values(mutated, 'state'), ['open']);
    assert.notDeepEqual(mutated, baseline);
    if (process.env.STAR_SEARCH_PORT_RED === '1')
      assert.deepEqual(mutated, baseline, 'intentional RED: indexing port state changed');
  });
}
