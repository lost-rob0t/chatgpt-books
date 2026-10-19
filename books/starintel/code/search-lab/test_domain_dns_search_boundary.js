'use strict';
// Exercises byte-attested original historical (and optionally merged) FTS code.
// No DNS resolution, network requests, or canonical SDK admission.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const {gitBlob, readIndex, emissions, difference, PINS} = require('./projection_delta');
const {BASE, fixtures, fieldNames, examine, inspect} = require('./domain_dns_search_boundary');

const hist = process.env.STAR_SEARCH_DOMAIN_HISTORICAL_DESIGN ||
  (process.env.STAR_SEARCH_LAB_SERVER &&
   path.join(process.env.STAR_SEARCH_LAB_SERVER, 'source/views/search.json'));
assert.ok(hist, 'set STAR_SEARCH_DOMAIN_HISTORICAL_DESIGN or STAR_SEARCH_LAB_SERVER');
const merged = process.env.STAR_SEARCH_DOMAIN_MERGED_DESIGN;
const originals = [{generation: 'historical', file: hist, source: readIndex(hist, 'historical')}];
if (merged) originals.push({generation: 'merged', file: merged, source: readIndex(merged, 'merged')});
const base = fixtures().before;

for (const {generation, file, source} of originals) {
  test(`${generation}: original JSON bytes match pinned Git blob`, () => {
    assert.equal(gitBlob(fs.readFileSync(file)), PINS[generation]);
  });
  test(`${generation}: canonical-shaped Domain has name/dtype/dataset, not DNS as raw fields`, () => {
    const rows = emissions(source, base);
    const names = new Set(rows.map(x => x.field));
    for (const name of ['name', 'dtype', 'dataset', 'tenant_id']) assert.ok(names.has(name));
    for (const name of ['dnsRecords', 'mxRecords', 'txtRecords', 'nameservers',
      'dnssec', 'resolvedAddresses', 'registrar', 'whois']) assert.ok(!names.has(name));
    assert.ok(rows.some(x => x.field === 'name' && x.value === 'lab.example.invalid'));
  });
  test(`${generation}: DNS state alone does not change one raw emission`, () => {
    const {before, changedDns} = fixtures();
    assert.deepEqual(difference(emissions(source, before), emissions(source, changedDns)), {
      before_count: 4, after_count: 4, added: [], removed: [],
      reordered_only: false, raw_emissions_changed: false,
    });
  });
  test(`${generation}: name and scope positive controls still change stored emissions`, () => {
    const finding = examine(source);
    assert.deepEqual(finding.name_change_fields, ['name']);
    assert.deepEqual(finding.scope_change_fields, ['dataset', 'tenant_id']);
    assert.equal(finding.dns_state_only_raw_change, false);
  });
  test(`${generation}: changing fictional IP/DNSSEC cannot become resolution proof`, () => {
    const {before, changedDns} = fixtures();
    assert.notDeepEqual(changedDns.dnsRecords, before.dnsRecords);
    assert.notEqual(changedDns.dnssec, before.dnssec);
    assert.notDeepEqual(changedDns.nameservers, before.nameservers);
    assert.equal(emissions(source, changedDns).find(x => x.field === 'name').value,
                 'lab.example.invalid');
  });
}

test('schema-oriented fixture has only invented .invalid names and documentation IPv4', () => {
  assert.equal(BASE.dtype, 'domain');
  assert.equal(BASE.schemaVersion, '0.10.1');
  assert.equal(BASE.dnsRecords[0].value, '192.0.2.10');
  assert.equal(BASE.dnssec, false);
  assert.match(BASE.name, /\.invalid$/);
});

test('hypothetical DNSSEC-indexing modification is caught by negative gate', () => {
  const source = originals[0].source;
  const mutant = source.replace("add('dtype',doc.dtype);",
    "add('dtype',doc.dtype);add('dnssec',doc.dnssec);");
  assert.notEqual(mutant, source);
  assert.throws(() => examine(mutant), /DNS-state-only mutation unexpectedly changes/);
});

test('hypothetical removal of name indexing fails its positive control', () => {
  const source = originals[0].source;
  const mutant = source.replace("'user','name','display_name'", "'user','display_name'");
  assert.notEqual(mutant, source);
  assert.throws(() => examine(mutant), /name positive control/);
});

test('distinct source generations cannot be relabelled or substituted', () => {
  assert.throws(() => readIndex(hist, 'merged'), /Git blob mismatch/);
  assert.throws(() => readIndex(hist, 'future'), /unsupported search generation/);
});

test('input assertions preserve source and invented fixtures', () => {
  const snap = JSON.stringify(BASE);
  examine(originals[0].source);
  assert.equal(JSON.stringify(BASE), snap);
  assert.deepEqual(fieldNames({added: [{field: 'name'}], removed: [{field:'name'}]}), ['name']);
});

test('report is explicit about absent canonical admission, authorization and installed index', () => {
  const output = inspect({historical: hist, ...(merged ? {merged} : {})});
  assert.equal(output.claim_status, 'PINNED_RAW_SOURCE_EXPERIMENT');
  assert.equal(output.generations.historical.design_git_blob, PINS.historical);
  const limits = output.limits.join(' ');
  for (const term of ['not independently validated', 'installed index',
    'public/authenticated visibility', 'canonical durability', 'DNSSEC']) {
    assert.ok(limits.includes(term), term);
  }
});

test('rejects unknown, missing, or wrong pinned source path without unverified fallbacks', () => {
  for (const paths of [{}, {merged: hist}, {historical: hist, experimental: hist}]) {
    assert.throws(() => inspect(paths), /historical design required/);
  }
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'bk13-dns-'));
  try {
    const modified = path.join(temp, 'search.json');
    fs.writeFileSync(modified, fs.readFileSync(hist, 'utf8').replace('fname', 'fnamx'));
    assert.throws(() => inspect({historical: modified}), /Git blob mismatch/);
  } finally {fs.rmSync(temp, {recursive: true, force: true});}
});

test('CLI returns machine-readable source observations and a nonzero invalid-path status', () => {
  const cli = path.join(__dirname, 'domain_dns_search_boundary.js');
  const args = [cli, hist, ...(merged ? [merged] : [])];
  const good = spawnSync(process.execPath, args, {encoding: 'utf8', timeout: 5000});
  assert.equal(good.status, 0, good.stderr);
  assert.equal(JSON.parse(good.stdout).generations.historical.dns_state_only_raw_change, false);
  const bad = spawnSync(process.execPath, [cli, path.join(__dirname, 'missing.json')],
    {encoding: 'utf8', timeout: 5000});
  assert.notEqual(bad.status, 0);
  assert.equal(bad.stdout, '');
});
