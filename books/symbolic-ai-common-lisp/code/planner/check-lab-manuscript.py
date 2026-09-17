#!/usr/bin/env python3
"""Execute the four trusted, checked-in Lisp snippets in the heuristic lab.

This publication test is not a runtime for external text. The first snippet needs
an ACTION/STATE fixture, the second defines the adapter, and the last two construct
operator sets. Fail closed when the chapter's snippet structure changes.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path


def lisp_string(path: Path) -> str:
    return '"' + str(path).replace('\\', '\\\\').replace('"', '\\"') + '"'


def main() -> None:
    here = Path(__file__).resolve().parent
    book = here.parent.parent
    manuscript = book / "manuscript" / "heuristic-laboratory.org"
    blocks = re.findall(
        r"^#\+begin_src lisp\s*\n(.*?)^#\+end_src\s*$",
        manuscript.read_text(encoding="utf-8"),
        flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if len(blocks) != 4:
        raise SystemExit(f"Expected four covered Lisp snippets, found {len(blocks)}")
    implementation = (here / "heuristic-labs.lisp").read_text(encoding="utf-8")
    if blocks[1].strip() not in implementation:
        raise SystemExit("Published relaxed adapter differs from tested implementation")

    systems = (
        book / "code/search/symbolic-ai-search.asd",
        book / "code/pattern-unify/symbolic-ai-pattern.asd",
        here / "symbolic-ai-planner.asd",
    )
    setup = "\n".join(f"(asdf:load-asd {lisp_string(path)})" for path in systems)
    driver = f'''(require :asdf)
{setup}
(asdf:load-system "symbolic-ai-planner/tests")
(in-package #:symbolic-ai.planner.tests)

(let* ((state '((token)))
       (schema (make-action-schema 'left '() '((token)) '((left-done)) '((token))))
       (action (first (instantiate-applicable-actions schema state))))
  (is-equal (canonical-state '((token) (left-done)))
            {blocks[0]}))

;; This is the checked-in manuscript definition, already checked against source.
{blocks[1]}

(let* ((schemas {blocks[2]})
       (initial '((ready)))
       (goals '((left-done) (right-done)))
       (real (solve-plan initial goals schemas :algorithm :uniform-cost))
       (relaxed (solve-lab-relaxation initial goals schemas
                                      '((ready) (left-done) (right-done))))
       (analysis (analyze-hmax-relaxation initial goals schemas)))
  (is (= 5 (symbolic-ai.search:search-result-cost real)))
  (is (= 5 (symbolic-ai.search:search-result-cost relaxed)))
  (is (= 3 (relaxed-analysis-estimate analysis))))

(let* ((schemas {blocks[3]})
       (initial '((token)))
       (goals '((left-done) (right-done)))
       (real (solve-plan initial goals schemas :algorithm :uniform-cost))
       (relaxed (solve-lab-relaxation initial goals schemas
                                      '((token) (left-done) (right-done))))
       (analysis (analyze-hmax-relaxation initial goals schemas)))
  (is (eq :not-found (symbolic-ai.search:search-result-status real)))
  (is (= 2 (symbolic-ai.search:search-result-cost relaxed)))
  (is (= 1 (relaxed-analysis-estimate analysis)))
  (signals invalid-plan-trace (explain-plan-result schemas relaxed)))

(run-tests)
(format t "Heuristic laboratory: all four manuscript Lisp snippets exercised.~%")
'''
    with tempfile.TemporaryDirectory(prefix="heuristic-manuscript-") as directory:
        script = Path(directory) / "snippets.lisp"
        script.write_text(driver, encoding="utf-8")
        subprocess.run(["sbcl", "--script", str(script)], check=True, cwd=book.parents[1])


if __name__ == "__main__":
    main()
