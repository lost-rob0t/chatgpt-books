"""BK08: the private ML-StarIntel PR workflow must exercise the offline benchmark.

This contract uses only the Python standard library and does not replace the
actual benchmark tests or claim that a GitHub Actions run has executed.
"""
from __future__ import annotations

from pathlib import Path
import unittest


WORKFLOW = Path(__file__).resolve().parents[4] / ".github/workflows/ml-starintel-research.yml"
STEP_NAME = "Run offline BK08 HTML tool benchmark regression suite"
BENCH_PATH = "books/ml-starintel/code/html-tool-benchmark"


class TestBK08WorkflowContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def _bk08_step(self) -> str:
        marker = "      - name: " + STEP_NAME + "\n"
        self.assertEqual(self.workflow.count(marker), 1)
        return self.workflow.split(marker, 1)[1].split("\n      - name:", 1)[0]

    def test_01_book_pr_trigger_remains_scoped(self) -> None:
        self.assertIn("  pull_request:\n    paths:\n      - 'books/ml-starintel/**'", self.workflow)
        self.assertIn("  workflow_dispatch:", self.workflow)

    def test_02_real_native_unittest_discovery(self) -> None:
        step = self._bk08_step()
        self.assertIn('"$RESEARCH_PYTHON" -m unittest discover -v -s . -p \'test_*.py\'', step)

    def test_03_benchmark_working_directory(self) -> None:
        step = self._bk08_step()
        self.assertIn("working-directory: " + BENCH_PATH, step)

    def test_04_four_offline_entrypoints_are_executed(self) -> None:
        step = self._bk08_step()
        for script, flag in (
            ("offline_html_trace_executor.py", "--demo"),
            ("html_trace_perturbations.py", "--verify"),
            ("html_template_split_audit.py", "--demo"),
            ("html_heldout_baselines.py", "--demo"),
        ):
            with self.subTest(script=script):
                self.assertIn(f'"$RESEARCH_PYTHON" {script} {flag}', step)

    def test_05_guarded_fail_fast_shell(self) -> None:
        step = self._bk08_step()
        self.assertIn("shell: bash", step)
        self.assertIn("set -euo pipefail", step)
        self.assertNotIn("|| true", step)
        self.assertNotIn("continue-on-error", step)

    def test_06_bk08_precedes_epub_build(self) -> None:
        self.assertLess(self.workflow.index(STEP_NAME),
                        self.workflow.index("Build and validate ML-StarIntel book"))


if __name__ == "__main__":
    unittest.main()
