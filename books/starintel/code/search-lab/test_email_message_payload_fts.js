#!/usr/bin/env node
'use strict';
// Chapter 15: source-exact historical/merged FTS emissions for synthetic
// canonical-shaped EmailMessage payloads. Not a schema admission, service,
// credential, installed index, analyzer, or search visibility experiment.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const vm = require('node:vm');

const PINS = Object.freeze({
  historical: '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged: 'dd6336f3047982db2f0e3615fed1413ed1e58e13',
});
const HISTORICAL = process.env.STAR_SEARCH_EMAIL_HISTORICAL_DESIGN ||
  (process.env.STAR_SEARCH_LAB_SERVER &&
    path.join(process.env.STAR_SEARCH_LAB_SERVER, 'source/views/search.json'));
const MERGED = process.env.STAR_SEARCH_EMAIL_MERGED_DESIGN;

function gitBlob(raw) {
  return crypto.createHash('sha1').update(`blob ${raw.length}\0`).update(raw).digest('hex');
}
function readPinned(filename, generation) {
  if (!filename) throw new Error('provide a pinned search.json file');
  const raw = fs.readFileSync(filename);
  assert.equal(gitBlob(raw), PINS[generation], `${generation} Git source blob must match`);
  const design = JSON.parse(raw);
  assert.equal(design._id, '_design/search');
  assert.equal(design.language, 'javascript');
  assert.equal(typeof design.indexes.fts.index, 'string');
  return design.indexes.fts.index;
}
function project(indexSource, document) {
  const rows = [];
  const context = vm.createContext({index(field, value, options) {
    assert.equal(options?.store, true);
    if (rows.length === 2048) throw new Error('bounded emission capture exceeded');
    rows.push({field, value});
  }});
  context.doc = structuredClone(document);
  context.project = new vm.Script(`(${indexSource})`)
    .runInContext(context, {timeout: 1000});
  new vm.Script('project(doc)').runInContext(context, {timeout: 1000});
  return rows;
}
function message() {
  // Fictional shape drawn from StarLang 0.10.1 $defs.EmailMessage.
  // Deliberately not asserted to pass canonical SDK validation or ingestion.
  return {
    id: 'starintel:email-message:fictional-001',
    rev: 'rev-example-001',
    schemaVersion: '0.10.1',
    dtype: 'email-message',
    dataset: 'book-synthetic',
    subject: 'Fictional delivery receipt',
    body: 'Synthetic correspondence about a laboratory fixture.',
    bodyHtml: '<p>Synthetic correspondence about a laboratory fixture.</p>',
    messageId: '<fixture-001@example.invalid>',
    threadId: 'thread-synthetic-001',
    from: {address: 'writer@example.invalid'},
    to: [{address: 'reader@example.invalid'}],
  };
}
const sources = [['historical', HISTORICAL]];
if (MERGED) sources.push(['merged', MERGED]);

for (const [generation, filename] of sources) {
  test(`${generation}: source identity and FTS callback`, () => {
    const index = readPinned(filename, generation);
    assert.equal(typeof index, 'string');
    assert.match(index, /function\(doc\)/);
  });
  const get = () => readPinned(filename, generation);
  test(`${generation}: email payload lacks direct raw index emissions`, () => {
    const rows = project(get(), message());
    assert.deepEqual(rows, [
      {field: 'tenant_id', value: 'default'},
      {field: 'dataset', value: 'book-synthetic'},
      {field: 'dtype', value: 'email-message'},
    ]);
  });
  test(`${generation}: changing the subject cannot change raw emissions`, () => {
    const before = message();
    const after = {...before, subject: 'Fictional alternate subject'};
    assert.deepEqual(project(get(), before), project(get(), after));
  });
  test(`${generation}: body and HTML representation are not direct fields`, () => {
    const before = message();
    const after = {...before, body: 'Different fictional message body',
      bodyHtml: '<b>Different fictional HTML</b>'};
    assert.deepEqual(project(get(), before), project(get(), after));
  });
  test(`${generation}: thread, message ID, sender and recipients are not emitted`, () => {
    const before = message();
    const after = {...before, messageId: '<other@example.invalid>',
      threadId: 'different-fictional-thread',
      from: {address: 'different@example.invalid'},
      to: [{address: 'elsewhere@example.invalid'}]};
    assert.deepEqual(project(get(), before), project(get(), after));
  });
  test(`${generation}: changing server-scope dataset is a positive control`, () => {
    const before = project(get(), message());
    const after = project(get(), {...message(), dataset: 'book-alternate'});
    assert.notDeepEqual(after, before);
    assert.deepEqual(after.filter(({field}) => field === 'dataset'),
      [{field: 'dataset', value: 'book-alternate'}]);
  });
  test(`${generation}: adding generic content would index a noncanonical key`, () => {
    const before = project(get(), message());
    const after = project(get(), {...message(), content: 'fictional generic field'});
    assert.equal(before.some(({field}) => field === 'content'), false);
    assert.deepEqual(after.filter(({field}) => field === 'content'),
      [{field: 'content', value: 'fictional generic field'}]);
  });
  test(`${generation}: empty email payload fields still leave scope/type emissions`, () => {
    const empty = {...message(), subject: '', body: '', bodyHtml: ''};
    assert.deepEqual(project(get(), empty), project(get(), message()));
  });
}
module.exports = {PINS, gitBlob, readPinned, project, message};
