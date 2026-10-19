'use strict';
// Pinned Server callback observations, not schema admission or live search.
const a = require('node:assert/strict');
const fs = require('node:fs');
const crypto = require('node:crypto');
const vm = require('node:vm');
const {test} = require('node:test');
const pins = {historical:'0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged:'dd6336f3047982db2f0e3615fed1413ed1e58e13'};
const root = process.env.STAR_SEARCH_LAB_SERVER;
const historical = process.env.STAR_SEARCH_ASN_HISTORICAL_DESIGN ||
  (root && require('node:path').join(root, 'source/views/search.json'));
a.ok(historical, 'provide exact historical search design');
const paths = [['historical',historical]];
if (process.env.STAR_SEARCH_ASN_MERGED_DESIGN)
  paths.push(['merged',process.env.STAR_SEARCH_ASN_MERGED_DESIGN]);
function callback(generation, file) {
  const raw = fs.readFileSync(file);
  const sha = crypto.createHash('sha1').update('blob '+raw.length+'\0').update(raw).digest('hex');
  a.equal(sha,pins[generation],'Git blob mismatch');
  const fts = JSON.parse(raw.toString('utf8')).indexes.fts;
  a.equal(fts.analyzer.fields.name,'keyword');
  let code = fts.index;
  if (process.env.STAR_SEARCH_ASN_NEGATIVE_CONTROL === 'index-number') {
    const anchor = "add('dtype',doc.dtype);";
    a.equal(code.split(anchor).length,2);
    code = code.replace(anchor,anchor+"add('number',doc.number);");
  }
  return code;
}
function emit(source, record) {
  const rows=[];
  const scope=vm.createContext({index(field,value,options) {
    a.equal(options?.store,true);
    a.ok(rows.length<2048,'bounded source emissions');
    rows.push([field,value]);
  }});
  scope.doc=structuredClone(record);
  scope.fn=new vm.Script('('+source+')').runInContext(scope,{timeout:1000});
  new vm.Script('fn(doc)').runInContext(scope,{timeout:1000});
  return rows;
}
function record(extra={}) { return {id:'starintel:asn:fictional',
  schemaVersion:'0.10.1',dtype:'asn',dataset:'book-public',
  number:64512,name:'Fictional Lab Transit',prefixes:['192.0.2.0/24'],
  peers:[64513],upstreams:[64514],rir:'fictional',registry:'fictional',...extra}; }
for (const [gen,file] of paths) {
  const fn=callback(gen,file);
  test(gen+': exact baseline contains scope/type and optional name',()=>{
    a.deepEqual(emit(fn,record()),[['tenant_id','default'],['dataset','book-public'],
      ['dtype','asn'],['name','Fictional Lab Transit']]);
  });
  test(gen+': ASN identity, prefixes, adjacency, registry are not FTS fields',()=>{
    const keys=emit(fn,record()).map(([key])=>key);
    for(const key of ['number','prefixes','peers','upstreams','rir','registry'])
      a.equal(keys.includes(key),false,key);
  });
  test(gen+': topology mutations leave emissions unchanged',()=>{
    a.deepEqual(emit(fn,record()),emit(fn,record({number:64515,
      prefixes:['198.51.100.0/24'],peers:[64516],upstreams:[64517],
      rir:'other',registry:'another'})));
  });
  test(gen+': positive controls and no-name negative control',()=>{
    a.deepEqual(emit(fn,record({name:undefined})).map(([key])=>key),
      ['tenant_id','dataset','dtype']);
    for(const extra of [{name:'Different Lab'}, {dataset:'book-other-public'},
      {dtype:'other-fictional'}])
      a.notDeepEqual(emit(fn,record()),emit(fn,record(extra)));
  });
  test(gen+': a name containing digits does not attest ASN adjacency',()=>{
    const rows=emit(fn,record({name:'ASN 64512 peer 64513'}));
    a.equal(rows.some(([key])=>key==='number'||key==='peers'),false);
    a.equal(rows.find(([key])=>key==='name')[1],'ASN 64512 peer 64513');
  });
}
