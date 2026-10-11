"""Pure-Python contract and regression tests for the gated BK10 integration witness."""

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from capstone import (
    CONTRACT, ContractError, candidate_futures, encode_state, evaluate,
    execute_offline_tool, read_manifest, require_component,
    request_offline_tool, run, stable_json, validate_observations,
)

ROOT = Path(__file__).resolve().parent
OBSERVATIONS = json.loads((ROOT / "fixtures" / "observations.json").read_text())


class FrozenFixtureTest(unittest.TestCase):
    def test_frozen_asset_digest(self):
        manifest = read_manifest(ROOT)
        for filename, digest in manifest["assets"].items():
            self.assertEqual(hashlib.sha256((ROOT / "fixtures" / filename).read_bytes()).hexdigest(), digest)

    def test_toy_witness_exact_output(self):
        result = run(ROOT)
        self.assertEqual(result["contract"], CONTRACT)
        self.assertEqual(result["state"]["observed_count"], 4)
        self.assertEqual(result["state"]["delta"], 1)
        self.assertEqual(result["forecast"]["forecast_t"], 3)
        self.assertEqual([x["count"] for x in result["forecast"]["candidates"]], [4, 5, 6])
        self.assertEqual(result["metrics"]["absolute_error"], 1)
        self.assertEqual(result["metrics"]["n_heldout"], 1)
        self.assertTrue(result["metrics"]["candidate_support_contains_truth"])
        self.assertEqual(result["tool_result"]["value"], "scheduled")
        self.assertEqual(result["optional_components_used"], [])

    def test_same_bytes_across_processes(self):
        cmd = [sys.executable, str(ROOT / "run_toy.py")]
        output1 = subprocess.check_output(cmd, cwd=ROOT)
        output2 = subprocess.check_output(cmd, cwd=ROOT)
        self.assertEqual(output1, output2)
        self.assertEqual(output1.decode("utf-8"), stable_json(run(ROOT)))

    def test_single_asset_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            destination = Path(d)
            (destination / "fixtures").mkdir()
            for name in ["manifest.json", "observations.json", "status.html", "truth.json"]:
                (destination / "fixtures" / name).write_bytes((ROOT / "fixtures" / name).read_bytes())
            (destination / "fixtures" / "status.html").write_bytes(b"<span data-field='status'>different</span>")
            with self.assertRaisesRegex(ContractError, "digest mismatch"):
                run(destination)


class SeparationAndSchemaTest(unittest.TestCase):
    def test_no_future_information_in_observation_schema(self):
        mutated = copy.deepcopy(OBSERVATIONS)
        mutated["records"][-1]["next_count"] = 6
        with self.assertRaisesRegex(ContractError, "exactly"):
            validate_observations(mutated)

    def test_truth_cannot_change_forecast(self):
        rows = validate_observations(copy.deepcopy(OBSERVATIONS))
        state = encode_state(rows, observation_digest="a" * 64)
        forecast = candidate_futures(state)
        metric_a = evaluate(forecast, {"version": "bk10.heldout.v0", "t": 3, "count": 6})
        metric_b = evaluate(forecast, {"version": "bk10.heldout.v0", "t": 3, "count": 1})
        self.assertEqual([x["count"] for x in forecast["candidates"]], [4, 5, 6])
        self.assertNotEqual(metric_a["absolute_error"], metric_b["absolute_error"])

    def test_reject_duplicate_ids_and_unordered_timestamps(self):
        dup = copy.deepcopy(OBSERVATIONS)
        dup["records"][1]["document_id"] = dup["records"][0]["document_id"]
        with self.assertRaisesRegex(ContractError, "duplicate"):
            validate_observations(dup)
        disorder = copy.deepcopy(OBSERVATIONS)
        disorder["records"][1]["t"] = disorder["records"][0]["t"]
        with self.assertRaisesRegex(ContractError, "increasing"):
            validate_observations(disorder)

    def test_reject_unsupported_schema_or_non_synthetic_identity(self):
        wrong = copy.deepcopy(OBSERVATIONS)
        wrong["version"] = "upstream-starintel-0.10.1"
        with self.assertRaisesRegex(ContractError, "incompatible"):
            validate_observations(wrong)
        wrong = copy.deepcopy(OBSERVATIONS)
        wrong["records"][0]["document_id"] = "real:person-id"
        with self.assertRaisesRegex(ContractError, "synthetic"):
            validate_observations(wrong)

    def test_reject_bool_count_and_extra_record_fields(self):
        wrong = copy.deepcopy(OBSERVATIONS)
        wrong["records"][0]["count"] = True
        with self.assertRaisesRegex(ContractError, "integer"):
            validate_observations(wrong)
        wrong = copy.deepcopy(OBSERVATIONS)
        wrong["records"][0]["embeddings"] = [1, 2]
        with self.assertRaisesRegex(ContractError, "exactly"):
            validate_observations(wrong)

    def test_probability_weights_and_forecast_identity(self):
        state = encode_state(validate_observations(copy.deepcopy(OBSERVATIONS)), observation_digest="b" * 64)
        forecast = candidate_futures(state)
        self.assertEqual(sum(c["weight_ppm"] for c in forecast["candidates"]), 1_000_000)
        with self.assertRaises(ContractError):
            candidate_futures({**state, "contract": "unrecognized"})

    def test_strict_horizon(self):
        forecast = candidate_futures(encode_state(validate_observations(copy.deepcopy(OBSERVATIONS)), observation_digest="c" * 64))
        with self.assertRaisesRegex(ContractError, "horizon"):
            evaluate(forecast, {"version": "bk10.heldout.v0", "t": 2, "count": 4})


class ToolAndOptionalComponentTest(unittest.TestCase):
    def test_tool_allowlist(self):
        forecast = candidate_futures(encode_state(validate_observations(copy.deepcopy(OBSERVATIONS)), observation_digest="d" * 64))
        call = request_offline_tool(forecast)
        page = (ROOT / "fixtures" / "status.html").read_bytes()
        self.assertEqual(execute_offline_tool(call, page)["value"], "scheduled")
        for mutation in [{"action": "follow"}, {"page_id": "https://example.com"}, {"field": "password"}]:
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ContractError, "unauthorized"):
                execute_offline_tool({**call, **mutation}, page)

    def test_duplicate_html_fields_and_malformed_html_fail_closed(self):
        call = {"contract": CONTRACT, "action": "extract_field", "page_id": "frozen-status-note", "field": "status"}
        pages = [
            b"<span data-field='status'>one</span><span data-field='status'>two</span>",
            b"<span data-field='status'>unterminated",
            b"<span data-field='status'><script>evil</script></span>",
            b"<html></html>",
        ]
        for page in pages:
            with self.subTest(page=page), self.assertRaises(ContractError):
                execute_offline_tool(call, page)

    def test_optional_components_unavailable_fail_closed(self):
        for name in ("bk01-world-model", "bk02-tiny-dynamics", "bk03-llm-training", "bk04-llm-runtime",
                     "bk05-diffusion", "bk06-trajectory-diffusion", "bk07-html-caller", "bk08-html-benchmark",
                     "bk09-llm-log-classifier"):
            with self.subTest(name=name), self.assertRaisesRegex(ContractError, "unavailable"):
                require_component({name: {"state": "issue-open", "commit_sha": None}}, name)
        with self.assertRaisesRegex(ContractError, "unsupported contract"):
            require_component({"x": {"state": "tested", "commit_sha": "a" * 40, "contract": "other"}}, "x")


if __name__ == "__main__":
    unittest.main()
