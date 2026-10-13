"""BK08 one-command benchmark: fail closed on bad local corpus acquisition."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import unittest

import html_heldout_baselines as subject
from offline_html_trace_executor import TraceFailure


class CorpusCliFailureTests(unittest.TestCase):
    def invoke(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = subject.main(list(args))
        return status, json.loads(stdout.getvalue()), stderr.getvalue()

    def files(self, directory):
        result = {}
        for split in ("train", "dev", "test"):
            path = Path(directory) / (split + ".jsonl")
            path.write_text('{"example":"local"}\n', encoding="utf-8")
            result[split] = path
        return result

    def invoke_files(self, paths):
        return self.invoke("--train", str(paths["train"]),
                           "--dev", str(paths["dev"]), "--test", str(paths["test"]))

    def assert_typed_input_error(self, paths):
        status, result, stderr = self.invoke_files(paths)
        self.assertEqual(status, 1)
        self.assertEqual(result["passed"], False)
        self.assertEqual(result["failure"], "invalid_record")
        self.assertTrue(result["detail"].startswith("invalid_record:"))
        self.assertNotIn("Traceback", stderr)
        return result

    def test_missing_train_is_typed_json(self):
        with tempfile.TemporaryDirectory() as td:
            paths = self.files(td)
            paths["train"].unlink()
            self.assert_typed_input_error(paths)

    def test_missing_dev_is_typed_json(self):
        with tempfile.TemporaryDirectory() as td:
            paths = self.files(td)
            paths["dev"].unlink()
            self.assert_typed_input_error(paths)

    def test_missing_test_is_typed_json(self):
        with tempfile.TemporaryDirectory() as td:
            paths = self.files(td)
            paths["test"].unlink()
            self.assert_typed_input_error(paths)

    def test_malformed_train_json_is_typed_json(self):
        with tempfile.TemporaryDirectory() as td:
            paths = self.files(td)
            paths["train"].write_text('{"example": }\n', encoding="utf-8")
            self.assert_typed_input_error(paths)

    def test_duplicate_json_keys_are_typed_json(self):
        with tempfile.TemporaryDirectory() as td:
            paths = self.files(td)
            paths["dev"].write_text('{"id": "one", "id": "two"}\n', encoding="utf-8")
            self.assert_typed_input_error(paths)

    def test_invalid_utf8_is_typed_json(self):
        with tempfile.TemporaryDirectory() as td:
            paths = self.files(td)
            paths["test"].write_bytes(b'\xff')
            self.assert_typed_input_error(paths)

    def test_oserror_on_read_is_typed_json_without_path_disclosure(self):
        with tempfile.TemporaryDirectory() as td:
            paths = self.files(td)
            original = subject.read_jsonl
            def blocked(path):
                if path.name == "dev.jsonl":
                    raise PermissionError(13, "SECRET_INTERNAL_PATH")
                return original(path)
            with patch.object(subject, "read_jsonl", side_effect=blocked):
                status, result, stderr = self.invoke_files(paths)
            self.assertEqual(status, 1)
            self.assertEqual(result["failure"], "invalid_record")
            self.assertNotIn("SECRET_INTERNAL_PATH", result["detail"])
            self.assertEqual(stderr, "")

    def test_typed_audit_leakage_remains_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            paths = self.files(td)
            with patch.object(subject, "run_bench", side_effect=TraceFailure("split_leakage", "fixture family collision")):
                status, result, stderr = self.invoke_files(paths)
            self.assertEqual(status, 1)
            self.assertEqual(result["failure"], "split_leakage")
            self.assertIn("family collision", result["detail"])
            self.assertEqual(stderr, "")

    def test_successful_three_partition_report_preserves_output_schema(self):
        with tempfile.TemporaryDirectory() as td:
            paths = self.files(td)
            report = {"schema": "unit.baselines/v1", "samples": 3}
            with patch.object(subject, "run_bench", return_value=report):
                status, result, stderr = self.invoke_files(paths)
            self.assertEqual(status, 0)
            self.assertEqual(result, {"passed": True, "report": report})
            self.assertEqual(stderr, "")

    def test_cli_error_output_repeats_exactly(self):
        with tempfile.TemporaryDirectory() as td:
            paths = self.files(td)
            paths["train"].unlink()
            first = self.assert_typed_input_error(paths)
            second = self.assert_typed_input_error(paths)
            self.assertEqual(first, second)

    def test_argument_usage_validation_is_still_argparse(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                subject.main(["--train", "/tmp/dummy.jsonl"])
        self.assertEqual(raised.exception.code, 2)

    def test_nonfile_directory_is_typed_json(self):
        with tempfile.TemporaryDirectory() as td:
            paths = self.files(td)
            paths["train"] = Path(td)
            self.assert_typed_input_error(paths)


if __name__ == "__main__":
    unittest.main()
