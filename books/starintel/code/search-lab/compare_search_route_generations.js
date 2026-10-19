#!/usr/bin/env node
'use strict';
// Chapter 15 optional *source* comparison, not a server dispatch or policy test.
const fs = require('node:fs');
const crypto = require('node:crypto');
const path = require('node:path');

const PINS = Object.freeze({
  historicalPublic: '572e78602c2b273f7ed8b45ffaa8d939ce7ce88c',
  mergedPublic: 'a77ea2cda8337f5c52da73537f87e772cadc6b63',
  authorization: 'eac4f1d38973cbbe3d19e9ed5e7b1b3c520919a5',
});
const PUBLIC_FORMS = Object.freeze([
  'public-search-scopes',
  'public-search-context',
  'public-search-authorized-query',
  'reject-public-scope-overrides',
  'handle-public-search-route',
  'handle-contracted-document-search-route',
]);
const AUTH_FORMS = Object.freeze(['handle-authorized-search-route']);

function gitBlob(raw) {
  const prefix = Buffer.from(`blob ${raw.length}\0`, 'utf8');
  return crypto.createHash('sha1').update(prefix).update(raw).digest('hex');
}
function readPinned(file, expected) {
  const raw = fs.readFileSync(file);
  const sha = gitBlob(raw);
  if (sha !== expected) throw new Error(`${path.basename(file)}: expected Git blob ${expected}, got ${sha}`);
  return raw.toString('utf8');
}
function balancedForm(source, start) {
  let depth = 0;
  let quoted = false, escaped = false, lineComment = false;
  for (let i = start; i < source.length; i += 1) {
    const c = source[i];
    if (lineComment) { if (c === '\n') lineComment = false; continue; }
    if (quoted) {
      if (escaped) { escaped = false; continue; }
      if (c === '\\') { escaped = true; continue; }
      if (c === '"') quoted = false;
      continue;
    }
    if (c === ';') { lineComment = true; continue; }
    if (c === '"') { quoted = true; continue; }
    if (c === '(') depth += 1;
    if (c === ')') { depth -= 1; if (depth === 0) return source.slice(start, i + 1); }
  }
  throw new Error('unterminated named Lisp form');
}
function namedDefuns(source) {
  const matches = Array.from(source.matchAll(/^\(defun\s+([^\s()]+)/gm));
  const result = new Map();
  for (const match of matches) {
    if (result.has(match[1])) throw new Error(`duplicate defun ${match[1]}`);
    result.set(match[1], balancedForm(source, match.index));
  }
  return result;
}

function compareForms(oldSource, newSource, names) {
  const oldForms = namedDefuns(oldSource), newForms = namedDefuns(newSource);
  return names.map((name) => {
    const earlier = oldForms.get(name), later = newForms.get(name);
    if (!earlier || !later) throw new Error(`required defun missing: ${name}`);
    if (earlier !== later) throw new Error(`pinned defun changed: ${name}`);
    return {name, source_bytes_equal: true, characters: earlier.length};
  });
}
function main(args) {
  if (args.length !== 4) throw new Error('usage: node compare_search_route_generations.js OLD_PUBLIC MERGED_PUBLIC OLD_AUTH MERGED_AUTH');
  const [oldPub, newPub, oldAuth, newAuth] = args;
  const pOld = readPinned(oldPub, PINS.historicalPublic);
  const pNew = readPinned(newPub, PINS.mergedPublic);
  const aOld = readPinned(oldAuth, PINS.authorization);
  const aNew = readPinned(newAuth, PINS.authorization);
  const compared = [...compareForms(pOld, pNew, PUBLIC_FORMS), ...compareForms(aOld, aNew, AUTH_FORMS)];
  process.stdout.write(`${JSON.stringify({
    result: 'PINNED_SOURCE_FORMS_UNCHANGED',
    compared,
    historical_server: 'ce14c77ccd2f51f543410fdeef3d78fb9978b769',
    merged_server: 'ca6fdcbdc1f3b8aa344c533a40d298f741a54f25',
    limitations: 'Source identity of named functions only; no runtime dispatch, auth, indexing, policy, or deployed behavior asserted.',
  }, null, 2)}\n`);
}
if (require.main === module) {
  try { main(process.argv.slice(2)); }
  catch (error) { process.stderr.write(`${error.message}\n`); process.exitCode = 1; }
}
module.exports = {gitBlob, namedDefuns, compareForms, PINS, PUBLIC_FORMS, AUTH_FORMS, main};
