"""ASCII-only terminal preview for already interpreted search Hit observations.

This is a display boundary only. It cannot authorize a caller, validate a
canonical document, attest an installed index, or establish durable storage.
"""
from __future__ import annotations

import json
from collections.abc import Iterable

MAX_PAGE_HITS = 100
MAX_LABEL_CHARS = 160
MAX_OTHER_CHARS = 240


def _text(value: object, label: str, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or (required and not value):
        raise ValueError(f"{label} must be {'nonempty ' if required else ''}text")
    return value


def _quoted(value: str | None, *, truncate: bool = False) -> str:
    """Produce inert ASCII even for terminal CSI/OSC, newlines, and bidi text."""
    if value is None:
        return 'null'
    limit = MAX_LABEL_CHARS if truncate else MAX_OTHER_CHARS
    shortened = len(value) > limit
    if shortened:
        value = value[:limit]
    return json.dumps(value, ensure_ascii=True) + (' [truncated]' if shortened else '')


def render_hits(hits: Iterable[object]) -> str:
    """Render one interpreted page, never raw unvalidated HTTP/search JSON."""
    lines = [
        'SEARCH PAGE PREVIEW -- UNVERIFIED RESULT OBSERVATIONS',
        'Not a canonical validation, authorization decision, or durable read.',
    ]
    count = 0
    for hit in hits:
        if count >= MAX_PAGE_HITS:
            raise ValueError('page preview exceeds 100 search hits')
        identity = _text(getattr(hit, 'identity', None), 'identity', required=True)
        fields = getattr(hit, 'fields', None)
        if not isinstance(fields, dict):
            raise ValueError('search hit requires stored-field evidence')
        title = _text(fields.get('title'), 'stored title')
        name = _text(fields.get('name'), 'stored name')
        label = name or title
        dtype = _text(getattr(hit, 'dtype', None), 'dtype')
        dataset = _text(getattr(hit, 'dataset', None), 'dataset')
        storage_rev = _text(getattr(hit, 'storage_revision', None), 'storage revision')
        canonical_rev = _text(getattr(hit, 'canonical_revision', None), 'canonical revision')
        lines.extend([
            f'[{count + 1}] identity={_quoted(identity)}',
            f'    label={_quoted(label, truncate=True)}',
            f'    dtype={_quoted(dtype)} dataset={_quoted(dataset)}',
            f'    storage_rev={_quoted(storage_rev)} canonical_rev={_quoted(canonical_rev)}',
        ])
        count += 1
    if not count:
        lines.append('No rows in the supplied page; corpus coverage is unknown.')
    lines.append(f'Observed hits on this page: {count}')
    return '\n'.join(lines) + '\n'
