'use strict';
// Original pinned StarIntel Server index callbacks; NOT Lucene or authorization.
// Canonical 0.10.1 Org/Alert/Event define labels, tags, topics string arrays.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const PINS = {historical:'0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged:'dd6336f3047982db2f0e3615fed1413ed1e58e13'};
function load(file, generation) {
  const bytes=fs.readFileSync(file);
  const hash=crypto.createHash('sha1').update(Buffer.from('blob '+bytes.length+'\0'))
    .update(bytes).digest('hex');
  assert.equal(hash,PINS[generation],generation+' Git blob drift');
  const design=JSON.parse(bytes.toString('utf8'));
  assert.equal(design._id,'_design/search');
  return design.indexes.fts.index;
}
function capture(source,doc) {
  const rows=[];
  const scope=vm.createContext({index:(field,value,opts)=>
    rows.push({field,value,stored:opts?.store===true})});
  scope.doc=structuredClone(doc);
  scope.fn=new vm.Script('('+source+')').runInContext(scope,{timeout:1000});
  new vm.Script('fn(doc)').runInContext(scope,{timeout:1000});
  return rows;
}
function sample() {return {id:'org:fictional',rev:'r1',schemaVersion:'0.10.1',
  dataset:'book-synthetic',dtype:'org',tenant_id:'default',
  name:'Example Cooperative',content:'Public workshop minutes',
  labels:['reviewed'],tags:['robotics'],topics:['education']};}
function values(rows,key) {return rows.filter(r=>r.field===key).map(r=>r.value);}
const historical=process.env.STAR_SEARCH_TAXONOMY_HISTORICAL_DESIGN ||
  (process.env.STAR_SEARCH_LAB_SERVER && path.join(
    process.env.STAR_SEARCH_LAB_SERVER,'source/views/search.json'));
assert.ok(historical,'set STAR_SEARCH_LAB_SERVER or historical design file');
const inputs=[['historical',historical]];
if(process.env.STAR_SEARCH_TAXONOMY_MERGED_DESIGN)
  inputs.push(['merged',process.env.STAR_SEARCH_TAXONOMY_MERGED_DESIGN]);
for(const [generation,file] of inputs) {
  const source=load(file,generation),doc=sample(),base=capture(source,doc);
  test(generation+': positive fields and absent taxonomy emissions',()=>{
    for(const [key,value] of Object.entries({name:'Example Cooperative',
      content:'Public workshop minutes',dataset:'book-synthetic',
      dtype:'org',tenant_id:'default'})) assert.deepEqual(values(base,key),[value]);
    for(const key of ['labels','tags','topics']) assert.deepEqual(values(base,key),[]);
    assert.ok(base.every(r=>r.stored));
  });
  for(const key of ['labels','tags','topics']) {
    test(generation+': '+key+'-only changes do not change raw emissions',()=>{
      assert.deepEqual(capture(source,{...doc,[key]:['altered',key]}),base);
      const omitted={...doc};delete omitted[key];
      assert.deepEqual(capture(source,omitted),base);
    });
  }
  test(generation+': nested data taxonomy is not emitted',()=>{
    assert.deepEqual(capture(source,{...doc,
      data:{labels:['other'],tags:['other'],topics:['other']}}),base);
  });
  test(generation+': indexed field changes remain detectable',()=>{
    for(const [key,value] of Object.entries({name:'Other Cooperative',
      content:'Other minutes',dataset:'other-synthetic',
      dtype:'alert',tenant_id:'other'}))
      assert.notDeepEqual(capture(source,{...doc,[key]:value}),base,key);
  });
  test(generation+': taxonomy-looking word in content is only content',()=>{
    const text='robotics education public-demo';
    const rows=capture(source,{...doc,content:text});
    assert.deepEqual(values(rows,'content'),[text]);
    for(const key of ['labels','tags','topics']) assert.deepEqual(values(rows,key),[]);
  });
  test(generation+': mutation control detects explicit taxonomy index code',()=>{
    const anchor="add('dtype',doc.dtype);";
    assert.ok(source.includes(anchor));
    const mutant=source.replace(anchor,anchor+"add('tags',doc.tags);");
    assert.notDeepEqual(capture(mutant,doc),
      capture(mutant,{...doc,tags:['changed']}));
    assert.deepEqual(values(capture(mutant,doc),'tags'),['robotics']);
  });
}
