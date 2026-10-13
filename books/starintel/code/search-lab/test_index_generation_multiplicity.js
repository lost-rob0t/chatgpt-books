'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {spawnSync} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const files = process.argv.slice(2);
assert.equal(files.length, 2, 'usage: node test_index_generation_multiplicity.js HISTORICAL MERGED');
const comparator = process.env.INDEX_COMPARISON_JS || path.join(__dirname, 'compare_index_generations.js');
function execute(...args) {
  return spawnSync(process.execPath, [comparator, ...args], {encoding:'utf8', timeout:5000});
}
const run = execute(...files);

// Assertions test the real pinned index callbacks invoked by the comparator.
test('the source-pinned comparator runs without exceptions', () => {
  assert.equal(run.status, 0, run.stderr);
  assert.equal(JSON.parse(run.stdout).status, 'PASS');
});
test('emission totals count repeated fields, not unique field names', () => {
  assert.equal(run.status, 0, run.stderr);
  const body = JSON.parse(run.stdout);
  assert.equal(body.historical_emissions, 14);
  assert.equal(body.merged_emissions, 18);
  assert.equal(body.merged_emissions-body.historical_emissions, 4);
});
test('three separately indexed content values remain ordered', () => {
  const body = JSON.parse(run.stdout);
  assert.deepEqual(body.shared_multivalue_emissions.content, ['alpha','beta','gamma']);
});
test('four sources values are retained rather than overwritten', () => {
  const body = JSON.parse(run.stdout);
  assert.deepEqual(body.shared_multivalue_emissions.sources,
    ['Source A','https://a.invalid','Source B','https://b.invalid']);
});
test('both source index blobs remain SHA-pinned', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(),'bk13-index-multi-'));
  try {
    const altered = path.join(tmp,'altered.json');
    const original = fs.readFileSync(files[0], 'utf8');
    fs.writeFileSync(altered,original.replace('"_id":"_design/search"','"_id":"_design/altered"'));
    const bad = execute(altered,files[1]);
    assert.notEqual(bad.status,0);
    assert.match(bad.stderr,/Source index Git blob mismatch/);
  } finally {
    fs.rmSync(tmp,{recursive:true,force:true});
  }
});
