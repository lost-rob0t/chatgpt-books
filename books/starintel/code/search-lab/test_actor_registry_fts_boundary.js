'use strict';
// Chapter 15: document FTS is not semantic actor/service discovery.
// Executes only the original, Git-blob-attested index callbacks. The Lisp
// catalog source is inspected, NOT run; no HTTP/SDK/Clouseau behavior is claimed.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

const INDEX_PINS = Object.freeze({
  historical: '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged: 'dd6336f3047982db2f0e3615fed1413ed1e58e13',
});
const REGISTRY_PIN = 'd4fb16570c9e7b40c40d2c3c01124fa83855e8fe';
const paths = [
  ['historical', process.env.STAR_SEARCH_ACTOR_HISTORICAL_DESIGN],
  ['merged', process.env.STAR_SEARCH_ACTOR_MERGED_DESIGN],
];
if (!paths[0][1]) {
  throw new Error('Pinned historical design is required');
}
function blobSHA(raw) {
  return crypto.createHash('sha1')
    .update(`blob ${raw.length}\0`).update(raw).digest('hex');
}
function pinnedSource(path, sha) {
  const raw = fs.readFileSync(path);
  assert.equal(blobSHA(raw), sha, 'exact Git blob required');
  return raw.toString('utf8');
}
function indexFn(generation, path) {
  const design = JSON.parse(pinnedSource(path, INDEX_PINS[generation]));
  assert.equal(design._id, '_design/search');
  let source = design.indexes.fts.index;
  if (process.env.STAR_SEARCH_ACTOR_CONTROL === 'mutated') {
    const anchor = "add('dtype',doc.dtype);";
    assert.equal(source.split(anchor).length, 2);
    source = source.replace(anchor, anchor + "add('actor',doc.actor);");
  }
  return source;
}
function emissions(source, document) {
  const out = [];
  const context = vm.createContext({index(name, value, options) {
    out.push({name, value, stored: options?.store === true});
  }});
  context.handler = new vm.Script(`(${source})`).runInContext(context, {timeout: 1000});
  context.document = structuredClone(document);
  new vm.Script('handler(document)').runInContext(context, {timeout: 1000});
  return out;
}
const canonicalShape = Object.freeze({
  id: 'starintel:actor-manifest:fictional-enricher',
  rev: 'fictional-r1',
  schemaVersion: '0.10.1',
  dataset: 'fictional-lab',
  dtype: 'actor-manifest',
  actor: 'fictional-enricher',
  accepts: ['fictional-input-v1'],
  produces: ['fictional-output-v1'],
  capabilities: ['fictional-transform'],
});
for (const [generation, path] of paths) {
  if (!path) continue;
  const callback = indexFn(generation, path);
  test(`${generation}: canonical ActorManifest name is not an FTS key`, () => {
    assert.deepEqual(emissions(callback, canonicalShape).map(row => row.name),
      ['tenant_id', 'dataset', 'dtype']);
    assert.equal(emissions(callback, canonicalShape).some(row => row.name === 'actor'), false);
  });
  test(`${generation}: accepted and produced contracts are not search facets`, () => {
    const out = emissions(callback, canonicalShape);
    assert.equal(out.some(row => ['accepts', 'produces'].includes(row.name)), false);
  });
  test(`${generation}: capabilities are not a catalog lookup through FTS`, () => {
    assert.equal(emissions(callback, canonicalShape)
      .some(row => row.name === 'capabilities'), false);
  });
  test(`${generation}: changing actor and capability has no raw FTS effect`, () => {
    assert.deepEqual(emissions(callback, canonicalShape), emissions(callback, {
      ...canonicalShape, actor: 'different-fictional-actor',
      capabilities: ['different-fictional-capability'],
      accepts: ['different-input'], produces: ['different-output'],
    }));
  });
  test(`${generation}: dataset and dtype positive controls affect the index`, () => {
    const baseline = emissions(callback, canonicalShape);
    assert.notDeepEqual(baseline, emissions(callback, {...canonicalShape, dataset: 'other-fixture'}));
    assert.notDeepEqual(baseline, emissions(callback, {...canonicalShape, dtype: 'other-fixture'}));
    assert.ok(baseline.every(row => row.stored));
  });
}
if (process.env.STAR_SEARCH_ACTOR_REGISTRY) {
const registry = pinnedSource(process.env.STAR_SEARCH_ACTOR_REGISTRY, REGISTRY_PIN);
function section(from, to) {
  const start = registry.indexOf(`(defun ${from}`);
  assert.notEqual(start, -1, 'pinned source form exists');
  const finish = to ? registry.indexOf(`(defun ${to}`, start + 1) : registry.length;
  assert.notEqual(finish, -1, 'next pinned source form exists');
  return registry.slice(start, finish);
}
test('semantic catalog source requires explicit operator visibility', () => {
  const s = section('actor-registry-public-entries', 'actor-registry-document');
  assert.match(s, /actor-registry-entry-operator-visible-p/);
  assert.match(s, /effective-runtime-observation/);
});
test('semantic catalog source exposes capabilities and separate status/ready', () => {
  const s = section('actor-registry-entry-public-object', 'actor-registry-public-entries');
  for (const key of ['"resourceUri"', '"semantic"', '"accepts"', '"produces"',
    '"capabilities"', '"status"', '"ready"', '"provenance"']) {
    assert.ok(s.includes(key), `source contains ${key}`);
  }
});
test('semantic catalog source is distinct from canonical corpus index', () => {
  const s = section('actor-registry-document');
  assert.match(s, /starintel-actor-registry-v1/);
  assert.match(s, /actor-registry-public-entries/);
});

}
