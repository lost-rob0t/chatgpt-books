#!/usr/bin/env python3
"""Inject the book actor test into one exact disposable StarIntel checkout.

The injector deliberately patches only two exact markers.  Any upstream layout
change fails closed so the book cannot silently claim it tested a different
runtime/test boundary.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ASD_MARKER = '     (:file "run-tests"))))'
ASD_REPLACEMENT = (
    '     (:file "book-actor")\n'
    '     (:file "book-actor-test")\n'
    '     (:file "run-tests"))))'
)
RUNNER_MARKER = '    observability-tests))'
RUNNER_REPLACEMENT = '    observability-tests\n    book-actor-tests))'


def replace_once(path: Path, marker: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(marker)
    if count != 1:
        raise RuntimeError(
            f"expected exactly one injection marker in {path}, found {count}: {marker!r}"
        )
    path.write_text(text.replace(marker, replacement, 1), encoding="utf-8")


def inject(server_root: Path, book_root: Path) -> None:
    tests_dir = server_root / "t"
    asd = server_root / "starintel-gserver-tests.asd"
    runner = tests_dir / "run-tests.lisp"
    for required in (tests_dir, asd, runner):
        if not required.exists():
            raise RuntimeError(f"missing expected upstream path: {required}")

    shutil.copyfile(book_root / "book-actor.lisp", tests_dir / "book-actor.lisp")
    shutil.copyfile(
        book_root / "book-actor-test.lisp", tests_dir / "book-actor-test.lisp"
    )
    replace_once(asd, ASD_MARKER, ASD_REPLACEMENT)
    replace_once(runner, RUNNER_MARKER, RUNNER_REPLACEMENT)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("server_root", type=Path)
    parser.add_argument(
        "--book-root",
        type=Path,
        default=Path(__file__).resolve().parent,
    )
    args = parser.parse_args()
    inject(args.server_root.resolve(), args.book_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
