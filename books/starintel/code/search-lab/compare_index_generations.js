'use strict';
const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const crypto=require('node:crypto');
const files=process.argv.slice(2);
assert.equal(files.length,2,'usage: node compare_index_generations.js HISTORICAL_JSON MERGED_JSON');
const expected=['0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a','dd6336f3047982db2f0e3615fed1413ed1e58e13'];
const indexSources=files.map((file,i)=>{
  const bytes=fs.readFileSync(file);
  const sha=crypto.createHash('sha1').update(Buffer.from('blob '+bytes.length+'\0')).update(bytes).digest('hex');
  assert.equal(sha,expected[i],'Source index Git blob mismatch');
  const design=JSON.parse(bytes.toString('utf8'));
  assert.equal(design._id,'_design/search');
  return design.indexes.fts.index;
});
function emit(source,doc){
  const values=[];
  const scope=vm.createContext({index:(field,value)=>values.push([field,value])});
  const indexer=new vm.Script('('+source+')').runInContext(scope,{timeout:1000});
  scope.indexer=indexer;
  scope.document=structuredClone(doc);
  new vm.Script('indexer(document)').runInContext(scope,{timeout:1000});
  return Object.fromEntries(values);
}
const specimen={dtype:'person',dataset:'book-synthetic',
  fullName:'Example Person',displayName:'Example Display',
  legalName:'Example Legal',orgType:'example-class',
  full_name:'old-name',display_name:'old-display',
  legal_name:'old-legal',org_type:'old-kind'};
const historical=emit(indexSources[0],specimen),merged=emit(indexSources[1],specimen);
const added=['fullName','displayName','legalName','orgType'];
for(const field of added){
  assert.equal(Object.hasOwn(historical,field),false,'Historical pin unexpectedly has '+field);
  assert.equal(merged[field],specimen[field],'Merged pin omitted '+field);
}
for(const field of ['full_name','display_name','legal_name','org_type']){
  assert.equal(historical[field],specimen[field]);
  assert.equal(merged[field],specimen[field]);
}
for(const field of ['dataset','dtype','tenant_id']){
  assert.equal(historical[field],merged[field],'Shared metadata drift: '+field);
}
assert.equal(Object.keys(merged).length-Object.keys(historical).length,4);
console.log(JSON.stringify({status:'PASS', historical_emissions:Object.keys(historical).length,
  merged_emissions:Object.keys(merged).length,added_fields:added,
  evidence:'original pinned JavaScript projection only; NOT installed Clouseau index'},null,2));
