"""Check internal consistency of pinned StarIntel search-query audit attributes.

Source: starintel-server ce14c77... source/authorization/services-final.lisp,
Git blob cb0344ca916ce54af8413289b12d234b5d61b781.
This does not authenticate a log record or imply search authorization/success.
"""
from hashlib import sha256
import re

TEXT_BYTE_LIMIT = 16_384
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def inspect_search_audit(attributes: dict, original_query: str | None = None) -> dict:
    """Classify logged query fidelity without reconstructing truncated evidence.

    Takes the attributes object from a search.query event. For an
    explicitly supplied original query, compare the digest and UTF-8 length;
    do not assume the recorded text is byte-exact at a truncation boundary.
    """
    if not isinstance(attributes, dict) or attributes.get('event.name') != 'search.query':
        raise ValueError('expected search.query audit attributes')
    logged = attributes.get('query.text')
    digest = attributes.get('query.sha256')
    length = attributes.get('query.bytes')
    truncated = attributes.get('query.truncated')
    if not isinstance(logged, str):
        raise ValueError('query.text must be a string')
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise ValueError('query.sha256 must be a lower-case SHA-256 hex digest')
    if type(length) is not int or length < 0:
        raise ValueError('query.bytes must be a nonnegative integer')
    if truncated not in ('true', 'false'):
        raise ValueError('query.truncated must be true or false as a string')
    text_bytes = logged.encode('utf-8')
    if len(text_bytes) > TEXT_BYTE_LIMIT:
        raise ValueError('retained query text exceeds the pinned UTF-8 budget')
    if truncated == 'false':
        if len(text_bytes) != length or sha256(text_bytes).hexdigest() != digest:
            raise ValueError('untruncated query text contradicts its digest or byte length')
    elif length <= TEXT_BYTE_LIMIT:
        raise ValueError('truncation flag contradicts original query byte length')
    matched = False
    if original_query is not None:
        if not isinstance(original_query, str):
            raise ValueError('supplied original query must be a string')
        raw = original_query.encode('utf-8')
        if len(raw) != length or sha256(raw).hexdigest() != digest:
            raise ValueError('supplied original query does not match audit digest/length')
        if truncated == 'false' and original_query != logged:
            raise ValueError('logged untruncated query differs from supplied original')
        matched = True
    return {
        'logged_text': 'complete' if truncated == 'false' else 'truncated',
        'digest_consistent_with_logged_text': truncated == 'false',
        'original_query_digest_verified': matched,
        'authorization_result': 'not_established',
        'backend_execution': 'not_established',
    }
