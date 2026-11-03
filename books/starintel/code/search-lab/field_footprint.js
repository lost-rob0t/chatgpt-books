#!/usr/bin/env node
'use strict';
// Field-level mutation probe of exact source-pinned raw FTS emissions.
// Synthetic inputs only: NOT canonical validation, Lucene or authorization.
const fs = require('node:fs');
const {readIndex, emissions, difference, PINS} = require('./projection_delta');

const RESERVED = new Set(['id', '_id', 'rev', '_rev', 'dtype', 'dataset',
  'schemaVersion', 'tenant', 'tenant_id', 'visibility', 'accessControl', 'deleted']);

function variation(value) {
  if (typeof value === 'string') return value + ' fictional-update';
  if (typeof value === 'boolean') return !value;
  if (typeof value === 'number' && Number.isSafeInteger(value) &&
      Number.isSafeInteger(value + 1)) return value + 1;
  if (Array.isArray(value)) {
    const i = value.findIndex(item => item !== null &&
      (typeof item === 'string' || typeof item === 'boolean' ||
        (typeof item === 'number' && Number.isSafeInteger(item) &&
         Number.isSafeInteger(item + 1))));
    if (i === -1) return undefined;
    const changed = structuredClone(value);
    changed[i] = variation(changed[i]);
    return changed;
  }
  return undefined;
}

function inventory(indexSource, document) {
  if (document === null || typeof document !== 'object' || Array.isArray(document)) {
    throw new Error('synthetic input must be a JSON object');
  }
  const before = emissions(indexSource, document);
  const fields = [];
  for (const key of Object.keys(document).sort()) {
    if (RESERVED.has(key)) {
      fields.push({field: key, effect: 'not_probed', reason: 'identity_or_scope_metadata'});
      continue;
    }
    const changedValue = variation(document[key]);
    if (changedValue === undefined) {
      fields.push({field: key, effect: 'not_probed', reason: 'unsupported_value_shape'});
      continue;
    }
    const changed = {...document, [key]: changedValue};
    const delta = difference(before, emissions(indexSource, changed));
    const emitted = [...new Set([...delta.added, ...delta.removed]
      .map(row => row.field))].sort();
    fields.push({field: key,
      effect: delta.raw_emissions_changed ? 'raw_emission_changed' : 'no_raw_change',
      changed_emitted_fields: emitted,
      reordered_only: delta.reordered_only});
  }
  return {fields,
    counts: {
      changed: fields.filter(x => x.effect === 'raw_emission_changed').length,
      unchanged: fields.filter(x => x.effect === 'no_raw_change').length,
      unprobed: fields.filter(x => x.effect === 'not_probed').length,
    }};
}

function inspect(generation, indexPath, document) {
  const source = readIndex(indexPath, generation);
  return {
    generation, index_source_git_blob: PINS[generation],
    ...inventory(source, document),
    evidence_boundary: 'Only single-field synthetic perturbations and pinned raw index() emissions; unchanged does not mean absent, unindexed, unauthorized, or not stored.',
  };
}

function main(args) {
  if (args.length !== 3) {
    throw new Error('usage: node field_footprint.js historical|merged PINNED_SEARCH_JSON SYNTHETIC_DOCUMENT_JSON');
  }
  const [generation, indexPath, documentPath] = args;
  const document = JSON.parse(fs.readFileSync(documentPath, 'utf8'));
  process.stdout.write(JSON.stringify(inspect(generation, indexPath, document), null, 2) + '\n');
}
if (require.main === module) {
  try { main(process.argv.slice(2)); }
  catch (error) { process.stderr.write(error.message + '\n'); process.exitCode = 1; }
}
module.exports = {RESERVED, variation, inventory, inspect, main};
