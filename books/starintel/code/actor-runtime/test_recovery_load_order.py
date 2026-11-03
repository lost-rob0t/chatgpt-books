from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("check_recovery_load_order.py")
SPEC = importlib.util.spec_from_file_location("check_recovery_load_order", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RecoveryLoadOrderTests(unittest.TestCase):
    def make_tree(
        self,
        *,
        asd: str | None = None,
        recovery_start: str | None = None,
        lifecycle_start: str | None = None,
    ) -> Path:
        root = Path(tempfile.mkdtemp())
        source = root / "source"
        source.mkdir()
        (source / "starintel-gserver.asd").write_text(
            asd
            or '(:serial t :components ((:file "target-recovery")\n(:file "runtime-lifecycle")))',
            encoding="utf-8",
        )
        (source / "target-recovery.lisp").write_text(
            recovery_start
            or "(defun start-actors () (recover-persisted-targets))\n",
            encoding="utf-8",
        )
        (source / "runtime-lifecycle.lisp").write_text(
            lifecycle_start or "(defun start-actors () *sys*)\n",
            encoding="utf-8",
        )
        self.addCleanup(lambda: __import__("shutil").rmtree(root))
        return root

    def test_accepts_recorded_boundary(self) -> None:
        result = MODULE.audit(self.make_tree())
        self.assertEqual(
            result,
            {
                "target_recovery_loaded_first": True,
                "early_start_calls_recovery": True,
                "final_start_omits_recovery": True,
            },
        )

    def test_rejects_reversed_load_order(self) -> None:
        root = self.make_tree(
            asd='(:serial t :components ((:file "runtime-lifecycle")\n(:file "target-recovery")))'
        )
        with self.assertRaisesRegex(RuntimeError, "no longer loads after"):
            MODULE.audit(root)

    def test_rejects_when_final_start_gains_recovery(self) -> None:
        root = self.make_tree(
            lifecycle_start="(defun start-actors () (recover-persisted-targets) *sys*)\n"
        )
        with self.assertRaisesRegex(RuntimeError, "now calls recovery"):
            MODULE.audit(root)

    def test_balanced_form_ignores_parentheses_inside_strings(self) -> None:
        text = '(defun start-actors () (format nil "(not structure)") *sys*)\n(other)'
        form = MODULE.extract_list_form(text, "(defun start-actors")
        self.assertEqual(form, '(defun start-actors () (format nil "(not structure)") *sys*)')


if __name__ == "__main__":
    unittest.main()
