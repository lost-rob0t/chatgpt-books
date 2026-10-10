"""Opt-in real HTTP lab; requires a dedicated, already provisioned local stack."""
import argparse
import json
import os
from pathlib import Path
import secrets
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from lab import interpret_page, next_bookmark, request_path


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(base, path, token=None, document=None):
    headers = {'Accept': 'application/json'}
    if token: headers['Authorization'] = 'Bearer ' + token
    if document is not None: headers['Content-Type'] = 'application/json'
    req = Request(base + path, headers=headers,
                  data=None if document is None else json.dumps(document).encode())
    try:
        with build_opener(NoRedirect()).open(req, timeout=10) as response:
            status, raw = response.status, response.read(2_000_001)
    except HTTPError as error:
        status, raw = error.code, error.read(2_000_001)
    if len(raw) > 2_000_000: raise ValueError('response exceeds lab byte budget')
    try: body = json.loads(raw)
    except (ValueError, UnicodeDecodeError): body = None
    return status, body


def fixture(identity, dataset, needle):
    source = Path(__file__).resolve().parents[1] / 'records/fixtures/person.json'
    value = json.loads(source.read_text())
    value['_id'] = identity
    value['dataset'] = dataset
    value['data']['fname'] = needle
    value['data']['lname'] = 'Synthetic'
    return value


def wait_document(base, identity, token):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        status, doc = request(base, '/api/v1/documents/' + quote(identity, safe=''), token)
        if status == 200 and isinstance(doc, dict) and doc.get('_id') == identity:
            return
        if status not in (200, 404): raise ValueError(f'read-back failed: HTTP {status}')
        time.sleep(.25)
    raise TimeoutError('accepted HTTP did not become a read-back document within 30 seconds')


def collect(base, surface, query, token=None):
    seen, previous = set(), None
    for _ in range(12):
        params = {'limit': 1}
        if previous: params['bookmark'] = previous
        status, page = request(base, request_path(surface, query, **params), token)
        if status != 200: raise ValueError(f'search failed: HTTP {status}')
        hits, bookmark = interpret_page(page)
        if len(hits) > 1: raise ValueError('backend ignored one-row limit')
        for hit in hits:
            if hit.identity in seen: raise ValueError('duplicate identity across pages')
            if hit.document is None: raise ValueError('include_docs response omitted document')
            seen.add(hit.identity)
        previous = next_bookmark(previous, bookmark, hits)
        if previous is None: return seen
    raise ValueError('pagination exceeded lab page budget')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', action='store_true', help='create five historical synthetic records in a disposable stack')
    parser.add_argument('--expect-backend-failure', action='store_true')
    args = parser.parse_args()
    base = os.environ['STAR_SEARCH_LAB_URL'].rstrip('/')
    url = urlsplit(base)
    if url.scheme not in ('http', 'https') or url.hostname not in ('localhost', '127.0.0.1', '::1') or url.username or url.password or url.path or url.query or url.fragment:
        raise ValueError('lab accepts only a local base URL without credentials or path')
    if os.environ.get('STAR_SEARCH_LAB_DISPOSABLE') != '1':
        raise ValueError('set STAR_SEARCH_LAB_DISPOSABLE=1 for a dedicated test deployment')
    if args.expect_backend_failure:
        status, _ = request(base, request_path('public', 'fname:synthetic'))
        if 200 <= status < 300: raise ValueError('backend fault returned apparent success')
        if status < 500: raise ValueError(f'failure was not a backend/server failure: HTTP {status}')
        print(json.dumps({'backend_fault': 'TESTED', 'http_status': status}))
        return
    if not args.seed: raise ValueError('normal service run requires --seed; fixtures must belong to this run')
    tokens = {name: os.environ['STAR_SEARCH_LAB_' + name] for name in ('WRITER', 'OTHER_WRITER', 'READER', 'NOSEARCH')}
    # Confirm credentials authenticate before treating 403 as authorization evidence.
    for token in tokens.values():
        status, _ = request(base, '/auth/context', token)
        if status != 200: raise ValueError(f'fixture credential cannot authenticate: HTTP {status}')
    needle = 'bookneedle' + secrets.token_hex(6)
    ids = ['starintel:person:' + needle + '-' + str(i) for i in range(5)]
    for i, identity in enumerate(ids):
        writer = tokens['OTHER_WRITER'] if i == 4 else tokens['WRITER']
        dataset = 'book-private' if i == 3 else 'book-public'
        status, _ = request(base, '/api/v1/documents', writer, fixture(identity, dataset, needle))
        if status not in (200, 202): raise ValueError(f'historical fixture rejected: HTTP {status}')
        wait_document(base, identity, writer)
    query = 'fname:' + needle
    # Read-back and index visibility are separate bounded observations.
    deadline = time.monotonic() + 30
    while True:
        public = collect(base, 'public', query)
        private = collect(base, 'authenticated', query, tokens['READER'])
        if public == set(ids[:3] + ids[4:]) and private == set(ids[:3]): break
        if ids[3] in public or ids[3] in private or ids[4] in private:
            raise ValueError('unauthorized synthetic fixture leaked')
        if time.monotonic() >= deadline: raise TimeoutError('expected records did not become search-visible within 30 seconds')
        time.sleep(.25)
    cases = [('anonymous authenticated search', request_path('authenticated', query), None, 401),
             ('missing search scope', request_path('authenticated', query), tokens['NOSEARCH'], 403),
             ('cross dataset', request_path('authenticated', query, dataset='book-private'), tokens['READER'], 403),
             ('cross tenant', request_path('authenticated', query, tenant='other'), tokens['READER'], 403),
             ('public dataset override', request_path('public', query, dataset='book-private'), None, 400),
             ('public tenant override', request_path('public', query, tenant='other'), None, 400),
             ('public oversized query', request_path('public', 'a' * 513), None, 400),
             ('public oversized page', request_path('public', query, limit=51), None, 400),
             ('authenticated oversized page', request_path('authenticated', query, limit=101), tokens['READER'], 400),
             ('malformed limit', request_path('public', query, limit='NaN'), None, 400),
             ('missing query', '/api/v1/search', None, 400)]
    for label, path, token, expected in cases:
        status, _ = request(base, path, token)
        if status != expected: raise ValueError(f'{label}: expected HTTP {expected}, got {status}')
    print(json.dumps({'schema': 'starintel-book-search-service-v1', 'claim_status': 'TESTED',
                      'checks': len(cases), 'public_records': len(public), 'authenticated_records': len(private),
                      'fixture_ids': ids, 'boundary': 'actual HTTP; provisioned runtime and index must match README pins'}))


if __name__ == '__main__':
    main()
