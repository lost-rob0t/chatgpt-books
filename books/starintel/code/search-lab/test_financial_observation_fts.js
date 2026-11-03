'use strict';
// Chapter 15: a FinancialObservation hit is not a ledger or amount audit.
// Pinned Server Git blobs are executed; synthetic StarLang 0.10.1-shaped
// documents are not SDK-validated and no service/search is performed.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const PINS = {
  historical: '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged: 'dd6336f3047982db2f0e3615fed1413ed1e58e13',
};
// Canonical StarLang 0.10.1 FinancialObservation:
// generated/schema.json blob 537163da436f67a973e280d1704e32bdba5b888b.
// 'amount' is a decimal STRING; currency, fiscalYear, observationType,
// payerIds, payeeIds, sourceTransactionIds are distinct canonical fields.
const OBS = {
  id: 'fictional:financial-observation:invoice-7', rev: 'r1',
  dtype: 'financial-observation', schemaVersion: '0.10.1',
  dataset: 'fictional-finance-demo', amount: '12345.67', currency: 'USD',
  fiscalYear: 2026, observationType: 'synthetic-invoice',
  payerIds: ['fictional:buyer-7'], payeeIds: ['fictional:vendor-3'],
  sourceTransactionIds: ['fictional:transaction-7'],
  provenance: {source: 'fictional-only'},
  description: 'Fictional financial observation',
};
const OTHER = {
  ...OBS, rev: 'r2', amount: '98765.43', currency: 'EUR',
  fiscalYear: 2025, observationType: 'synthetic-refund',
  payerIds: ['fictional:buyer-2'], payeeIds: ['fictional:vendor-8'],
  sourceTransactionIds: ['fictional:transaction-8'],
  provenance: {source: 'other-fictional-source'}, description: 'Other case',
};
const GAPS = ['amount','currency','fiscalYear','observationType','payerIds',
  'payeeIds','sourceTransactionIds','provenance','description','rev'];
const historical = process.env.STAR_SEARCH_FINANCIAL_HISTORICAL_DESIGN ||
  (process.env.STAR_SEARCH_LAB_SERVER && path.join(
    process.env.STAR_SEARCH_LAB_SERVER, 'source/views/search.json'));
if (!historical) throw new Error('pinned historical Server design required');
const inputs = [['historical',historical]];
if (process.env.STAR_SEARCH_FINANCIAL_MERGED_DESIGN)
  inputs.push(['merged',process.env.STAR_SEARCH_FINANCIAL_MERGED_DESIGN]);
function callback(file,generation) {
  const bytes = fs.readFileSync(file);
  const sha = crypto.createHash('sha1').update('blob '+bytes.length+'\0')
    .update(bytes).digest('hex');
  assert.equal(sha,PINS[generation],'exact upstream Git blob required');
  const design = JSON.parse(bytes.toString('utf8'));
  assert.equal(design._id,'_design/search');
  assert.equal(design.indexes.fts.analyzer.fields.dataset,'keyword');
  assert.equal(design.indexes.fts.analyzer.fields.tenant_id,'keyword');
  return design.indexes.fts.index;
}
function project(source,doc) {
  const rows=[];
  vm.runInNewContext('('+source+')(doc)',{
    doc:structuredClone(doc),index(field,value,options) {
      assert.equal(options && options.store,true);
      assert.equal(typeof field,'string');
      assert.ok(['string','number','boolean'].includes(typeof value));
      if (rows.length>=2048) throw new Error('bounded emission limit');
      rows.push([field,value]);
    }}, {timeout:1000});
  return rows;
}
const values=(rows,field)=>rows.filter(row=>row[0]===field).map(row=>row[1]);
for (const [generation,file] of inputs) {
  const source=callback(file,generation),baseline=project(source,OBS);
  test(generation+': scope/type are the only raw emissions',()=>{
    assert.deepEqual(baseline,[['tenant_id','default'],
      ['dataset',OBS.dataset],['dtype',OBS.dtype]]);
  });
  test(generation+': monetary and source identifiers are not indexed',()=>{
    for (const field of GAPS) assert.deepEqual(values(baseline,field),[],field);
  });
  test(generation+': opposing synthetic financial claims share raw search emissions',()=>{
    assert.deepEqual(project(source,OTHER),baseline);
  });
  test(generation+': decimal formatting is not a query filter',()=>{
    for (const amount of ['0','-42.75','+105.00'])
      assert.deepEqual(project(source,{...OBS,amount}),baseline);
  });
  test(generation+': no transaction reference does not change the index',()=>{
    assert.deepEqual(project(source,{...OBS,sourceTransactionIds:[]}),baseline);
  });
  test(generation+': dataset change is an index observation, not a grant',()=>{
    const rows=project(source,{...OBS,dataset:'other-fictional-finance'});
    assert.deepEqual(values(rows,'dataset'),['other-fictional-finance']);
    assert.deepEqual(values(rows,'amount'),[]);
  });
  test(generation+': tenant field is not an authorization decision',()=>{
    const rows=project(source,{...OBS,tenant_id:'fictional-tenant'});
    assert.deepEqual(values(rows,'tenant_id'),['fictional-tenant']);
  });
  test(generation+': an unvalidated raw title is only a positive control',()=>{
    const rows=project(source,{...OBS,title:'RAW INPUT ONLY'});
    assert.deepEqual(values(rows,'title'),['RAW INPUT ONLY']);
    assert.deepEqual(values(baseline,'title'),[]);
  });
  test(generation+': deliberate index edit falsifies the omission claim',()=>{
    const anchor="add('dtype',doc.dtype);";
    assert.equal(source.split(anchor).length,2);
    const altered=project(source.replace(anchor,anchor+"add('amount',doc.amount);"),OBS);
    assert.deepEqual(values(altered,'amount'),[OBS.amount]);
    assert.notDeepEqual(altered,baseline);
    if (process.env.STAR_SEARCH_FINANCIAL_RED==='1')
      assert.deepEqual(altered,baseline,'intentional RED: amount indexed');
  });
}
