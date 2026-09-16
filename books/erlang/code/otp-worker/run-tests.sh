#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
EBIN="$ROOT/ebin"
rm -rf "$EBIN"
mkdir -p "$EBIN"
erlc -Werror -o "$EBIN" "$ROOT"/src/*.erl "$ROOT"/test/*.erl
erl -noshell -pa "$EBIN" \
  -eval 'case eunit:test(otp_worker_tests, [verbose]) of ok -> halt(0); error -> halt(1) end.'
