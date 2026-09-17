#!/usr/bin/env python3

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from inject_upstream_test import inject


class InjectorTests(unittest.TestCase):
    def make_fixture(self, root: Path, *, valid: bool = True) -> tuple[Path, Path]:
        server = root / "server"
        book = root / "book"
        (server / "t").mkdir(parents=True)
        book.mkdir()
        (book / "book-actor.lisp").write_text("ACTOR\n", encoding="utf-8")
        (book / "book-actor-test.lisp").write_text("TEST\n", encoding="utf-8")
        asd_marker = '     (:file "run-tests"))))' if valid else "NO ASD MARKER"
        runner_marker = "    observability-tests))" if valid else "NO RUNNER MARKER"
        (server / "starintel-gserver-tests.asd").write_text(
            f"prefix\n{asd_marker}\n", encoding="utf-8"
        )
        (server / "t" / "run-tests.lisp").write_text(
            f"prefix\n{runner_marker}\n", encoding="utf-8"
        )
        return server, book

    def test_injects_actor_test_and_required_suite_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server, book = self.make_fixture(Path(tmp))
            inject(server, book)
            asd = (server / "starintel-gserver-tests.asd").read_text(encoding="utf-8")
            runner = (server / "t" / "run-tests.lisp").read_text(encoding="utf-8")
            self.assertEqual(asd.count('(:file "book-actor")'), 1)
            self.assertEqual(asd.count('(:file "book-actor-test")'), 1)
            self.assertEqual(runner.count("book-actor-tests"), 1)
            self.assertEqual((server / "t" / "book-actor.lisp").read_text(), "ACTOR\n")
            self.assertEqual((server / "t" / "book-actor-test.lisp").read_text(), "TEST\n")

    def test_fails_closed_when_upstream_marker_drifts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server, book = self.make_fixture(Path(tmp), valid=False)
            with self.assertRaisesRegex(RuntimeError, "injection marker"):
                inject(server, book)


if __name__ == "__main__":
    unittest.main()
