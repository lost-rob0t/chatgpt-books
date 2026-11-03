'use strict';
// BK13: service discovery is not a verified TCP endpoint, TLS handshake, or certificate.
// Execute ORIGINAL immutable StarIntel Server FTS callbacks for both source editions.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

const PINS = Object.freeze({
  historical: '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged: 'dd6336f3047982db2f0e3615fed1413ed1e58e13',
});
const path = require('node:path');
const root = process.env.STAR_SEARCH_LAB_SERVER;
const historical = process.env.STAR_SEARCH_SERVICE_HISTORICAL_DESIGN ||
  (root && path.join(root, 'source/views/search.json'));
if (!historical) throw new Error('Original historical search.json is required');
const INPUTS = [['historical', historical]];
if (process.env.STAR_SEARCH_SERVICE_MERGED_DESIGN)
  INPUTS.push(['merged', process.env.STAR_SEARCH_SERVICE_MERGED_DESIGN]);

function sourceFor(file, generation) {
  const bytes = fs.readFileSync(file);
  const sha = crypto.createHash('sha1')
    .update(Buffer.from('blob ' + bytes.length + '\0')).update(bytes).digest('hex');
  assert.equal(sha, PINS[generation], generation + ': source Git blob mismatch');
  const design = JSON.parse(bytes.toString('utf8'));
  assert.equal(design._id, '_design/search');
  assert.equal(design.indexes.fts.analyzer.fields.dataset, 'keyword');
  assert.equal(design.indexes.fts.analyzer.fields.tenant_id, 'keyword');
  return design.indexes.fts.index;
}
function capture(callback, record) {
  const emissions = [];
  const context = vm.createContext({index(field, value, options) {
    emissions.push({field, value, stored: options?.store === true});
  }});
  context.callback = new vm.Script('(' + callback + ')').runInContext(context, {timeout: 1000});
  context.record = structuredClone(record);
  new vm.Script('callback(record)').runInContext(context, {timeout: 1000});
  return emissions;
}
const values = (events, field) => events.filter(e => e.field === field).map(e => e.value);

// Fictional canonical-shaped 0.10.1 Service; not claimed SDK-validated or ingested.
const service = Object.freeze({
  id: 'starintel:service:fictional-lab-01', rev: 'r1',
  dtype: 'service', dataset: 'book-registered-systems', schemaVersion: '0.10.1',
  name: 'Owned lab status endpoint',
  host: {id: 'starintel:host:fictional-lab-01', schema: 'org.starintel/core@1/host'},
  port: 8443, transport: 'tcp', product: 'training-web', version: '1.0',
  state: 'open', tls: true,
  tlsCertificate: {id: 'starintel:file:fictional-cert-01', schema: 'org.starintel/core@1/file'},
  fingerprints: {sha256: 'synthetic-only'},
  lastOpenAt: 1792300000,
});
const unindexed = ['port', 'transport', 'product', 'version', 'state', 'tls',
  'tlsCertificate', 'host', 'fingerprints', 'lastOpenAt'];

for (const [generation, file] of INPUTS) {
  const callback = sourceFor(file, generation);
  const baseline = capture(callback, service);
  test(generation + ': source emits name and scope but not service validation', () => {
    assert.deepEqual(values(baseline, 'name'), [service.name]);
    assert.deepEqual(values(baseline, 'dataset'), [service.dataset]);
    assert.deepEqual(values(baseline, 'dtype'), ['service']);
    assert.deepEqual(values(baseline, 'tenant_id'), ['default']);
    assert.ok(baseline.every(e => e.stored));
  });
  test(generation + ': TLS flag and certificate reference changes preserve index events', () => {
    const changed = {...service, tls: false,
      tlsCertificate: {id: 'starintel:file:other-fictional-cert', schema: 'org.starintel/core@1/file'}};
    assert.deepEqual(capture(callback, changed), baseline);
    assert.deepEqual(values(baseline, 'tls'), []);
    assert.deepEqual(values(baseline, 'tlsCertificate'), []);
  });
  test(generation + ': port, protocol and observed service state are not indexed', () => {
    const changed = {...service, port: 22, transport: 'udp', state: 'closed',
      product: 'other-training-product', version: '999.0', lastOpenAt: 1799999999};
    assert.deepEqual(capture(callback, changed), baseline);
    for (const key of ['port', 'transport', 'state', 'product', 'version', 'lastOpenAt'])
      assert.deepEqual(values(baseline, key), []);
  });
  test(generation + ': host and fingerprint references cannot certify a connection', () => {
    const changed = {...service,
      host: {id: 'starintel:host:fictional-lab-02', schema: 'org.starintel/core@1/host'},
      fingerprints: {sha256: 'another-fictional-hash'}};
    assert.deepEqual(capture(callback, changed), baseline);
    assert.deepEqual(values(baseline, 'host'), []);
    assert.deepEqual(values(baseline, 'fingerprints'), []);
  });
  test(generation + ': every unsupported Service field is absent', () => {
    for (const key of unindexed) assert.deepEqual(values(baseline, key), [], key);
  });
  test(generation + ': indexed name change provides a positive control', () => {
    const changed = capture(callback, {...service, name: 'Different training endpoint'});
    assert.notDeepEqual(changed, baseline);
    assert.deepEqual(values(changed, 'name'), ['Different training endpoint']);
  });
  test(generation + ': dataset field changes are observed, not authorization grants', () => {
    const changed = capture(callback, {...service, dataset: 'book-restricted-systems'});
    assert.notDeepEqual(changed, baseline);
    assert.deepEqual(values(changed, 'dataset'), ['book-restricted-systems']);
    for (const key of unindexed) assert.deepEqual(values(changed, key), []);
  });
  test(generation + ': injected TLS-indexing mutant is detected by RED control', () => {
    const needle = "add('title',doc.title);";
    assert.equal(callback.split(needle).length, 2, 'mutation anchor drifted');
    const mutant = callback.replace(needle, needle + "add('tls',doc.tls);");
    const changed = capture(mutant, {...service, tls: false});
    assert.deepEqual(values(changed, 'tls'), [false]);
    assert.notDeepEqual(changed, baseline);
    if (process.env.STAR_SEARCH_SERVICE_RED === '1')
      assert.deepEqual(changed, baseline, 'intentional RED: mutated callback indexed TLS flag');
  });
}
