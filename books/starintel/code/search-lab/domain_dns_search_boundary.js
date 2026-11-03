#!/usr/bin/env node
'use strict';
// Fixed, fictional 0.10.1 Domain-shaped example. No DNS, HTTP, or document writes.
const path = require('node:path');
const {readIndex, emissions, difference, PINS} = require('./projection_delta');

const BASE = Object.freeze({
  id: 'domain:fictional:lab.example.invalid',
  dataset: 'book-synthetic',
  dtype: 'domain',
  schemaVersion: '0.10.1',
  name: 'lab.example.invalid',
  dnssec: false,
  dnsRecords: [{type: 'A', value: '192.0.2.10'}],
  mxRecords: [{priority: 10, exchange: 'mail.example.invalid'}],
  txtRecords: ['fictional verification text'],
  nameservers: ['ns1.example.invalid'],
  registrar: 'Example Registry',
});

function fixtures() {
  // All reserved example strings; not evidence of any actual resolver answer.
  const before = structuredClone(BASE);
  const changedDns = {
    ...structuredClone(BASE),
    dnssec: true,
    dnsRecords: [{type: 'AAAA', value: '2001:db8::10'}],
    mxRecords: [{priority: 20, exchange: 'other.example.invalid'}],
    txtRecords: ['changed fictional verification text'],
    nameservers: ['ns2.example.invalid'],
    registrar: 'Another Fictional Registry',
  };
  const changedName = {...structuredClone(BASE), name: 'renamed.example.invalid'};
  const changedScope = {...structuredClone(BASE), dataset: 'book-other-synthetic', tenant_id: 'other'};
  return {before, changedDns, changedName, changedScope};
}

function fieldNames(delta) {
  return [...new Set([...delta.added, ...delta.removed].map(x => x.field))].sort();
}

function examine(source) {
  const {before, changedDns, changedName, changedScope} = fixtures();
  const initial = emissions(source, before);
  const dnsDelta = difference(initial, emissions(source, changedDns));
  const nameDelta = difference(initial, emissions(source, changedName));
  const scopeDelta = difference(initial, emissions(source, changedScope));
  const indexed = fieldNames(nameDelta);
  const scopeFields = fieldNames(scopeDelta);
  const omitted = fieldNames(dnsDelta);
  if (dnsDelta.raw_emissions_changed) {
    throw new Error(`DNS-state-only mutation unexpectedly changes raw search emissions: ${omitted.join(',')}`);
  }
  if (indexed.length !== 1 || indexed[0] !== 'name') {
    throw new Error('synthetic Domain name positive control did not change the name emission');
  }
  if (scopeFields.join(',') !== 'dataset,tenant_id') {
    throw new Error('synthetic dataset/tenant scope control did not change both indexed fields');
  }
  if (!initial.some(x => x.field === 'dtype' && x.value === 'domain') ||
      !initial.some(x => x.field === 'name' && x.value === BASE.name)) {
    throw new Error('the original index did not emit synthetic Domain identity fields');
  }
  return {
    name_change_fields: indexed,
    dns_state_only_raw_change: dnsDelta.raw_emissions_changed,
    dns_state_only_emission_delta_count: dnsDelta.added.length + dnsDelta.removed.length,
    scope_change_fields: scopeFields,
  };
}

function inspect(paths) {
  if (!paths || typeof paths !== 'object' || Array.isArray(paths) ||
      !Object.hasOwn(paths, 'historical') ||
      Object.keys(paths).some(name => !Object.hasOwn(PINS, name))) {
    throw new Error('historical design required; optional merged design');
  }
  const generations = {};
  for (const generation of ['historical', 'merged']) {
    if (!Object.hasOwn(paths, generation)) continue;
    const source = readIndex(paths[generation], generation);
    generations[generation] = {
      design_git_blob: PINS[generation],
      ...examine(source),
    };
  }
  return {
    claim_status: 'PINNED_RAW_SOURCE_EXPERIMENT',
    schema_authority: 'org.starintel/core@1 0.10.1 (field names inspected; example not SDK-validated)',
    synthetic_domain: BASE.name,
    generations,
    limits: [
      'The example is Domain-shaped, not independently validated or ingested.',
      'Only the original pinned JavaScript index() callbacks and stored raw emissions execute.',
      'The missing DNS emission is not a statement about domain resolution, DNSSEC, WHOIS, or source freshness.',
      'Nothing here establishes an installed index, public/authenticated visibility, authorization or canonical durability.',
    ],
  };
}

function main(args) {
  if (args.length < 1 || args.length > 2) {
    throw new Error('usage: node domain_dns_search_boundary.js HISTORICAL_SEARCH_JSON [MERGED_SEARCH_JSON]');
  }
  const paths = {historical: path.resolve(args[0])};
  if (args[1]) paths.merged = path.resolve(args[1]);
  process.stdout.write(JSON.stringify(inspect(paths), null, 2) + '\n');
}

if (require.main === module) {
  try { main(process.argv.slice(2)); }
  catch (error) { process.stderr.write(error.message + '\n'); process.exitCode = 1; }
}
module.exports = {BASE, fixtures, fieldNames, examine, inspect, main};
