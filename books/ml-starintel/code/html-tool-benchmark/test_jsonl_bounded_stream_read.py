"""BK08 bounded-input regression: never read a whole mutable JSONL file blindly."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from offline_html_trace_executor import MAX_DATASET_BYTES, TraceFailure, read_jsonl


class JsonlBoundedStreamTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "dataset.jsonl"
        self.path.write_bytes(b'{"id":"ok"}\n')

    def fake_read(self, content: bytes):
        """Instrument the *requested* byte count on an otherwise real Path."""
        lengths = []
        class Reader:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def read(self, count=-1):
                lengths.append(count)
                return content if count < 0 else content[:count]
        with patch.object(Path, "open", return_value=Reader()):
            result = read_jsonl(self.path)
        return result, lengths

    def assert_code(self, code, callback):
        with self.assertRaises(TraceFailure) as raised:
            callback()
        self.assertEqual(raised.exception.code, code)

    def test_01_stream_read_has_explicit_byte_cap(self):
        actual, lengths = self.fake_read(b'{"id":"ok"}\n')
        self.assertEqual(actual, [{"id": "ok"}])
        self.assertEqual(lengths, [MAX_DATASET_BYTES + 1])

    def test_02_two_records_still_parse(self):
        actual, lengths = self.fake_read(b'{"id":"one"}\n{"id":"two"}\n')
        self.assertEqual(actual, [{"id": "one"}, {"id": "two"}])
        self.assertEqual(lengths, [MAX_DATASET_BYTES + 1])

    def test_03_utf8_content_still_parses(self):
        raw = json.dumps({"name": "Zoë 🚀"}, ensure_ascii=False).encode() + b"\n"
        actual, lengths = self.fake_read(raw)
        self.assertEqual(actual, [{"name": "Zoë 🚀"}])
        self.assertEqual(lengths, [MAX_DATASET_BYTES + 1])

    def test_04_stat_to_read_growth_still_fails_typed(self):
        huge = b'{"id":"one"}' + b' ' * MAX_DATASET_BYTES
        # Real file has a valid small stat; fake stream grows after the stat.
        lengths = []
        class Reader:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self, count=-1):
                lengths.append(count)
                return huge if count < 0 else huge[:count]
        with patch.object(Path, "open", return_value=Reader()):
            self.assert_code("invalid_record", lambda: read_jsonl(self.path))
        self.assertEqual(lengths, [MAX_DATASET_BYTES + 1])

    def test_05_reader_does_not_use_path_read_bytes(self):
        with patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded path.read_bytes")):
            self.assertEqual(read_jsonl(self.path), [{"id": "ok"}])

    def test_06_exact_byte_limit_is_valid_jsonl(self):
        # A single padded object stays within the fixed byte budget exactly.
        raw = b'{"id":"ok"}' + b' ' * (MAX_DATASET_BYTES - 11)
        self.path.write_bytes(raw)
        self.assertEqual(self.path.stat().st_size, MAX_DATASET_BYTES)
        self.assertEqual(read_jsonl(self.path), [{"id": "ok"}])

    def test_07_one_byte_over_limit_fails_before_stream_open(self):
        self.path.write_bytes(b' ' * (MAX_DATASET_BYTES + 1))
        with patch.object(Path, "open", side_effect=AssertionError("should not open")):
            self.assert_code("invalid_record", lambda: read_jsonl(self.path))

    def test_08_existing_symlink_rejection_precedes_read(self):
        alias = Path(self.temp.name) / "alias.jsonl"
        alias.symlink_to(self.path)
        with patch.object(Path, "open", side_effect=AssertionError("should not open")):
            self.assert_code("invalid_record", lambda: read_jsonl(alias))

    def test_09_missing_file_is_rejected(self):
        self.path.unlink()
        self.assert_code("invalid_record", lambda: read_jsonl(self.path))

    def test_10_directory_is_rejected(self):
        self.assert_code("invalid_record", lambda: read_jsonl(Path(self.temp.name)))

    def test_11_malformed_json_is_still_typed(self):
        self.path.write_bytes(b'{"id": }\n')
        self.assert_code("invalid_record", lambda: read_jsonl(self.path))

    def test_12_duplicate_keys_are_still_rejected(self):
        self.path.write_bytes(b'{"id":1,"id":2}\n')
        self.assert_code("invalid_record", lambda: read_jsonl(self.path))

    def test_13_crlf_line_framing_preserved(self):
        self.path.write_bytes(b'{"id":"a"}\r\n{"id":"b"}\r\n')
        self.assertEqual(read_jsonl(self.path), [{"id": "a"}, {"id": "b"}])

    def test_14_reader_request_is_never_minus_one(self):
        _, lengths = self.fake_read(b'{"id":"ok"}\n')
        self.assertTrue(lengths)
        self.assertTrue(all(x > 0 for x in lengths))

    def test_15_final_empty_line_remains_ignored(self):
        self.path.write_bytes(b'{"id":"ok"}\n\n')
        self.assertEqual(read_jsonl(self.path), [{"id": "ok"}])

    def test_16_file_byte_budget_is_independent_of_sample_count(self):
        self.path.write_bytes(b'{"x":1}\n' * 8)
        self.assertEqual(len(read_jsonl(self.path)), 8)


if __name__ == "__main__":
    unittest.main()
