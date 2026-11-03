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
    if truncated == 'false' and len(text_bytes) > TEXT_BYTE_LIMIT:
        raise ValueError('retained query text exceeds the pinned UTF-8 budget')
    # The pinned Lisp implementation cuts *bytes* then decodes with
    # :errorp nil. Only the final, incomplete UTF-8 codepoint (at most
    # three discarded octets, or one replacement character) can change
    # the retained text's re-encoded length. This is not a full-query check.
    if truncated == 'true' and length <= TEXT_BYTE_LIMIT:
        raise ValueError('truncation flag contradicts original query byte length')
    if truncated == 'true' and not (
        TEXT_BYTE_LIMIT - 3 <= len(text_bytes) <= TEXT_BYTE_LIMIT + 2
    ):
        raise ValueError('truncated retained query text is outside its UTF-8 boundary budget')
    if truncated == 'false':
        if len(text_bytes) != length or sha256(text_bytes).hexdigest() != digest:
            raise ValueError('untruncated query text contradicts its digest or byte length')
    matched = False
    prefix_checked = None
    if original_query is not None:
        if not isinstance(original_query, str):
            raise ValueError('supplied original query must be a string')
        raw = original_query.encode('utf-8')
        if len(raw) != length or sha256(raw).hexdigest() != digest:
            raise ValueError('supplied original query does not match audit digest/length')
        if truncated == 'false':
            if original_query != logged:
                raise ValueError('logged untruncated query differs from supplied original')
        else:
            # A digest of the full original does not attest the *retained*
            # log text. Compare every safely decoded codepoint in the first
            # 16,384 original octets. Lisp may drop/replace only an incomplete
            # terminal UTF-8 character; never guess that terminal character.
            cut = raw[:TEXT_BYTE_LIMIT]
            safe_prefix = cut.decode('utf-8', errors='ignore')
            has_partial_terminal = len(safe_prefix.encode('utf-8')) != len(cut)
            if not logged.startswith(safe_prefix):
                raise ValueError('logged prefix contradicts supplied original query')
            suffix = logged[len(safe_prefix):]
            if (not has_partial_terminal and suffix) or (has_partial_terminal and len(suffix) > 1):
                raise ValueError('logged truncation suffix exceeds the uncertain UTF-8 boundary')
        matched = True
        prefix_checked = True
    return {
        'logged_text': 'complete' if truncated == 'false' else 'truncated',
        'digest_consistent_with_logged_text': truncated == 'false',
        'original_query_digest_verified': matched,
        'retained_prefix_consistent_with_original': prefix_checked,
        'authorization_result': 'not_established',
        'backend_execution': 'not_established',
    }
