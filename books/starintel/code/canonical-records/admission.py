"""Book-local duplicate-key admission guard; validation stays in the pinned SDK.

This demonstrates a policy at the original JSON-text boundary. It is not a
replacement parser, a complete resource limiter, or a StarIntel service.
"""
import json

from starintel_canonical import Document


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object member: {key!r}")
        result[key] = value
    return result


def read_document(text):
    # Inspect names without coercing number tokens. This pass is discarded;
    # the official SDK parses the original text with exact numeric semantics.
    json.loads(text, object_pairs_hook=unique_object,
               parse_int=str, parse_float=str)
    return Document.from_json(text)
