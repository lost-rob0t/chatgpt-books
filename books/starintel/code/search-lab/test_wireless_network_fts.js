'use strict';
// Synthetic wireless identifiers and security must not be inferred from raw FTS.
// Neither source callback validates canonical StarLang or queries a live index.
const A = require('node:assert/strict');
const C = require('node:crypto');
const F = require('node:fs');
const T = require('node:test');
const V = require('node:vm');
const sourcePins = {
  historical: '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged: 'dd6336f3047982db2f0e3615fed1413ed1e58e13',
};
const files = [
  ['historical', process.env.STAR_SEARCH_WIRELESS_HISTORICAL_DESIGN],
  ['merged', process.env.STAR_SEARCH_WIRELESS_MERGED_DESIGN],
];
if (!files[0][1]) throw Error('pinned historical design is required');
function indexFrom(name, path) {
  const raw = F.readFileSync(path);
  const sha = C.createHash('sha1').update('blob '+raw.length+'\0').update(raw).digest('hex');
  A.equal(sha, sourcePins[name]);
  const design = JSON.parse(raw.toString('utf8'));
  A.equal(design._id, '_design/search');
  return design.indexes.fts.index;
}
function emissions(callback, doc) {
  const rows=[];
  const ctx=V.createContext({index(field, value, options) {
    rows.push({field, value, stored: options?.store===true});
  }});
  ctx.callback=new V.Script('('+callback+')').runInContext(ctx,{timeout:1000});
  ctx.doc=structuredClone(doc);
  new V.Script('callback(doc)').runInContext(ctx,{timeout:1000});
  return rows;
}
const sample = {
  id:'starintel:wireless-network:fictional-demo', dataset:'synthetic-equipment',
  dtype:'wireless-network', schemaVersion:'0.10.1',rev:'fictional-rev-1',
  ssid:'TEST-ONLY-NETWORK',bssid:'02:00:00:00:00:01', security:'wpa2-psk',
  channel:6,frequencyMhz:2437,signalDbm:-60,
};
const socialPost = {
  id:'starintel:social-media-post:fictional-chat',dataset:'synthetic-equipment',
  dtype:'social-media-post',schemaVersion:'0.10.1',
  content:'Fictional topic only',channel:'fictional-room',
};
for(const [gen,path] of files){
  if(!path) continue;
  const fn=indexFrom(gen,path);
  T(gen+': wireless channel indexed alongside scope, not SSID or BSSID',()=>{
    const rows=emissions(fn,sample);
    A.deepEqual(rows.map(r=>r.field),['tenant_id','dataset','dtype','channel']);
    A.deepEqual(rows.map(r=>r.value),['default','synthetic-equipment','wireless-network',6]);
    A.ok(rows.every(r=>r.stored));
  });
  T(gen+': canonical SSID/BSSID and security not FTS fields',()=>{
    const rows=emissions(fn,sample);
    for(const k of ['ssid','bssid','security','frequencyMhz','signalDbm'])
      A.deepEqual(rows.filter(r=>r.field===k),[]);
  });
  T(gen+': fake security change cannot alter raw FTS output',()=>{
    A.deepEqual(emissions(fn,sample), emissions(fn,{...sample,
      security:'open',frequencyMhz:2462,signalDbm:-90}));
  });
  T(gen+': changing wireless channel is a raw FTS positive control',()=>{
    const one=emissions(fn,sample), other=emissions(fn,{...sample,channel:11});
    A.notDeepEqual(one,other);
    A.deepEqual(one.filter(r=>r.field==='channel').map(r=>r.value),[6]);
    A.deepEqual(other.filter(r=>r.field==='channel').map(r=>r.value),[11]);
  });
  T(gen+': two canonical channel meanings share the same FTS field',()=>{
    const wireless=emissions(fn,sample).filter(r=>r.field==='channel');
    const conversation=emissions(fn,socialPost).filter(r=>r.field==='channel');
    A.deepEqual(wireless.map(r=>r.value),[6]);
    A.deepEqual(conversation.map(r=>r.value),['fictional-room']);
    A.equal(typeof wireless[0].value,'number');
    A.equal(typeof conversation[0].value,'string');
  });
  T(gen+': fake network identifiers are not FTS positive matches',()=>{
    A.deepEqual(emissions(fn,sample), emissions(fn,{...sample,
      ssid:'TEST-ONLY-OTHER',bssid:'02:00:00:00:00:02'}));
  });
  T(gen+': dataset and dtype remain independent controls',()=>{
    A.notDeepEqual(emissions(fn,sample),emissions(fn,{...sample,dataset:'other-fake'}));
    A.notDeepEqual(emissions(fn,sample),emissions(fn,{...sample,dtype:'other-type'}));
  });
  T(gen+': explicitly expanded callback detects wireless SSID edits',()=>{
    const anchor="add('dtype',doc.dtype);";
    A.equal(fn.split(anchor).length,2);
    const extended=fn.replace(anchor,anchor+"add('ssid',doc.ssid);");
    A.notDeepEqual(emissions(extended,sample), emissions(extended,{...sample,
      ssid:'TEST-ONLY-OTHER'}));
  });
}
