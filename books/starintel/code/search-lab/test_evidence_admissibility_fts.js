#!/usr/bin/env node
'use strict';

// Exact pinned FTS callback emissions on fictional EvidenceRecord-shaped data.
// These tests do NOT execute StarLang admission, HTTP authorization, installed
// CouchDB/Clouseau, canonical read-back, or evidence-integrity verification.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');

const PINS = Object.freeze({
  historical: '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged: 'dd6336f3047982db2f0e3615fed1413ed1e58e13',
});
const root = process.env.STAR_SEARCH_LAB_SERVER;
const historical = process.env.STAR_SEARCH_EVIDENCE_HISTORICAL_DESIGN ||
  (root && path.join(root, 'source/views/search.json'));
if (!historical) throw new Error('provide exact historical search design');
const generations = [['historical', historical]];
if (process.env.STAR_SEARCH_EVIDENCE_MERGED_DESIGN) {
  generations.push(['merged', process.env.STAR_SEARCH_EVIDENCE_MERGED_DESIGN]);
}

function gitBlob(bytes) {
  return crypto.createHash('sha1')
    .update('blob ' + bytes.length + '\0').update(bytes).digest('hex');
}
function sourceFor(generation, filename, mutant = false) {
  const bytes = fs.readFileSync(filename);
  assert.equal(gitBlob(bytes), PINS[generation], 'pinned Git blob mismatch');
  const design = JSON.parse(bytes.toString('utf8'));
  assert.equal(design._id, '_design/search');
  assert.equal(design.language, 'javascript');
  let source = design.indexes.fts.index;
  if (mutant || process.env.STAR_SEARCH_EVIDENCE_RED === '1') {
    const anchor = "add('dtype',doc.dtype);";
    assert.equal(source.split(anchor).length, 2, 'mutation anchor changed');
    source = source.replace(anchor, anchor +
      "add('verificationStatus',doc.verificationStatus);");
  }
  return source;
}
function emit(source, doc) {
  const rows = [];
  const context = vm.createContext({
    index(field, value, opts) {
      assert.equal(opts?.store, true);
      assert.ok(rows.length < 2048, 'bounded raw emission capture');
      rows.push([field, value]);
    },
  });
  context.document = structuredClone(doc);
  context.indexer = new vm.Script('(' + source + ')')
    .runInContext(context, {timeout: 1000});
  new vm.Script('indexer(document)').runInContext(context, {timeout: 1000});
  return rows;
}
function fictionalEvidence(overrides = {}) {
  return {
    id: 'starintel:evidence-record:fictional-001',
    rev: 'r1-fictional',
    schemaVersion: '0.10.1',
    dtype: 'evidence-record',
    dataset: 'book-synthetic',
    claim: 'A synthetic beacon generated one lab event',
    verificationStatus: 'unverified',
    admissibilityStatus: 'pending-review',
    status: 'pending',
    contentHash: 'a'.repeat(64),
    chainOfCustody: [{actor: 'fictional-collector', action: 'record'}],
    claimIds: ['starintel:claim:fictional-001'],
    collectionMethod: 'synthetic-demo',
    provenance: {source: 'fictional fixture'},
    ...overrides,
  };
}
function values(rows, key) {
  return rows.filter(([field]) => field === key).map(([, value]) => value);
}

for (const [generation, filename] of generations) {
  const source = sourceFor(generation, filename);
  test(generation + ': immutable Server design and runnable callback', () => {
    assert.ok(source.startsWith('function(doc)'));
  });
  test(generation + ': lexical claim and scope/type are emitted', () => {
    assert.deepEqual(emit(source, fictionalEvidence()), [
      ['tenant_id', 'default'], ['dataset', 'book-synthetic'],
      ['dtype', 'evidence-record'],
      ['claim', 'A synthetic beacon generated one lab event'],
    ]);
  });
  test(generation + ': verification and admissibility statuses are absent', () => {
    const base = emit(source, fictionalEvidence());
    const changed = emit(source, fictionalEvidence({
      verificationStatus: 'verified',
      admissibilityStatus: 'rejected', status: 'closed',
    }));
    assert.deepEqual(changed, base);
    for (const field of ['verificationStatus', 'admissibilityStatus', 'status']) {
      assert.deepEqual(values(base, field), [], field);
    }
  });
  test(generation + ': chain/hash/method/claim references are absent', () => {
    const base = emit(source, fictionalEvidence());
    const changed = emit(source, fictionalEvidence({
      contentHash: 'b'.repeat(64),
      chainOfCustody: [{actor: 'different-fictional-collector'}],
      claimIds: ['starintel:claim:fictional-999'],
      collectionMethod: 'alternate-synthetic-demo',
      provenance: {source: 'different fictional fixture'},
    }));
    assert.deepEqual(changed, base);
    for (const field of ['contentHash', 'chainOfCustody', 'claimIds',
      'collectionMethod', 'provenance']) {
      assert.deepEqual(values(base, field), [], field);
    }
  });
  test(generation + ': lexical claim mutation is a positive control', () => {
    const changed = emit(source, fictionalEvidence({
      claim: 'A different synthetic beacon generated one lab event',
    }));
    assert.notDeepEqual(changed, emit(source, fictionalEvidence()));
    assert.deepEqual(values(changed, 'claim'),
      ['A different synthetic beacon generated one lab event']);
  });
  test(generation + ': dataset change is a separate scope-field control', () => {
    const changed = emit(source, fictionalEvidence({dataset: 'book-other'}));
    assert.deepEqual(values(changed, 'dataset'), ['book-other']);
    assert.notDeepEqual(changed, emit(source, fictionalEvidence()));
  });
  test(generation + ': deletion of claim leaves no lexical claim field', () => {
    const doc = fictionalEvidence();
    delete doc.claim;
    const emitted = emit(source, doc);
    assert.deepEqual(values(emitted, 'claim'), []);
    assert.deepEqual(values(emitted, 'dataset'), ['book-synthetic']);
  });
  test(generation + ': synthetic verification-index mutant is detectable', () => {
    const mutant = sourceFor(generation, filename, true);
    const a = emit(mutant, fictionalEvidence({verificationStatus: 'unverified'}));
    const b = emit(mutant, fictionalEvidence({verificationStatus: 'verified'}));
    assert.notDeepEqual(a, b);
    assert.deepEqual(values(b, 'verificationStatus'), ['verified']);
  });
}
