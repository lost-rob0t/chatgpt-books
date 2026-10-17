#!/usr/bin/env bash
# Sourced at the audited upstream stack-test injection point.
: "$BOOK_REPO_ROOT"
: "$STARINTEL_SERVER_PIN"
: "$server_url"
: "$api_key"
: "$artifact_dir"

STARINTEL_URL="$server_url" \
STARINTEL_TOKEN="$api_key" \
STARINTEL_SERVER_PIN="$STARINTEL_SERVER_PIN" \
STARINTEL_BOOK_CANONICAL_OUTPUT="$artifact_dir/book-canonical-live.json" \
    python3 "$BOOK_REPO_ROOT/books/starintel/code/canonical-live/probe.py"
