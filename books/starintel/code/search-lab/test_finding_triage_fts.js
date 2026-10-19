'use strict';
// Chapter 15: search discoverability is not a Finding triage or remediation check.
// Execute exact, independently attested historical/merged Server FTS callbacks.
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
const root = process.env.STAR_SEARCH_LAB_SERVER;
const historical = process.env.STAR_SEARCH_FINDING_HISTORICAL_DESIGN ||
  (root && path.join(root, 'source/views/search.json'));
if (!historical) throw new Error('original historical search.json is required');
const inputs = [['historical', historical]];
if (process.env.STAR_SEARCH_FINDING_MERGED_DESIGN)
  inputs.push(['merged', process.env.STAR_SEARCH_FINDING_MERGED_DESIGN]);

function sourceFor(file, generation) {
  const bytes = fs.readFileSync(file);
  const sha = crypto.createHash('sha1')
    .update(Buffer.from('blob ' + bytes.length + '\0')).update(bytes).digest('hex');
  assert.equal(sha, PINS[generation], generation + ': original Git blob drift');
  const design = JSON.parse(bytes.toString('utf8'));
  assert.equal(design._id, '_design/search');
  assert.equal(design.indexes.fts.analyzer.fields.dataset, 'keyword');
  assert.equal(design.indexes.fts.analyzer.fields.tenant_id, 'keyword');
  return design.indexes.fts.index;
}

function capture(callback, record) {
  const output = [];
  const scope = vm.createContext({index(field, value, options) {
    output.push({field, value, stored: options?.store === true});
  }});
  scope.callback = new vm.Script('(' + callback + ')').runInContext(scope, {timeout: 1000});
  scope.record = structuredClone(record);
  new vm.Script('callback(record)').runInContext(scope, {timeout: 1000});
  return output;
}
const values = (events, key) => events.filter(e => e.field === key).map(e => e.value);

// Fictional canonical-shaped Finding, not SDK-validated or ingested.
const initial = Object.freeze({
  id: 'starintel:finding:fictional-01', rev: 'r1', dtype: 'finding',
  dataset: 'training-security', schemaVersion: '0.10.1',
  title: 'Fictional package audit finding',
  severity: 'low', status: 'open', cve: ['CVE-0000-0000'],
  cvss: {score: 2.1}, cwe: ['CWE-000'],
  discoveredAt: 1767225600,
  recommendation: 'Review synthetic package',
});
for (const [generation, file] of inputs) {
  const source = sourceFor(file, generation);
  const baseline = capture(source, initial);
  test(generation + ': Finding label and caller-independent index scope are emitted', () => {
    assert.deepEqual(values(baseline, 'title'), [initial.title]);
    assert.deepEqual(values(baseline, 'dtype'), ['finding']);
    assert.deepEqual(values(baseline, 'dataset'), ['training-security']);
    assert.deepEqual(values(baseline, 'tenant_id'), ['default']);
    assert.ok(baseline.every(x => x.stored));
  });
  test(generation + ': severity and CVSS changes do not alter raw index emissions', () => {
    const changed = {...initial, severity: 'critical', cvss: {score: 9.9}};
    assert.deepEqual(capture(source, changed), baseline);
    assert.deepEqual(values(baseline, 'severity'), []);
    assert.deepEqual(values(baseline, 'cvss'), []);
  });
  test(generation + ': open versus resolved triage states are not indexed', () => {
    const changed = {...initial, status: 'resolved', resolvedAt: 1769904000};
    assert.deepEqual(capture(source, changed), baseline);
    assert.deepEqual(values(baseline, 'status'), []);
    assert.deepEqual(values(baseline, 'resolvedAt'), []);
  });
  test(generation + ': CVE, CWE and recommendation claims are not indexed', () => {
    const changed = {...initial, cve: ['CVE-9999-9999'], cwe: ['CWE-999'],
      recommendation: 'Do nothing to fictional system'};
    assert.deepEqual(capture(source, changed), baseline);
    for (const key of ['cve', 'cwe', 'recommendation'])
      assert.deepEqual(values(baseline, key), []);
  });
  test(generation + ': nested Finding data cannot turn nonindexed triage into evidence', () => {
    const a = capture(source, {...initial, data: {severity: 'low', status: 'open'}});
    const b = capture(source, {...initial, data: {severity: 'critical', status: 'resolved'}});
    assert.deepEqual(a, b);
    assert.deepEqual(a, baseline);
  });
  test(generation + ': title change is a positive control for index coverage', () => {
    const changed = capture(source, {...initial, title: 'Different fictional finding'});
    assert.notDeepEqual(changed, baseline);
    assert.deepEqual(values(changed, 'title'), ['Different fictional finding']);
  });
  test(generation + ': dataset difference is observed, not a grant of search authority', () => {
    const changed = capture(source, {...initial, dataset: 'training-private'});
    assert.deepEqual(values(changed, 'dataset'), ['training-private']);
    assert.notDeepEqual(changed, baseline);
    assert.deepEqual(values(changed, 'severity'), []);
  });
  test(generation + ': deliberate in-memory severity-indexing mutant is detected', () => {
    const needle = "add('title',doc.title);";
    assert.equal(source.split(needle).length, 2, 'mutant anchor changed');
    const mutant = source.replace(needle, needle + "add('severity',doc.severity);");
    const changed = capture(mutant, {...initial, severity: 'critical'});
    assert.deepEqual(values(changed, 'severity'), ['critical']);
    assert.notDeepEqual(changed, baseline);
    if (process.env.STAR_SEARCH_FINDING_RED === '1')
      assert.deepEqual(changed, baseline, 'intentional RED: mutant indexed severity');
  });
}
