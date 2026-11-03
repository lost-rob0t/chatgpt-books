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
  return design.indexes.fts;
});
function emit(source,doc){
  const values=[];
  const scope=vm.createContext({index:(field,value,options)=>values.push({field,value,stored:options?.store===true})});
  const indexer=new vm.Script('('+source+')').runInContext(scope,{timeout:1000});
  scope.indexer=indexer;
  scope.document=structuredClone(doc);
  new vm.Script('indexer(document)').runInContext(scope,{timeout:1000});
  return values;  // Preserve every index() call, including repeated fields.
}
const specimen={dtype:'person',dataset:'book-synthetic',
  fullName:'Example Person',displayName:'Example Display',
  legalName:'Example Legal',orgType:'example-class',
  full_name:'old-name',display_name:'old-display',
  legal_name:'old-legal',org_type:'old-kind',
  content:['alpha','beta','gamma'],
  sources:[{name:'Source A',url:'https://a.invalid'},
           {name:'Source B',url:'https://b.invalid'}]};
const historical=emit(indexSources[0].index,specimen),merged=emit(indexSources[1].index,specimen);
const valuesFor=(emissions,field)=>emissions.filter(e=>e.field===field).map(e=>e.value);
const added=['fullName','displayName','legalName','orgType'];
for(const field of added){
  assert.equal(valuesFor(historical,field).length,0,'Historical pin unexpectedly has '+field);
  assert.deepEqual(valuesFor(merged,field),[specimen[field]],'Merged pin omitted '+field);
}
for(const field of ['full_name','display_name','legal_name','org_type']){
  assert.deepEqual(valuesFor(historical,field),[specimen[field]]);
  assert.deepEqual(valuesFor(merged,field),[specimen[field]]);
}
for(const field of ['dataset','dtype','tenant_id']){
  assert.deepEqual(valuesFor(historical,field),valuesFor(merged,field),'Shared metadata drift: '+field);
}
const multivalue={
  content:['alpha','beta','gamma'],
  sources:['Source A','https://a.invalid','Source B','https://b.invalid']
};
for(const [field,want] of Object.entries(multivalue)){
  assert.deepEqual(valuesFor(historical,field),want);
  assert.deepEqual(valuesFor(merged,field),want);
}
assert.ok([...historical,...merged].every(e=>e.stored===true));
assert.equal(merged.length-historical.length,4);
// Source declaration, NOT observed Clouseau/Lucene tokenizer output.
const analyzerFor=(fts,field)=>{
  assert.equal(fts.analyzer.name,'perfield');
  return Object.hasOwn(fts.analyzer.fields,field)
    ? fts.analyzer.fields[field] : fts.analyzer.default;
};
const trackedAnalyzerFields=['name','fullName','displayName','legalName','full_name','dataset','tenant_id','dtype'];
const declaredAnalyzers=Object.fromEntries(trackedAnalyzerFields.map(field=>[
  field, indexSources.map(fts=>analyzerFor(fts,field))
]));
assert.deepEqual(declaredAnalyzers.name,['keyword','keyword']);
for(const field of ['fullName','displayName','legalName','full_name','dtype']){
  assert.deepEqual(declaredAnalyzers[field],['standard','standard']);
}
for(const field of ['dataset','tenant_id']){
  assert.deepEqual(declaredAnalyzers[field],['keyword','keyword']);
}
console.log(JSON.stringify({status:'PASS', historical_emissions:historical.length,
  merged_emissions:merged.length,added_fields:added,
  declared_analyzers_by_generation:declaredAnalyzers,
  shared_multivalue_emissions:multivalue,
  evidence:'original pinned JavaScript projection only; NOT installed Clouseau index'},null,2));
