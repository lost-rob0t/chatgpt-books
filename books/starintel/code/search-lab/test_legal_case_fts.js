'use strict';
// Chapter 15: a fictional canonical-shaped LegalCase is not court evidence.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const PINS = {historical:'0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged:'dd6336f3047982db2f0e3615fed1413ed1e58e13'};
const oldFile = process.env.STAR_SEARCH_LEGALCASE_HISTORICAL_DESIGN ||
  (process.env.STAR_SEARCH_LAB_SERVER && path.join(process.env.STAR_SEARCH_LAB_SERVER,
    'source/views/search.json'));
if (!oldFile) throw new Error('pinned historical design required');
const inputs = [['historical',oldFile]];
if (process.env.STAR_SEARCH_LEGALCASE_MERGED_DESIGN)
  inputs.push(['merged',process.env.STAR_SEARCH_LEGALCASE_MERGED_DESIGN]);
function callback(file, generation) {
  const bytes = fs.readFileSync(file);
  const sha = crypto.createHash('sha1').update('blob '+bytes.length+'\0')
    .update(bytes).digest('hex');
  assert.equal(sha, PINS[generation], 'Git source blob mismatch');
  const design = JSON.parse(bytes.toString('utf8'));
  assert.equal(design._id,'_design/search');
  assert.equal(design.indexes.fts.analyzer.fields.dataset,'keyword');
  assert.equal(design.indexes.fts.analyzer.fields.tenant_id,'keyword');
  return design.indexes.fts.index;
}
function project(fn, doc) {
  const out = [];
  const context = vm.createContext({document:structuredClone(doc),
    index(field,value,options) {
      assert.equal(options && options.store,true);
      if (out.length >= 2048) throw new Error('bounded capture overflow');
      out.push({field,value});
    }});
  new vm.Script('('+fn+')(document)').runInContext(context,{timeout:1000});
  return out;
}
const fields = ['caseName','caseNumber','court','citation','filedAt',
  'docketEntries','status','disposition','outcome','partyIds','rev'];
// StarLang 0.10.1 LegalCase schema: blob 537163da436f67a973e280d1704e32bdba5b888b.
// This synthetic record is canonical-SHAPED, not SDK-validated.
const record = {id:'fictional:legal-case:7',rev:'r1',dtype:'legal-case',
  dataset:'fictional-cases',schemaVersion:'0.10.1',
  caseName:'Imaginary Borough v. Paper Observatory',caseNumber:'FICTIONAL-7',
  court:'Fictional Tribunal',citation:'Fictional Reporter 7',
  filedAt:'2026-05-01T00:00:00Z',docketEntries:[{entry:'invented filing'}],
  status:'pending',disposition:'none',outcome:'undecided',
  partyIds:['fictional:organization:7']};
for (const [generation,file] of inputs) {
  const source = callback(file,generation);
  const before = project(source,record);
  test(generation+': raw search scope contains only tenant/dataset/type',()=>{
    assert.deepEqual(before,[{field:'tenant_id',value:'default'},
      {field:'dataset',value:'fictional-cases'},
      {field:'dtype',value:'legal-case'}]);
  });
  test(generation+': canonical case identity and docket fields not indexed',()=>{
    for (const name of fields) assert.ok(!before.some(x=>x.field===name),name);
    assert.ok(!before.some(x=>x.field==='name'));
  });
  test(generation+': alleged dismissal does not alter raw index',()=>{
    const after = {...record,caseName:'Different invented case',rev:'r2',
      status:'closed',disposition:'dismissed',outcome:'no trial',
      docketEntries:[{entry:'invented dismissal'}]};
    assert.deepEqual(project(source,after),before);
  });
  test(generation+': dataset and tenant are index facts, not grants',()=>{
    const after = project(source,{...record,dataset:'other-fictional',
      tenant_id:'fictional-tenant'});
    assert.deepEqual(after,[{field:'tenant_id',value:'fictional-tenant'},
      {field:'dataset',value:'other-fictional'},
      {field:'dtype',value:'legal-case'}]);
  });
  test(generation+': dropping caseName does not change projection',()=>{
    const unnamed = {...record}; delete unnamed.caseName;
    assert.deepEqual(project(source,unnamed),before);
  });
  test(generation+': indexed dtype changes independently of legal outcome',()=>{
    assert.notDeepEqual(project(source,{...record,dtype:'fictional-other'}),before);
  });
  test(generation+': deliberate caseName indexing mutation is detected',()=>{
    const anchor = "add('dtype',doc.dtype);";
    assert.equal(source.split(anchor).length,2);
    const mutated = project(source.replace(anchor,anchor+"add('caseName',doc.caseName);"),record);
    assert.ok(mutated.some(x=>x.field==='caseName' && x.value===record.caseName));
    if (process.env.STAR_SEARCH_LEGALCASE_RED==='1')
      assert.deepEqual(mutated,before,'intentional RED mutation control');
  });
}
