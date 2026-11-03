"""Check Chapter 15 Org citation keys against the book's local BibTeX file.

Static key-integrity gate only: it neither runs examples nor authenticates sources,
checks citation rendering, validates full BibTeX syntax, or accesses a service.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

CITE_START = re.compile(r'\[cite(?:/[A-Za-z0-9_-]+)?:', re.I)
CITE_GROUP = re.compile(r'\[cite(?:/[A-Za-z0-9_-]+)?:([^\]]*)\]', re.I | re.S)
CITE_KEY = re.compile(r'(?<![A-Za-z0-9])@([A-Za-z0-9][A-Za-z0-9_.:+-]*)')
BIB_ENTRY = re.compile(r'^\s*@([A-Za-z][A-Za-z0-9_-]*)\s*[({]\s*([^\s,})]+)\s*,', re.M)
BIB_SPECIAL = frozenset({'comment', 'preamble', 'string'})


class CitationError(ValueError):
    """Citation key use is ambiguous or has no bibliography definition."""


def check(manuscript: str, bibliography: str) -> dict[str, int]:
    """Resolve citation keys in one Org chapter against local BibTeX entry keys."""
    starts = list(CITE_START.finditer(manuscript))
    groups = list(CITE_GROUP.finditer(manuscript))
    if len(starts) != len(groups):
        raise CitationError('unterminated Org citation group')
    if not groups:
        raise CitationError('no Org citations found')

    used = []
    for group in groups:
        keys = CITE_KEY.findall(group.group(1))
        if not keys:
            raise CitationError('citation group has no @key')
        used.extend(keys)

    defined = set()
    for match in BIB_ENTRY.finditer(bibliography):
        kind, key = match.groups()
        if kind.lower() in BIB_SPECIAL:
            continue
        if key in defined:
            raise CitationError(f'duplicate bibliography key: {key}')
        defined.add(key)
    missing = sorted(set(used) - defined)
    if missing:
        raise CitationError('undefined citation keys: ' + ', '.join(missing))
    return {'citation_groups': len(groups), 'references': len(used),
            'unique_cited_keys': len(set(used)), 'bibliography_entries': len(defined)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manuscript', type=Path)
    parser.add_argument('bibliography', type=Path)
    args = parser.parse_args(argv)
    try:
        result = check(args.manuscript.read_text(encoding='utf-8'),
                       args.bibliography.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, CitationError) as exc:
        parser.exit(2, f'Chapter 15 citation keys: {exc}\n')
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
