"""Select unchanged top-level upstream forms, with no product-repository edits."""
import re
from pathlib import Path


def form(source: str, name: str) -> str:
    matches = list(re.finditer(r'^\((?:defun|defparameter|define-condition)\s+' + re.escape(name) + r'(?=[\s()])', source, re.M | re.I))
    if len(matches) != 1:
        raise ValueError(f'expected one upstream form: {name}')
    start = matches[0].start()
    depth, string, comment, escaped = 0, False, False, False
    for i in range(start, len(source)):
        char = source[i]
        if comment:
            comment = char != '\n'; continue
        if string:
            if escaped: escaped = False
            elif char == '\\': escaped = True
            elif char == '"': string = False
            continue
        if char == ';': comment = True
        elif char == '"': string = True
        elif char == '(': depth += 1
        elif char == ')':
            depth -= 1
            if depth == 0: return source[start:i+1]
    raise ValueError(f'unterminated upstream form: {name}')


SELECTIONS = {
 'source/frontends/http-boundary-core.lisp': ('http-input-error', 'signal-http-input-error', '+http-max-query-limit+', 'non-empty-string-p', 'query-value', 'require-query-string', 'bounded-query-integer', 'strip-server-tenant-fields', 'strip-outbox-payload-tenants', 'strip-server-tenant-from-rows', 'strip-server-tenant-from-search-body'),
 'source/frontends/http-contract-routes.lisp': ('+public-search-max-query-length+', '+public-search-max-results+', 'public-search-scopes', 'public-search-context', 'public-search-authorized-query', 'reject-public-scope-overrides', 'handle-public-search-route'),
 'source/frontends/http-authorization-routes.lisp': ('handle-authorized-search-route',),
 'source/authorization/policy.lisp': ('prefixed-scope-p', 'administrator-scopes-p', 'capability-granted-p', 'scope-values'),
 'source/authorization/services.lisp': ('lucene-escape', 'lucene-term', 'lucene-scope-clause', 'restricted-values', 'require-search-dimension'),
 'source/authorization/services-final.lisp': ('authorized-search-query',),
}


def extract(root: Path, output: Path) -> None:
    parts = []
    for path, names in SELECTIONS.items():
        package = 'star.authorization' if '/authorization/' in path else 'star.frontends.http-api'
        parts.append(f'(in-package :{package})')
        source = (root / path).read_text()
        parts.extend(form(source, name) for name in names)
    output.write_text('\n\n'.join(parts) + '\n')


if __name__ == '__main__':
    import sys
    extract(Path(sys.argv[1]), Path(sys.argv[2]))
