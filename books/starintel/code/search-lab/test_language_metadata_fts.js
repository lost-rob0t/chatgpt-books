'use strict';
// Source-exact raw FTS callback evidence, not a live search or schema validation.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const PINS = {historical:'0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged:'dd6336f3047982db2f0e3615fed1413ed1e58e13'};
function design(file, generation) {
  const raw = fs.readFileSync(file);
  const sha = crypto.createHash('sha1')
    .update(Buffer.from('blob '+raw.length+'\0')).update(raw).digest('hex');
  assert.equal(sha, PINS[generation], 'unpinned search index source');
  const result = JSON.parse(raw.toString('utf8'));
  assert.equal(result._id, '_design/search');
  return result.indexes.fts;
}
function capture(source, doc) {
  const rows = [], scope = vm.createContext({index:(field,value,options) =>
    rows.push({field,value,stored:options?.store === true})});
  scope.doc = structuredClone(doc);
  scope.fn = new vm.Script('('+source+')').runInContext(scope,{timeout:1000});
  new vm.Script('fn(doc)').runInContext(scope,{timeout:1000});
  return rows;
}
const values = (rows, field) => rows.filter(r=>r.field===field).map(r=>r.value);
const sample = (dtype, extra) => ({id:'synthetic:'+dtype,rev:'r1',
  schemaVersion:'0.10.1',dataset:'book-synthetic',tenant_id:'default',dtype,...extra});
const historical = process.env.STAR_SEARCH_LANGUAGE_HISTORICAL_DESIGN ||
  (process.env.STAR_SEARCH_LAB_SERVER && path.join(
    process.env.STAR_SEARCH_LAB_SERVER,'source/views/search.json'));
assert.ok(historical, 'set STAR_SEARCH_LAB_SERVER to a pinned historical checkout');
const inputs = [['historical',historical]];
if (process.env.STAR_SEARCH_LANGUAGE_MERGED_DESIGN)
  inputs.push(['merged',process.env.STAR_SEARCH_LANGUAGE_MERGED_DESIGN]);
for (const [generation,file] of inputs) {
  const fts = design(file,generation);
  const person = sample('person',{fname:'Nadia',language:'en'});
  const post = sample('social-media-post',{
    content:'Fictional public workshop announcement',language:'en'});
  test(generation+': analyzer declaration has no language-specific field',()=>{
    assert.equal(fts.analyzer.name,'perfield');
    assert.equal(fts.analyzer.default,'standard');
    assert.equal(fts.analyzer.fields.dataset,'keyword');
    assert.equal(fts.analyzer.fields.tenant_id,'keyword');
    assert.equal(Object.hasOwn(fts.analyzer.fields,'language'),false);
  });
  test(generation+': changing canonical-shaped Person.language is invisible',()=>{
    const base=capture(fts.index,person);
    for(const language of ['fr','ar','he','und'])
      assert.deepEqual(capture(fts.index,{...person,language}),base);
    const absent={...person}; delete absent.language;
    assert.deepEqual(capture(fts.index,absent),base);
    assert.deepEqual(values(base,'language'),[]);
    assert.deepEqual(values(base,'fname'),['Nadia']);
    assert.ok(base.every(r=>r.stored));
  });
  test(generation+': SocialMediaPost.language is not raw FTS evidence',()=>{
    const base=capture(fts.index,post);
    for(const language of ['fr','ar','he','und'])
      assert.deepEqual(capture(fts.index,{...post,language}),base);
    assert.deepEqual(values(base,'language'),[]);
    assert.deepEqual(values(base,'content'),[post.content]);
    assert.deepEqual(values(base,'dtype'),['social-media-post']);
  });
  test(generation+': nested data.language also has no raw emission',()=>{
    const base=capture(fts.index,person);
    assert.deepEqual(capture(fts.index,{...person,data:{language:'fr'}}),base);
    assert.deepEqual(values(base,'language'),[]);
  });
  test(generation+': indexed content and server scope fields remain controls',()=>{
    const base=capture(fts.index,post);
    assert.notDeepEqual(capture(fts.index,{...post,content:'Other text'}),base);
    assert.notDeepEqual(capture(fts.index,{...post,dataset:'book-other'}),base);
    assert.deepEqual(values(base,'dataset'),['book-synthetic']);
    assert.deepEqual(values(base,'tenant_id'),['default']);
  });
  test(generation+': mutant emitting language changes observed projection',()=>{
    const anchor="add('dtype',doc.dtype);";
    assert.ok(fts.index.includes(anchor));
    const mutant=fts.index.replace(anchor,anchor+"add('language',doc.language);");
    assert.notDeepEqual(capture(mutant,person),
      capture(mutant,{...person,language:'fr'}));
    assert.deepEqual(values(capture(mutant,person),'language'),['en']);
  });
}
