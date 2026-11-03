#!/usr/bin/env node
'use strict';
// Compare observable index() emissions from two synthetic documents.
// This is NOT a CouchDB, Clouseau, authorization, or canonical-validity test.
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');

const PINS = Object.freeze({
  historical: '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged: 'dd6336f3047982db2f0e3615fed1413ed1e58e13',
});

function gitBlob(bytes) {
  return crypto.createHash('sha1')
    .update(Buffer.from(`blob ${bytes.length}\0`)).update(bytes).digest('hex');
}

function readIndex(file, generation) {
  if (!Object.hasOwn(PINS, generation)) throw new Error('unsupported search generation');
  const bytes = fs.readFileSync(file);
  const sha = gitBlob(bytes);
  if (sha !== PINS[generation]) throw new Error(`search index source Git blob mismatch: ${sha}`);
  const design = JSON.parse(bytes.toString('utf8'));
  if (design._id !== '_design/search' || typeof design.indexes?.fts?.index !== 'string') {
    throw new Error('pinned search design is malformed');
  }
  return design.indexes.fts.index;
}

function emissions(indexSource, document) {
  if (document === null || Array.isArray(document) || typeof document !== 'object') {
    throw new Error('synthetic input must be a JSON object');
  }
  const rows = [];
  // Match the course capture's emission ceiling; not a service limit.
  const MAX_EMISSIONS = 2048;
  const context = vm.createContext({index(field, value, options) {
    if (rows.length >= MAX_EMISSIONS) throw new Error('course projection emission budget exceeded');
    if (typeof field !== 'string' || !field ||
        !['string', 'number', 'boolean'].includes(typeof value) || options?.store !== true) {
      throw new Error('unexpected pinned index emission');
    }
    rows.push({field, value});
  }});
  context.document = structuredClone(document);
  context.indexer = new vm.Script(`(${indexSource})`).runInContext(context, {timeout: 1000});
  new vm.Script('indexer(document)').runInContext(context, {timeout: 1000});
  return rows;
}

function countRows(rows) {
  const totals = new Map();
  for (const entry of rows) {
    const key = JSON.stringify([entry.field, entry.value]);
    const current = totals.get(key);
    if (current) current.count += 1;
    else totals.set(key, {...entry, count: 1});
  }
  return totals;
}

function difference(before, after) {
  const left = countRows(before), right = countRows(after);
  const added = [], removed = [];
  for (const key of [...new Set([...left.keys(), ...right.keys()])].sort()) {
    const a = left.get(key)?.count ?? 0;
    const b = right.get(key)?.count ?? 0;
    if (b > a) added.push({...right.get(key), count: b - a});
    if (a > b) removed.push({...left.get(key), count: a - b});
  }
  const reorderedOnly = added.length === 0 && removed.length === 0 &&
    JSON.stringify(before) !== JSON.stringify(after);
  return {
    before_count: before.length,
    after_count: after.length,
    added, removed, reordered_only: reorderedOnly,
    raw_emissions_changed: added.length > 0 || removed.length > 0 || reorderedOnly,
  };
}

function inspect(generation, indexPath, before, after) {
  const source = readIndex(indexPath, generation);
  return {
    generation,
    index_source_git_blob: PINS[generation],
    ...difference(emissions(source, before), emissions(source, after)),
    evidence_boundary: 'Pinned raw JavaScript index() calls only. Not canonical validation, installed index, authorized search, ranking, or durable evidence.',
  };
}

function main(args) {
  if (args.length !== 4) {
    throw new Error('usage: node projection_delta.js historical|merged PINNED_SEARCH_JSON BEFORE_JSON AFTER_JSON');
  }
  const [generation, indexPath, beforePath, afterPath] = args;
  const before = JSON.parse(fs.readFileSync(beforePath, 'utf8'));
  const after = JSON.parse(fs.readFileSync(afterPath, 'utf8'));
  process.stdout.write(JSON.stringify(inspect(generation, indexPath, before, after), null, 2) + '\n');
}

if (require.main === module) {
  try { main(process.argv.slice(2)); }
  catch (error) { process.stderr.write(`${error.message}\n`); process.exitCode = 1; }
}
module.exports = {PINS, gitBlob, readIndex, emissions, difference, inspect, main};
