'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const crypto = require('node:crypto');
// Exact callback strings from pinned server source/views/data.json at
// ce14c77ccd2f51f543410fdeef3d78fb9978b769 and merged ca6fdcbd....
const views = {
  total: "function(doc){if(!doc||!doc._id)return;if(doc._id.indexOf('_design/')===0)return;emit(null,1);}",
  count_by_dtype: "function(doc){if(!doc||!doc._id)return;if(doc._id.indexOf('_design/')===0)return;if(doc.dtype)emit(doc.dtype,1);}",
  count_by_dataset: "function(doc){if(!doc||!doc._id)return;if(doc._id.indexOf('_design/')===0)return;if(doc.dataset)emit(doc.dataset,1);}"
};
const hashes = {total:'c0cbc122',count_by_dtype:'0360a4d1',count_by_dataset:'dfb96a6d'};
function fnv(text) {
  let h=0x811c9dc5;
  for (const byte of Buffer.from(text, 'utf8')) h=Math.imul(h^byte,0x01000193)>>>0;
  return h.toString(16).padStart(8,'0');
}
function map(view,docs) {
  const records=[];
  const context=vm.createContext({emit:(key,value)=>records.push({key,value})});
  context.mapper=new vm.Script('('+views[view]+')').runInContext(context,{timeout:1000});
  for (const doc of docs) {
    context.document=structuredClone(doc);
    new vm.Script('mapper(document)').runInContext(context,{timeout:1000});
  }
  return records;
}
const documents=[
  {_id:'p-1',dtype:'person',dataset:'book-public'},
  {_id:'p-2',dtype:'person',dataset:'book-public'},
  {_id:'o-1',dtype:'org',dataset:'book-other-public'},
  {_id:'r-private',dtype:'relation',dataset:'book-private'},
  {_id:'_design/search',dtype:'relation',dataset:'book-private'}
];
const publicDatasets=new Set(['book-public','book-other-public']);
const publicDocs=documents.filter(d=>!d._id.startsWith('_design/') && publicDatasets.has(d.dataset));
const countBy=rows=>Object.fromEntries([...new Set(rows.map(x=>x.key))].map(k=>[
  k,rows.filter(x=>x.key===k).reduce((a,b)=>a+b.value,0)
]));
test('complete design source pin, when supplied by runner', t => {
  const file=process.env.STAR_SEARCH_STATS_DESIGN;
  if (!file) {t.skip('No full source checkout; only exact callbacks tested');return;}
  const bytes=fs.readFileSync(file);
  const blob=crypto.createHash('sha1').update(Buffer.from('blob '+bytes.length+'\0')).update(bytes).digest('hex');
  assert.equal(blob,'90389f5ef0f0812d851db9397fee1507969ac4bd');
  const actual=JSON.parse(bytes.toString('utf8'));
  for (const [name,source] of Object.entries(views)) {
    assert.equal(actual.views[name].map,source);
    assert.equal(actual.views[name].reduce,'_sum');
  }
});
test('real map callback fingerprints are unchanged', () => {
  for (const [name,source] of Object.entries(views)) assert.equal(fnv(source),hashes[name]);
});
test('total map counts both public and private records but not design documents', () => {
  assert.equal(map('total',documents).reduce((a,b)=>a+b.value,0),4);
  assert.equal(map('total',publicDocs).reduce((a,b)=>a+b.value,0),3);
});
test('dtype map retains a private relation in the global aggregate', () => {
  assert.deepEqual(countBy(map('count_by_dtype',documents)),{person:2,org:1,relation:1});
  assert.deepEqual(countBy(map('count_by_dtype',publicDocs)),{person:2,org:1});
});
test('dataset map could group data, but public stats route does not query this view', () => {
  assert.deepEqual(countBy(map('count_by_dataset',documents)),{
    'book-public':2,'book-other-public':1,'book-private':1
  });
});
test('removing only the private fixture removes exactly its aggregate contribution', () => {
  const subset=documents.filter(d=>d._id!=='r-private');
  assert.equal(map('total',subset).reduce((a,b)=>a+b.value,0),3);
  assert.equal(countBy(map('count_by_dtype',subset)).relation,undefined);
});
test('unscoped aggregate is not a public-search-completeness denominator', () => {
  assert.equal(map('total',documents).length-publicDocs.length,1);
});
