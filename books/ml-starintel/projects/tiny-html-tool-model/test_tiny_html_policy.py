"""Deterministic BK07 model tests on local static HTML, never network I/O."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tiny_html_policy import (CompactDOM, TinyPolicy, candidates, evaluate, execute,
                              prepare_rows, read_jsonl, validate_trace)

ROOT = Path(__file__).resolve().parent


def fixture(kind, label, suffix):
    if kind == "extract":
        html = (f'<main><div id="ignored">ignore text</div>'
                f'<span id="record-{suffix}" title="{label}">{label}</span>'
                f'<span id="other">other text</span></main>')
        handle = "n2"
        instruction = f"extract {label} text"
        second = {"tool": "extract", "field": "text"}
        expected = label
    else:
        html = (f'<main><a href="/other">Other</a>'
                f'<a href="/page/{suffix}" aria-label="{label}">{label}</a>'
                f'<span id="irrelevant">Random text</span></main>')
        handle = "n2"
        instruction = f"follow {label} link"
        second = {"tool": "follow"}
        expected = f"/page/{suffix}"
    return {"html": html, "instruction": instruction,
            "gold_calls": [{"tool": "select", "node": handle}, second],
            "expected": expected}


class DomContractTests(unittest.TestCase):
    def test_compact_order_and_nested_text(self):
        dom = CompactDOM('<main><section id="record"><b>Value</b> &amp; more</section></main>')
        self.assertEqual(dom.node("n1").text, "Value & more")
        self.assertEqual(dom.compact()[1]["attrs"]["id"], "record")

    def test_oversized_document_and_depth_rejected(self):
        with self.assertRaises(ValueError):
            CompactDOM("x" * 16_385)
        with self.assertRaises(ValueError):
            CompactDOM("<div>" * 25)

    def test_scripts_are_not_represented_as_actions(self):
        dom = CompactDOM('<main><script>secret payload</script><span>Safe</span></main>')
        self.assertNotIn("secret", json.dumps(dom.compact()).lower())
        self.assertTrue(any(c.tool == "extract" for c in candidates(dom)))

    def test_constrained_calls_reject_invalid_schema_and_destinations(self):
        dom = CompactDOM('<a href="javascript:alert(1)">Bad</a><a href="/next">Next</a>')
        self.assertNotIn("n0", [c.node for c in candidates(dom) if c.tool == "follow"])
        for bad in ([{"tool": "click", "node": "n1"}],
                    [{"tool": "select", "node": "n1"}, {"tool": "follow", "url": "https://x"}],
                    [{"tool": "select", "node": "n5"}, {"tool": "follow"}]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_trace(dom, bad)
        self.assertEqual(execute(dom, [{"tool": "select", "node": "n1"}, {"tool": "follow"}]), "/next")

    def test_expected_mismatch_rejected_before_training(self):
        item = fixture("extract", "Record", 1)
        item["expected"] = "wrong"
        with self.assertRaises(ValueError):
            prepare_rows([item])


class TrainingTests(unittest.TestCase):
    def setUp(self):
        self.rows = [fixture("extract", "Alpha", 1), fixture("extract", "Beta", 2),
                     fixture("follow", "Next", 3), fixture("follow", "Details", 4)]

    def test_seeded_training_and_schema_valid_predictions(self):
        one = TinyPolicy()
        two = TinyPolicy()
        m1 = one.fit(self.rows, epochs=30, seed=91)
        m2 = two.fit(self.rows, epochs=30, seed=91)
        self.assertEqual(m1, m2)
        self.assertEqual(one.weights, two.weights)
        self.assertTrue(any(v > 0 for v in m1))
        self.assertEqual(evaluate(one, self.rows)["exact_call_accuracy"], 1.0)
        self.assertEqual(evaluate(one, self.rows)["extraction_success"], 1.0)
        for item in self.rows:
            dom = CompactDOM(item["html"])
            validate_trace(dom, one.predict(dom, item["instruction"]))

    def test_model_roundtrip_and_invalid_format(self):
        model = TinyPolicy()
        model.fit(self.rows, epochs=30, seed=91)
        restored = TinyPolicy.from_json(model.to_json())
        self.assertEqual(restored.weights, model.weights)
        with self.assertRaises(ValueError):
            TinyPolicy.from_json('{"format":"other","weights":{}}')

    def test_exact_call_and_extraction_metrics_are_distinct(self):
        # The model can select a container whose text matches the child without
        # matching the exact gold tool trace. The two metrics must stay separate.
        row = {"html": '<div><span>Value</span></div>', "instruction": "read Value",
               "gold_calls": [{"tool": "select", "node": "n1"}, {"tool": "extract", "field": "text"}],
               "expected": "Value"}
        report = evaluate(TinyPolicy(), [row])
        self.assertEqual(report["exact_call_accuracy"], 0.0)
        self.assertEqual(report["extraction_success"], 1.0)

    def test_cli_offline_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in self.rows))
            cp = subprocess.run([sys.executable, str(ROOT / "tiny_html_policy.py"),
                                 "--train", str(path), "--evaluate", str(path),
                                 "--epochs", "30", "--seed", "91"],
                                capture_output=True, text=True, timeout=15)
            self.assertEqual(cp.returncode, 0, cp.stderr)
            report = json.loads(cp.stdout)
            self.assertEqual(report["format"], "tiny-html-policy/v1")
            self.assertEqual(report["evaluation"]["exact_call_accuracy"], 1.0)
            self.assertEqual(len(read_jsonl(path)), len(self.rows))


if __name__ == "__main__":
    unittest.main()
