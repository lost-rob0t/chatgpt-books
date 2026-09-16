#!/usr/bin/env python3
"""Inject the book probe into a pinned, disposable upstream stack-test copy.

The book does not fork StarIntel's deployment logic.  Instead, CI checks out an
exact upstream revision and inserts one sourced hook immediately before the
upstream stack-test's final success message, while the authenticated disposable
stack is still live.  Any upstream script drift makes this tool fail closed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

# The pinned upstream script intentionally has no newline after this final line.
# Keep the marker byte-faithful: source drift should fail rather than guess.
MARKER = (
    "printf 'Authenticated and authorized Nix-built stack passed scoped denial, "
    "FTS, and restart persistence checks.\\n'"
)
INJECTION = (
    'set_stage "starintel-book-service-trace"\n'
    ': "${STARINTEL_BOOK_PROBE:?STARINTEL_BOOK_PROBE must point to the book probe}"\n'
    'source "$STARINTEL_BOOK_PROBE"\n\n'
)


def inject(stack_test: Path) -> None:
    original = stack_test.read_text(encoding="utf-8")
    count = original.count(MARKER)
    if count != 1:
        raise RuntimeError(
            f"expected exactly one pinned stack-test marker, found {count}; "
            "re-audit the upstream script before changing the injector"
        )
    if INJECTION in original:
        raise RuntimeError("book probe injection is already present")
    stack_test.write_text(original.replace(MARKER, INJECTION + MARKER), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("stack_test", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    inject(args.stack_test)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
