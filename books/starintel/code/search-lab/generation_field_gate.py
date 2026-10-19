"""Source-exact rolling-upgrade FTS field preflight, never a search authorization test.

Reports a single synthetic top-level string's raw index() emissions under
independently attested historical/merged StarIntel Server source generations.
An observed emission is not a Lucene token, search hit, authorized result,
installed design, canonical schema validation, or persisted document.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

PINS = {
    'historical': '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
    'merged': 'dd6336f3047982db2f0e3615fed1413ed1e58e13',
}
MAX_FIELDS = 32
NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,63}\Z')
# Fixed harness: only Git-blob-attested source text is compiled in the VM.
JS_PROBE = r"""
'use strict';
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const results = {};
for (const field of input.fields) {
  const token = 'fictional-field-sentinel';
  const document = {dataset:'book-synthetic',dtype:'person',
    schemaVersion:'0.10.1',[field]:token};
  const rows = [];
  const context = vm.createContext({index(key, value, options) {
    rows.push({key,value,stored:options?.store === true});
    if (rows.length > 2048) throw new Error('emission budget exceeded');
  }});
  context.doc = document;
  context.runIndex = new vm.Script('(' + input.source + ')')
    .runInContext(context,{timeout:1000});
  new vm.Script('runIndex(doc)').runInContext(context,{timeout:1000});
  results[field] = rows.some(row => row.key === field &&
    row.value === token && row.stored);
}
process.stdout.write(JSON.stringify(results));
"""


def load(path: Path, generation: str) -> dict:
    raw = path.read_bytes()
    sha = hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest()
    if sha != PINS[generation]:
        raise ValueError(f'{generation}: original Git blob mismatch')
    design = json.loads(raw)
    if design.get('_id') != '_design/search':
        raise ValueError('not the attested search design')
    fts = design['indexes']['fts']
    if fts['analyzer']['name'] != 'perfield' or not isinstance(fts['index'], str):
        raise ValueError('unsupported pinned search design')
    return fts


def inspect(paths: dict[str, Path], fields: list[str]) -> dict:
    if not fields or len(fields) > MAX_FIELDS or len(set(fields)) != len(fields):
        raise ValueError('require 1..32 distinct fields')
    if any(not isinstance(name, str) or not NAME.fullmatch(name) for name in fields):
        raise ValueError('field names must be simple explicit identifiers')
    if 'historical' not in paths or set(paths) - set(PINS):
        raise ValueError('an attested historical source is required')
    result = {}
    for generation, path in paths.items():
        fts = load(path, generation)
        proc = subprocess.run(['node', '-e', JS_PROBE],
            input=json.dumps({'source': fts['index'], 'fields': fields}),
            text=True, capture_output=True, timeout=10, check=False)
        if proc.returncode:
            raise ValueError(f'{generation}: source callback probe failed')
        raw = json.loads(proc.stdout)
        if set(raw) != set(fields) or any(type(value) is not bool for value in raw.values()):
            raise ValueError('unexpected source callback probe envelope')
        analyzer = fts['analyzer']
        result[generation] = {
            name: {
                'raw_emission_observed': raw[name],
                'declared_analyzer': (
                    analyzer['fields'].get(name, analyzer['default']) if raw[name] else None),
            }
            for name in fields
        }
    states = []
    for name in fields:
        h = result['historical'][name]['raw_emission_observed']
        m = (result['merged'][name]['raw_emission_observed']
             if 'merged' in result else None)
        state = ('historical_only_observed' if h and m is False else
                 'both_observed' if h and m is True else
                 'merged_only_observed' if not h and m is True else
                 'neither_observed' if m is False else
                 'historical_observed_merged_unknown' if h else
                 'historical_not_observed_merged_unknown')
        states.append({'field': name, 'classification': state,
                       'generations': {key: value[name] for key, value in result.items()}})
    return {
        'source_git_blobs': {name: PINS[name] for name in paths},
        'fields': states,
        'limits': [
            'Only one synthetic top-level string value was tested per field.',
            'Raw source index() emission is not query matching or installed-index coverage.',
            'Neither source projection proves public/authenticated authorization,',
            'nor canonical 0.10.1 admission, durable state, or valid bookmarks.',
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('historical', type=Path, help='pinned historical search.json')
    parser.add_argument('--merged', type=Path, help='pinned merged search.json, optional')
    parser.add_argument('--field', action='append', required=True)
    parser.add_argument('--require', choices=('historical', 'merged', 'both'),
                        help='fail if any probe lacks raw emission in the named source(s)')
    args = parser.parse_args(argv)
    paths = {'historical': args.historical}
    if args.merged is not None:
        paths['merged'] = args.merged
    try:
        if args.require in ('merged', 'both') and 'merged' not in paths:
            raise ValueError('cannot gate merged source without an attested merged design')
        out = inspect(paths, args.field)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f'source preflight rejected: {error}', file=sys.stderr)
        return 2
    required = (('historical', 'merged') if args.require == 'both' else
                (args.require,) if args.require else ())
    unsatisfied = [row['field'] for row in out['fields'] if any(
        not row['generations'][generation]['raw_emission_observed'] for generation in required)]
    out['gate'] = {'required': args.require, 'satisfied': not unsatisfied,
                   'unobserved_fields': unsatisfied}
    print(json.dumps(out, indent=2, sort_keys=True))
    return 1 if unsatisfied else 0


if __name__ == '__main__':
    raise SystemExit(main())
