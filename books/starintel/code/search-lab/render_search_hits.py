"""Render already-authorized search Hit observations as inert HTML.

This does not authenticate callers, authorize rows, validate canonical records,
or establish that any search hit is present in durable storage. Only fields
explicitly provided by the search response are displayed; arbitrary embedded
\`\`doc\`\` contents are not treated as presentation instructions.
"""
from __future__ import annotations

from html import escape
from typing import Iterable


MAX_LABEL_CHARS = 160


def _scalar(value: object, field: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{field} must be text or absent")
    return value


def _literal(value: str) -> str:
    return escape(value, quote=True)


def render_hits(hits: Iterable[object]) -> str:
    """Return a noninteractive HTML fragment for previously authorized hits.

    The caller must first run the pinned search-result interpreter and enforce
    its authorization/pagination boundaries. This display layer never parses
    or trusts raw HTML from result fields and never generates hyperlinks.
    """
    lines = [
        '<section class="search-hits">',
        '<p>Search-page observations only; not canonical validation or durable-read evidence.</p>',
        '<ol>',
    ]
    count = 0
    for hit in hits:
        identity = _scalar(getattr(hit, 'identity', None), 'identity')
        if not identity:
            raise ValueError('search hit needs an identity')
        fields = getattr(hit, 'fields', None)
        if not isinstance(fields, dict):
            raise ValueError('search hit needs stored-field evidence')
        for key in ('name', 'title'):
            _scalar(fields.get(key), f'stored {key}')
        label = fields.get('name') or fields.get('title') or 'Unnamed search hit'
        label_truncated = len(label) > MAX_LABEL_CHARS
        label = label[:MAX_LABEL_CHARS]
        dtype = _scalar(getattr(hit, 'dtype', None), 'dtype')
        dataset = _scalar(getattr(hit, 'dataset', None), 'dataset')
        storage_rev = _scalar(getattr(hit, 'storage_revision', None), 'storage revision')
        canonical_rev = _scalar(getattr(hit, 'canonical_revision', None), 'canonical revision')
        lines.append('<li>')
        lines.append(f'<strong>{_literal(label)}</strong>')
        if label_truncated:
            lines.append('<span class="label-truncation">[display truncated]</span>')
        lines.append(f'<code class="hit-id">{_literal(identity)}</code>')
        for name, value in (('dtype', dtype), ('dataset', dataset),
                            ('storage revision', storage_rev),
                            ('canonical revision', canonical_rev)):
            if value is not None:
                lines.append(f'<span>{_literal(name)}: {_literal(value)}</span>')
        lines.append('</li>')
        count += 1
    lines.extend(['</ol>',
                  '<p>No rows in this supplied page.</p>' if count == 0 else '',
                  '</section>'])
    return '\n'.join(x for x in lines if x)
