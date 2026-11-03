'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const {readIndex, gitBlob, PINS} = require('./projection_delta');
const {variation, inventory, inspect} = require('./field_footprint');

const historical = process.env.STAR_SEARCH_LAB_INDEX ||
  (process.env.STAR_SEARCH_LAB_SERVER &&
   path.join(process.env.STAR_SEARCH_LAB_SERVER, 'source/views/search.json'));
assert.ok(historical, 'STAR_SEARCH_LAB_SERVER or STAR_SEARCH_LAB_INDEX is required');
const source = readIndex(historical, 'historical');
const doc = {id:'org:fictional',rev:'r1',dtype:'org',dataset:'fictional',
  schemaVersion:'0.10.1',name:'Fictional Cooperative',organizationType:'cooperative',
  content:['alpha','beta'],notes:{reason:'fictional'},deleted:false};

test('original historical index bytes are Git-blob-attested', () => {
  assert.equal(gitBlob(fs.readFileSync(historical)), PINS.historical);
});
test('meaningful name edit produces changed raw name emissions', () => {
  const got = inventory(source, doc);
  const row = got.fields.find(x => x.field === 'name');
  assert.equal(row.effect, 'raw_emission_changed');
  assert.deepEqual(row.changed_emitted_fields, ['name']);
});
test('canonical organizationType omission is differentiated from unsupported values', () => {
  const got = inventory(source, doc);
  assert.equal(got.fields.find(x => x.field === 'organizationType').effect, 'no_raw_change');
  assert.equal(got.fields.find(x => x.field === 'notes').effect, 'not_probed');
});
test('array of primitives uses one changed element without changing its type', () => {
  assert.deepEqual(variation(['one','two']), ['one fictional-update','two']);
  assert.equal(inventory(source, doc).fields.find(x => x.field === 'content').effect,
    'raw_emission_changed');
});
test('scope and identity are explicitly unprobed', () => {
  const got = inventory(source, doc);
  for (const key of ['id','rev','dataset','dtype','schemaVersion']) {
    assert.deepEqual(got.fields.find(x => x.field === key),
      {field:key,effect:'not_probed',reason:'identity_or_scope_metadata'});
  }
});
test('structured, null, unsafe numeric and empty-array values are unprobed', () => {
  const x = inventory(source, {name:'Example',object:{x:1},nil:null,empty:[],unsafe:1.5});
  for (const key of ['object','nil','empty','unsafe']) {
    assert.equal(x.fields.find(row => row.field === key).effect,'not_probed');
  }
});
test('input is not changed and summary counts match classified fields', () => {
  const snap = JSON.stringify(doc), got=inventory(source, doc);
  assert.equal(JSON.stringify(doc),snap);
  assert.equal(got.counts.changed+got.counts.unchanged+got.counts.unprobed,
    got.fields.length);
});
test('malformed document and wrong Git-blob fail closed', () => {
  assert.throws(() => inventory(source, []), /JSON object/);
  assert.throws(() => inspect('merged',historical,doc),/Git blob mismatch/);
});
test('CLI executes attested source with coherent JSON output and failure status', () => {
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'bk13-footprint-'));
  try {
    const fixture=path.join(dir,'fictional.json');
    fs.writeFileSync(fixture,JSON.stringify(doc));
    const cli=path.join(__dirname,'field_footprint.js');
    const good=spawnSync(process.execPath,[cli,'historical',historical,fixture],
      {encoding:'utf8',timeout:5000});
    assert.equal(good.status,0,good.stderr);
    const result=JSON.parse(good.stdout);
    assert.equal(result.fields.find(x=>x.field==='name').effect,'raw_emission_changed');
    assert.match(result.evidence_boundary,/not stored/);
    const bad=spawnSync(process.execPath,[cli,'merged',historical,fixture],
      {encoding:'utf8',timeout:5000});
    assert.notEqual(bad.status,0);
    assert.equal(bad.stdout,'');
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
});
