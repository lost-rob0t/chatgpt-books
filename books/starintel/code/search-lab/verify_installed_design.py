"""Offline comparison of the pinned source FTS design and an exported CouchDB design.

This verifies an exported JSON snapshot, not the running search backend or its index.
"""
import argparse
import hashlib
import json
from pathlib import Path

HISTORICAL_GIT_BLOB = '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a'
MERGED_GIT_BLOB = 'dd6336f3047982db2f0e3615fed1413ed1e58e13'
SOURCE_PINS = {'historical': HISTORICAL_GIT_BLOB, 'merged': MERGED_GIT_BLOB}


def git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def compare_exported_design(source: bytes, installed: bytes, generation: str = 'historical') -> dict:
    if generation not in SOURCE_PINS:
        raise ValueError('unknown pinned search design generation')
    source_sha = git_blob_sha(source)
    if source_sha != SOURCE_PINS[generation]:
        raise ValueError(f'source file does not match {generation} search design Git blob')
    try:
        expected = json.loads(source)
        actual = json.loads(installed)
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError('source or installed design is not valid JSON') from error
    if not isinstance(actual, dict) or actual.get('_id') != '_design/search':
        raise ValueError('export is not the expected CouchDB search design document')
    try:
        expected_fts = expected['indexes']['fts']
        actual_fts = actual['indexes']['fts']
    except (KeyError, TypeError) as error:
        raise ValueError('missing FTS definition in exported search design') from error
    if not isinstance(actual_fts, dict) or actual_fts != expected_fts:
        raise ValueError('installed exported FTS definition differs from pinned source')
    if actual.get('language') != expected.get('language'):
        raise ValueError('installed exported design language differs from pinned source')
    return {
        'status': 'MATCH',
        'generation': generation,
        'source_git_blob': source_sha,
        'index_name': 'fts',
        'evidence': 'exported design JSON only; not active Clouseau/search or HTTP authorization',
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pinned_source', type=Path)
    parser.add_argument('exported_design', type=Path)
    parser.add_argument('--generation', choices=tuple(SOURCE_PINS), default='historical',
                        help='immutable server FTS design generation; defaults to historical')
    args = parser.parse_args()
    print(json.dumps(compare_exported_design(args.pinned_source.read_bytes(),
                                             args.exported_design.read_bytes(), args.generation), indent=2))


if __name__ == '__main__':
    main()
