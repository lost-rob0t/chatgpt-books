"""Search-result interpretation; never a replacement search/authorization engine."""
from dataclasses import dataclass
from copy import deepcopy
import json
from verify_installed_design import git_blob_sha, HISTORICAL_GIT_BLOB
from pathlib import Path
import subprocess
from urllib.parse import urlencode

HERE = Path(__file__).resolve().parent
SERVER_PIN = 'ce14c77ccd2f51f543410fdeef3d78fb9978b769'
SDK_PIN = '6aa8051dc7ea560943a60a25e1d600467f2778bc'
PUBLIC_PATH = '/api/v1/search'
PRIVATE_PATH = '/api/v1/documents/search'


def require_pin(root: Path, pin: str) -> None:
    actual = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != pin:
        raise ValueError(f'expected {pin}, got {actual}')
    dirty = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=no'], text=True)
    if dirty:
        raise ValueError('tracked upstream source must be clean')


def projection(root: Path, document: dict) -> list[dict]:
    if not isinstance(document, dict):
        raise ValueError('projection needs a JSON document object')
    # Every direct projection call must attest the source, not just run-tests.
    require_pin(root, SERVER_PIN)
    # A clean Git status can hide edits to tracked skip-worktree entries.
    source = root / 'source/views/search.json'
    try:
        source_bytes = source.read_bytes()
    except OSError as error:
        raise ValueError('pinned index design source is unavailable') from error
    if git_blob_sha(source_bytes) != HISTORICAL_GIT_BLOB:
        raise ValueError('pinned index design Git blob mismatch')
    result = subprocess.run(['node', str(HERE / 'index_projection.js'),
                             str(root / 'source/views/search.json')],
                            input=json.dumps(document, allow_nan=False), text=True, capture_output=True, check=True, timeout=30)
    emissions = json.loads(result.stdout)
    if not isinstance(emissions, list):
        raise ValueError('expected a list of captured index emissions')
    for emission in emissions:
        if (not isinstance(emission, dict)
                or not isinstance(emission.get('field'), str)
                or not emission['field']
                or not isinstance(emission.get('options'), dict)
                or emission['options'].get('store') is not True
                or 'value' not in emission
                or emission['value'] is None
                or isinstance(emission['value'], (list, dict))):
            raise ValueError('malformed captured index emission')
    return emissions


def request_path(surface: str, query: str, **params) -> str:
    if surface not in ('public', 'authenticated'):
        raise ValueError('unknown search surface')
    # Public search ignores sort; refuse a parameter that only appears honored.
    if surface == 'public' and 'sort' in params:
        raise ValueError('public search does not forward sort')
    # Encoding is transport handling; validation belongs to the real server.
    route = PUBLIC_PATH if surface == 'public' else PRIVATE_PATH
    return route + '?' + urlencode({'q': query, **params})


@dataclass(frozen=True)
class Hit:
    identity: str
    revision: str | None
    dtype: str | None
    dataset: str | None
    document: dict | None
    fields: dict
    storage_revision: str | None = None
    canonical_revision: str | None = None


def interpret_page(page: dict) -> tuple[list[Hit], str | None]:
    if not isinstance(page, dict) or 'error' in page or not isinstance(page.get('rows'), list):
        raise ValueError('expected a CouchDB search page, not a document/list/error envelope')
    # The pinned public route caps responses at 50 rows, authenticated at 100.
    # Reject a larger result before copying any search-row evidence.
    if len(page['rows']) > 100:
        raise ValueError('search response exceeds pinned page row budget (100)')
    hits = []
    identities = set()
    for row in page['rows']:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id']:
            raise ValueError('search row needs a nonempty identity')
        identity = row['id']
        if identity in identities:
            raise ValueError('duplicate identity within one page')
        identities.add(identity)
        doc, fields = row.get('doc'), row.get('fields', {})
        if not isinstance(fields, dict) or (doc is not None and not isinstance(doc, dict)):
            raise ValueError('invalid document or stored-fields projection')
        if doc is not None and doc.get('_id', doc.get('id')) != identity:
            raise ValueError('row/document identity disagreement')
        if 'tenant_id' in fields or (doc is not None and 'tenant_id' in doc):
            raise ValueError('server tenancy metadata leaked on egress')
        # Stored index metadata and an embedded document are distinct evidence.
        # Do not silently choose one when their scalar scope/type disagrees.
        if doc is not None:
            for key in ('dtype', 'dataset'):
                stored, embedded = fields.get(key), doc.get(key)
                if (isinstance(stored, str) and isinstance(embedded, str)
                        and stored != embedded):
                    raise ValueError(f'{key} stored fields and document disagree')
        # Storage and canonical revisions are different namespaces of evidence.
        # Keep the legacy revision convenience field, but preserve both origins.
        storage_rev = doc.get('_rev') if doc is not None else None
        canonical_rev = doc.get('rev') if doc is not None else None
        if any(value is not None and not isinstance(value, str)
               for value in (storage_rev, canonical_rev)):
            raise ValueError('search hit has an invalid revision')
        revision = storage_rev if storage_rev is not None else canonical_rev
        hits.append(Hit(identity, revision,
                        (doc or fields).get('dtype'), (doc or fields).get('dataset'),
                        deepcopy(doc), deepcopy(fields),
                        storage_rev, canonical_rev))
    bookmark = page.get('bookmark')
    if bookmark is not None and not isinstance(bookmark, str):
        raise ValueError('bookmark must be an opaque string')
    return hits, bookmark


def next_bookmark(previous: str | None, bookmark: str | None, hits: list[Hit]) -> str | None:
    if not hits:
        return None
    if not bookmark or bookmark == previous:
        raise ValueError('nonempty page has missing/repeated bookmark')
    return bookmark
