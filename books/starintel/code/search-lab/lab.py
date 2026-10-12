"""Search-result interpretation; never a replacement search/authorization engine."""
from dataclasses import dataclass
import json
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
    result = subprocess.run(['node', str(HERE / 'index_projection.js'),
                             str(root / 'source/views/search.json')],
                            input=json.dumps(document, allow_nan=False), text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def request_path(surface: str, query: str, **params) -> str:
    if surface not in ('public', 'authenticated'):
        raise ValueError('unknown search surface')
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


def interpret_page(page: dict) -> tuple[list[Hit], str | None]:
    if not isinstance(page, dict) or not isinstance(page.get('rows'), list):
        raise ValueError('expected a CouchDB search page, not a document/list/error envelope')
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
        revision = (doc or {}).get('_rev', (doc or {}).get('rev'))
        if revision is not None and not isinstance(revision, str):
            raise ValueError('search hit has an invalid revision')
        hits.append(Hit(identity, revision,
                        (doc or fields).get('dtype'), (doc or fields).get('dataset'), doc, fields))
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
