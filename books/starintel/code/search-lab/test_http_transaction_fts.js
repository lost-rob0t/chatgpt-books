'use strict';
// Different BK13 topic: HTTP transaction metadata is not a raw search audit trail.
// The two Git-blob-pinned original FTS callbacks run in Node, not CouchDB.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');
const pins = {historical:'0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged:'dd6336f3047982db2f0e3615fed1413ed1e58e13'};
function read(file, name) {
  const bytes = fs.readFileSync(file);
  const git = crypto.createHash('sha1').update(Buffer.from('blob '+bytes.length+'\0'))
    .update(bytes).digest('hex');
  assert.equal(git, pins[name], 'wrong original source');
  return JSON.parse(bytes.toString('utf8')).indexes.fts.index;
}
function emit(fn, doc) {
  const rows = [];
  const context = vm.createContext({index(field,value,o) {
    rows.push({field,value,store:o?.store === true});
  },doc:structuredClone(doc)});
  context.fn = new vm.Script('('+fn+')').runInContext(context,{timeout:1000});
  new vm.Script('fn(doc)').runInContext(context,{timeout:1000});
  return rows;
}
function values(rows, key) {return rows.filter(x=>x.field===key).map(x=>x.value);}
// 0.10.1 HttpTransaction schema requires transactionId, method, url, responseStatus;
// headers and body artifact digests are different canonical fields, not FTS facets.
const specimen = {id:'book:http:one',rev:'r1',schemaVersion:'0.10.1',
  dataset:'book-synthetic',dtype:'http-transaction',transactionId:'demo-tx',
  method:'GET',url:'https://example.invalid/resource',responseStatus:200,
  requestBodyHash:'fictional-request',responseBodyHash:'fictional-response',
  redactedHeaders:{authorization:'[REDACTED]'}};
for (const [kind,file] of [
  ['historical',process.env.STAR_SEARCH_HTTP_HISTORICAL_DESIGN],
  ['merged',process.env.STAR_SEARCH_HTTP_MERGED_DESIGN]]) {
  if (!file) continue;
  const fn=read(file,kind);
  test(kind+': URL, dataset and dtype emitted',()=>{
    const rows=emit(fn,specimen);
    assert.deepEqual(values(rows,'url'),['https://example.invalid/resource']);
    assert.deepEqual(values(rows,'dataset'),['book-synthetic']);
    assert.deepEqual(values(rows,'dtype'),['http-transaction']);
    assert.ok(rows.every(row=>row.store));
  });
  test(kind+': changing HTTP method leaves raw search emissions unchanged',()=>{
    assert.deepEqual(emit(fn,specimen),emit(fn,{...specimen,method:'POST'}));
    assert.deepEqual(values(emit(fn,specimen),'method'),[]);
  });
  test(kind+': changing response status leaves raw search emissions unchanged',()=>{
    assert.deepEqual(emit(fn,specimen),emit(fn,{...specimen,responseStatus:503}));
    assert.deepEqual(values(emit(fn,specimen),'responseStatus'),[]);
  });
  test(kind+': redacted header values are not FTS scalars',()=>{
    assert.deepEqual(emit(fn,specimen),emit(fn,{...specimen,
      redactedHeaders:{authorization:'different-redacted-value'}}));
    assert.deepEqual(values(emit(fn,specimen),'redactedHeaders'),[]);
  });
  test(kind+': body artifact hashes are not FTS scalars',()=>{
    assert.deepEqual(emit(fn,specimen),emit(fn,{...specimen,
      requestBodyHash:'different-req',responseBodyHash:'different-response'}));
    assert.deepEqual(values(emit(fn,specimen),'responseBodyHash'),[]);
  });
  test(kind+': changed URL and dataset remain distinct positive controls',()=>{
    assert.notDeepEqual(emit(fn,specimen),emit(fn,{...specimen,
      url:'https://example.invalid/another-resource'}));
    assert.notDeepEqual(emit(fn,specimen),emit(fn,{...specimen,dataset:'book-other'}));
  });
  test(kind+': changing the index function to add responseStatus would be observable',()=>{
    const marker="add('dtype',doc.dtype);";
    assert.ok(fn.includes(marker));
    const mutant=fn.replace(marker,marker+"add('responseStatus',doc.responseStatus);");
    assert.notDeepEqual(emit(mutant,specimen),emit(mutant,{...specimen,responseStatus:503}));
  });
}
assert.ok(process.env.STAR_SEARCH_HTTP_HISTORICAL_DESIGN,'historical design required');
