'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const {PINS, gitBlob, readIndex, emissions, difference, inspect} = require('./projection_delta');

const historical = process.env.STAR_SEARCH_LAB_INDEX ||
  (process.env.STAR_SEARCH_LAB_SERVER &&
   path.join(process.env.STAR_SEARCH_LAB_SERVER, 'source/views/search.json'));
assert.ok(historical, 'STAR_SEARCH_LAB_INDEX or STAR_SEARCH_LAB_SERVER is required');
const CLI = path.join(__dirname, 'projection_delta.js');
const source = readIndex(historical, 'historical');
const org = {id:'org:synthetic',schemaVersion:'0.10.1',dtype:'org',
  dataset:'book-synthetic',name:'Example Cooperative'};

function keys(rows) { return rows.map(row => [row.field,row.value]); }

// The generated chapter exercise exercises the unaltered source callback,
// including a check for historically missing canonical fields.
test('Git blob attests original historical index function', () => {
  const bytes = fs.readFileSync(historical);
  assert.equal(gitBlob(bytes), PINS.historical);
});
test('unchanged input produces no changes', () => {
  const got = inspect('historical', historical, org, structuredClone(org));
  assert.equal(got.raw_emissions_changed, false);
  assert.equal(got.reordered_only, false);
  assert.deepEqual(got.added, []);
  assert.deepEqual(got.removed, []);
});
test('changing canonical name produces one removed and one added raw emission', () => {
  const got = inspect('historical', historical, org, {...org,name:'Updated Cooperative'});
  assert.deepEqual(got.removed, [{field:'name',value:'Example Cooperative',count:1}]);
  assert.deepEqual(got.added, [{field:'name',value:'Updated Cooperative',count:1}]);
  assert.equal(got.raw_emissions_changed, true);
});
test('changing canonical organizationType does not appear as a raw emission', () => {
  const before={...org,organizationType:'cooperative'};
  const after={...before,organizationType:'nonprofit'};
  const got=inspect('historical',historical,before,after);
  assert.equal(got.raw_emissions_changed,false);
  assert.ok(!keys(emissions(source,before)).some(([field])=>field==='organizationType'));
});
test('duplicate values are counted, never collapsed into a set', () => {
  const before={...org,content:['one','one','two']};
  const after={...org,content:['one','two']};
  const got=inspect('historical',historical,before,after);
  assert.deepEqual(got.removed,[{field:'content',value:'one',count:1}]);
  assert.deepEqual(got.added,[]);
});
test('order-only changes are distinguished from emission multiset changes', () => {
  const before={...org,content:['alpha','beta']};
  const after={...org,content:['beta','alpha']};
  const got=inspect('historical',historical,before,after);
  assert.equal(got.reordered_only,true);
  assert.deepEqual(got.added,[]);
  assert.deepEqual(got.removed,[]);
});
test('comparison does not change the original JSON objects', () => {
  const before=structuredClone(org), after={...org,name:'Updated'};
  const serialized=[JSON.stringify(before),JSON.stringify(after)];
  inspect('historical',historical,before,after);
  assert.deepEqual([JSON.stringify(before),JSON.stringify(after)],serialized);
});
test('invalid source bytes fail closed before running index code', () => {
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'bk13-projection-delta-'));
  try {
    const altered=path.join(dir,'search.json');
    fs.writeFileSync(altered,fs.readFileSync(historical,'utf8').replace('_design/search','_design/altered'));
    assert.throws(()=>inspect('historical',altered,org,org),/Git blob mismatch/);
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
});
test('CLI uses the pinned source and JSON files, and rejects wrong source', () => {
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'bk13-projection-cli-'));
  try {
    const before=path.join(dir,'before.json'),after=path.join(dir,'after.json');
    fs.writeFileSync(before,JSON.stringify(org));
    fs.writeFileSync(after,JSON.stringify({...org,name:'CLI Example'}));
    const good=spawnSync(process.execPath,[CLI,'historical',historical,before,after],
      {encoding:'utf8',timeout:5000});
    assert.equal(good.status,0,good.stderr);
    const got=JSON.parse(good.stdout);
    assert.equal(got.added[0].value,'CLI Example');
    assert.match(got.evidence_boundary,/Not canonical validation/);
    const bad=spawnSync(process.execPath,[CLI,'merged',historical,before,after],
      {encoding:'utf8',timeout:5000});
    assert.notEqual(bad.status,0);
    assert.match(bad.stderr,/Git blob mismatch/);
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
});
test('malformed non-object input fails without generating a success report', () => {
  assert.throws(()=>emissions(source,['not a document']),/JSON object/);
});
