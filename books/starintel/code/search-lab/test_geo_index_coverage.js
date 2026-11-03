'use strict';
// Executed source behavior only: a full-text index is not a geospatial index.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const server = process.env.STAR_SEARCH_LAB_SERVER;
assert.ok(server, 'STAR_SEARCH_LAB_SERVER must name a pinned server checkout');
const source = path.join(server, 'source/views/search.json');
const bytes = fs.readFileSync(source);
const gitBlob = crypto.createHash('sha1')
  .update(Buffer.from('blob ' + bytes.length + '\0')).update(bytes).digest('hex');
const expectedBlob = '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a';
assert.equal(gitBlob, expectedBlob, 'must run exact historical index');
const fts = JSON.parse(bytes.toString('utf8')).indexes.fts;

// The fields and string-number types correspond to the pinned generated
// StarLang 0.10.1 $defs.GeoPoint schema. This test does NOT run SDK validation.
const point = Object.freeze({
  id: 'geo:book-square', dataset: 'book-synthetic', dtype: 'geo',
  schemaVersion: '0.10.1', geometryType: 'point',
  latitude: '39.9612', longitude: '-83.0007', geohash: 'synthetic-geohash',
  placeName: 'Fictional Civic Square'
});
function events(document) {
  const calls = [];
  const ctx = vm.createContext({index: (field, value, options) => {
    calls.push({field, value, store: options && options.store === true});
  }});
  ctx.fn = new vm.Script('(' + fts.index + ')').runInContext(ctx, {timeout: 1000});
  ctx.doc = structuredClone(document);
  new vm.Script('fn(doc)').runInContext(ctx, {timeout: 1000});
  return calls;
}
function values(document, field) {
  return events(document).filter(x=>x.field===field).map(x=>x.value);
}
const spatialFields = ['latitude','longitude','geohash','geometryType','placeName'];

test('original historical Git blob, not a mock index', () => {
  assert.equal(gitBlob, expectedBlob);
  assert.equal(fts.analyzer.fields.dataset, 'keyword');
});
test('geospatial input still emits meaningful ordinary text-scope metadata', () => {
  assert.deepEqual(values(point,'dataset'),['book-synthetic']);
  assert.deepEqual(values(point,'dtype'),['geo']);
  assert.deepEqual(values(point,'tenant_id'),['default']);
  assert.ok(events(point).every(x=>x.store));
});
test('historical full-text index does not select canonical geographic properties', () => {
  for (const name of spatialFields) {
    assert.deepEqual(values(point,name),[], 'unexpected projected field: '+name);
  }
});
test('different coordinates and place descriptions have indistinguishable FTS emissions', () => {
  const changed = {...point,latitude:'40.1000',longitude:'-82.7000',
    geohash:'different',placeName:'A Different Fictional Place'};
  assert.notEqual(point.latitude,changed.latitude);
  assert.deepEqual(events(point),events(changed));
});
test('a different dataset produces distinguishable index emissions', () => {
  const changed = {...point,dataset:'book-public'};
  assert.notDeepEqual(events(point),events(changed));
  assert.deepEqual(values(changed,'dataset'),['book-public']);
});
test('ordinary content text is indexable but does not produce spatial coordinates', () => {
  const described = {...point,content:'Synthetic landmark mention'};
  assert.deepEqual(values(described,'content'),['Synthetic landmark mention']);
  for (const name of spatialFields) assert.deepEqual(values(described,name),[]);
});
test('these callbacks do not validate required GeoPoint coordinates', () => {
  const incomplete = {...point}; delete incomplete.latitude; delete incomplete.longitude;
  assert.deepEqual(events(incomplete),events(point));
});
