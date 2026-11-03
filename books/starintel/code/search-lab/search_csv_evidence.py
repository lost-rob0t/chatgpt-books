"""One-page, text-encoded CSV preview of already interpreted search hits.

Derived display artifact, not a canonical record, authorization check, or
spreadsheet-format security certification. Consumers should keep the JSON
source for lossless recovery and perform application-specific validation.
"""

import csv
from io import StringIO
import json

COLUMNS = ('identity', 'dtype', 'dataset', 'canonical_revision', 'storage_revision')
MAX_ROWS = 100  # Historical authenticated handler's maximum bounded page size.
MAX_CELL_CODEPOINTS = 4096


def text_cell(value):
    """Serialize a scalar as visibly tagged JSON, never as raw spreadsheet text.

    An absent value is a distinct null tag. Literal strings, including those
    that look like formulas, begin with the safe fixed prefix 's:'. JSON
    escaping keeps separators, controls and non-ASCII code points explicit.
    """
    if value is None:
        return 'null'
    if type(value) is not str:
        raise ValueError('CSV preview accepts only string-or-null hit scalars')
    if len(value) > MAX_CELL_CODEPOINTS:
        raise ValueError('CSV preview scalar exceeds its bounded display budget')
    return 's:' + json.dumps(value, ensure_ascii=True)


def export_hit_page(hits):
    """Export only five already-interpreted scalar attributes from one page.

    Search bookmarks, untrusted document bodies, stored fields and scores are
    never consulted. This function cannot decide authorization or retrieval
    completeness. Caller MUST obtain hits from lab.interpret_page() first.
    """
    if type(hits) not in (list, tuple):
        raise ValueError('CSV preview requires a materialized single page')
    if len(hits) > MAX_ROWS:
        raise ValueError('CSV preview exceeds one bounded search page')
    out = StringIO(newline='')
    writer = csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator='\n')
    writer.writerow(COLUMNS)
    for hit in hits:
        try:
            values = (hit.identity, hit.dtype, hit.dataset,
                      hit.canonical_revision, hit.storage_revision)
        except AttributeError as error:
            raise ValueError('CSV preview expects interpreted search hits') from error
        if not isinstance(values[0], str) or not values[0]:
            raise ValueError('CSV preview requires a nonempty identity')
        writer.writerow([text_cell(value) for value in values])
    return out.getvalue()
