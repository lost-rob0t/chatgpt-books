"""Read-only, source-pinned audit of Chapter 15 search API discovery metadata.

This examines historical Lisp declarations. It does not execute Lisp, fetch a
live OpenAPI document, authorize a query, or establish index coverage.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

PINNED = {
    'cli/http-contract-final.lisp': '787169f771845c153d40371d6896838d820cfafa',
    'cli/http-contract-documents.lisp': 'b95fb786cfab6122013229349b7cea54145c1993',
    'source/frontends/http-contract-routes.lisp': '572e78602c2b273f7ed8b45ffaa8d939ce7ce88c',
    'source/frontends/http-authorization-routes.lisp': 'eac4f1d38973cbbe3d19e9ed5e7b1b3c520919a5',
}


def blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def _form(source: str, anchor: str) -> str:
    """Extract one balanced Lisp form, ignoring parentheses in strings/comments.

    This is a small *reader* for an exact pinned declaration, not an evaluator or
    a general-purpose Lisp parser. No code is executed from source text.
    """
    matches = []
    offset = 0
    while True:
        at = source.find(anchor, offset)
        if at < 0:
            break
        matches.append(at)
        offset = at + len(anchor)
    if len(matches) != 1 or not anchor.startswith('('):
        raise ValueError(f'expected exactly one form for {anchor}')
    start = matches[0]
    depth = 0
    quoted = escaped = comment = False
    for index in range(start, len(source)):
        char = source[index]
        if comment:
            if char == '\n':
                comment = False
            continue
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == ';':
            comment = True
        elif char == '"':
            quoted = True
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
            if depth < 0:
                break
    raise ValueError(f'incomplete Lisp form for {anchor}')


def analyze(parts: dict[str, str]) -> dict[str, object]:
    if set(parts) != set(PINNED):
        raise ValueError('all four exact historical source units are required')
    public_contract = _form(parts['cli/http-contract-final.lisp'],
                            '(make-http-operation\n  :id "public.search.get"')
    auth_contract = _form(parts['cli/http-contract-documents.lisp'],
                          '(make-http-operation\n  :id "documents.search"')
    auth_parameters = _form(parts['cli/http-contract-documents.lisp'],
                            '(defparameter +document-search-query-parameters+')
    public_route = _form(parts['source/frontends/http-contract-routes.lisp'],
                         '(defun handle-public-search-route')
    auth_route = _form(parts['source/frontends/http-authorization-routes.lisp'],
                       '(defun handle-authorized-search-route')

    facts = {
        'public_route_requires_q': '(require-query-string params "q")' in public_route,
        'authenticated_route_requires_q': '(require-query-string params "q")' in auth_route,
        'public_registry_declares_query_parameters': ':query-parameters' in public_contract,
        'authenticated_registry_declares_query_parameters':
            ':query-parameters +document-search-query-parameters+' in auth_contract,
        'authenticated_registry_declares_required_q':
            '(list :name "q" :required t' in auth_parameters,
        'public_route_reads_limit': '"limit"' in public_route,
        'public_route_reads_bookmark': '"bookmark"' in public_route,
    }
    # Fail closed if expected source contracts cannot be recognized; otherwise a
    # renamed/unmounted handler might be misclassified as a metadata omission.
    expected = ('public_route_requires_q', 'authenticated_route_requires_q',
                'authenticated_registry_declares_query_parameters',
                'authenticated_registry_declares_required_q',
                'public_route_reads_limit', 'public_route_reads_bookmark')
    if not all(facts[key] for key in expected):
        raise ValueError('pinned source shapes changed; do not infer the gap')
    facts['public_discovery_q_gap'] = (
        facts['public_route_requires_q']
        and not facts['public_registry_declares_query_parameters']
    )
    facts['claim_class'] = 'PINNED_SOURCE_DECLARATIONS_ONLY'
    facts['limits'] = [
        'No live OpenAPI/client-manifest artifact was retrieved.',
        'No Lisp runtime or HTTP middleware was executed.',
        'No search authorization, index coverage, or canonical evidence was proved.',
    ]
    return facts


def audit_checkout(root: Path) -> dict[str, object]:
    sources: dict[str, str] = {}
    for path, expected in PINNED.items():
        raw = (root / path).read_bytes()
        if blob_sha(raw) != expected:
            raise ValueError(f'historical Git blob mismatch: {path}')
        sources[path] = raw.decode('utf-8')
    return analyze(sources)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) != 1:
        print('usage: compare_search_discovery.py PINNED_SERVER_ROOT', file=sys.stderr)
        return 2
    try:
        result = audit_checkout(Path(argv[0]))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f'pinned search discovery audit rejected: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result['public_discovery_q_gap'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
