#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
EBIN="$ROOT/ebin"
rm -rf "$EBIN"
mkdir -p "$EBIN"
erlc -Werror -o "$EBIN" "$ROOT"/src/*.erl "$ROOT"/test/*.erl
NODE="erlang_book_dist_origin_$$"
erl -noshell -sname "$NODE" -setcookie erlang_book_test_cookie \
  -kernel connect_all false \
  -pa "$EBIN" \
  -eval 'case eunit:test(distributed_service_tests, [verbose]) of ok -> halt(0); error -> halt(1) end.'
