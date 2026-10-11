"""Deterministic native regressions for the BK08 static HTML trace executor."""
import copy
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from offline_html_trace_executor import (
    MAX_ACTIONS,
    MAX_NODES,
    MAX_PAGES,
    MAX_PAGE_BYTES,
    TraceFailure,
    demo_records,
    evaluate,
    main,
    read_jsonl,
    resolve_page,
    run_trace,
)


class StaticHtmlExecutionTests(unittest.TestCase):
    def assert_failure(self, code, fn, *args):
        with self.assertRaises(TraceFailure) as ctx:
            fn(*args)
        self.assertEqual(ctx.exception.code, code)

    def test_all_five_gold_traces_execute_against_html(self):
        for row in demo_records():
            with self.subTest(row=row["id"]):
                out = run_trace(row["pages"], row["start"], row["gold_trace"])
                self.assertEqual(out["extractions"], row["gold_extractions"])
                self.assertEqual(out["visited"], row["gold_visited"])

    def test_demo_metrics_are_measured_not_claimed(self):
        result = evaluate(demo_records())
        self.assertEqual(result["samples"], 5)
        self.assertEqual(result["metrics"]["argument_accuracy"], 0.9)
        self.assertEqual(result["metrics"]["extraction_success"], 0.8)
        self.assertEqual(result["metrics"]["sequence_success"], 0.8)
        failures = {c["id"]: c["failure"] for c in result["cases"] if c["failure"]}
        self.assertEqual(failures, {"cards_01": "selector_zero"})

    def test_argument_accuracy_conditioned_on_same_action_type(self):
        record = copy.deepcopy(demo_records()[0])
        record["candidate_trace"] = [
            {"op":"select", "selector":"#wrong"},
            {"op":"follow", "kind":"next"},
        ]
        metrics = evaluate([record])["cases"][0]
        self.assertEqual(metrics["tool_accuracy"], 0.5)
        self.assertEqual(metrics["argument_accuracy"], 0.0)
        self.assertEqual(metrics["exact_call_accuracy"], 0.0)

    def test_nonnumeric_identity_reports_typed_validation_error(self):
        invalid = copy.deepcopy(demo_records()[0])
        invalid["id"] = 42
        self.assert_failure("invalid_record", evaluate, [invalid, demo_records()[1]])

    def test_order_of_input_records_does_not_change_report(self):
        examples = demo_records()
        self.assertEqual(evaluate(examples), evaluate(list(reversed(examples))))

    def test_determinism_across_50_permutations(self):
        originals = demo_records()
        expected = evaluate(originals)
        rng = random.Random(19)
        for _ in range(50):
            shuffled = originals[:]
            rng.shuffle(shuffled)
            self.assertEqual(evaluate(shuffled), expected)

    def test_sha256_provenance_exact_html_bytes(self):
        case = demo_records()[0]
        result = run_trace(case["pages"], case["start"], case["gold_trace"])
        self.assertEqual(result["page_sha256"][case["start"]], hashlib.sha256(case["pages"][case["start"]].encode()).hexdigest())

    def test_only_selected_element_is_extracted(self):
        pages = {"/x.html": "<p id='a'>A</p><p id='b'>B</p>"}
        actions = [{"op":"select","selector":"p#b"},{"op":"extract","field":"choice"}]
        self.assertEqual(run_trace(pages, "/x.html", actions)["extractions"], {"choice": "B"})

    def test_class_selector_and_whitespace_text(self):
        pages = {"/x.html": "<div class='one match two'> A <strong>B</strong> C  </div>"}
        actions = [{"op":"select","selector":"div.match"},{"op":"extract","field":"value"}]
        self.assertEqual(run_trace(pages, "/x.html", actions)["extractions"], {"value": "A B C"})

    def test_attribute_extraction(self):
        pages = {"/x.html": "<a id='link' href='child.html'>Hello</a>"}
        actions = [{"op":"select","selector":"#link"},{"op":"extract","field":"dest","attribute":"href"}]
        self.assertEqual(run_trace(pages, "/x.html", actions)["extractions"], {"dest": "child.html"})

    def test_script_and_style_text_are_not_extracted(self):
        pages = {"/x.html": "<div id='safe'>A<script>not-data</script><style>noise</style>B</div>"}
        actions = [{"op":"select","selector":"#safe"},{"op":"extract","field":"text"}]
        self.assertEqual(run_trace(pages, "/x.html", actions)["extractions"], {"text": "AB"})

    def test_ambiguous_selector_fails_instead_of_first_match(self):
        pages = {"/x.html": "<div class='same'>A</div><div class='same'>B</div>"}
        self.assert_failure("selector_ambiguous", run_trace, pages,"/x.html",[{"op":"select","selector":".same"}])

    def test_missing_selector_fails(self):
        self.assert_failure("selector_zero", run_trace, {"/x.html":"<div/>"}, "/x.html", [{"op":"select","selector":"#never"}])

    def test_descendant_selector_explicitly_not_supported(self):
        self.assert_failure("invalid_action", run_trace, {"/x.html":"<div><b id='b'>x</b></div>"}, "/x.html", [{"op":"select","selector":"div #b"}])

    def test_cannot_extract_without_select(self):
        self.assert_failure("invalid_action",run_trace,{"/x.html":"<p>ok</p>"},"/x.html",[{"op":"extract","field":"value"}])

    def test_duplicate_output_field_rejected(self):
        actions = [{"op":"select","selector":"#b"},{"op":"extract","field":"x"},{"op":"extract","field":"x"}]
        self.assert_failure("invalid_action",run_trace,{"/x.html":"<p id='b'>ok</p>"},"/x.html",actions)

    def test_follow_requires_selected_anchor(self):
        self.assert_failure("invalid_action",run_trace,{"/x.html":"<p id='b'>ok</p>"},"/x.html",[{"op":"select","selector":"#b"},{"op":"follow","kind":"next"}])

    def test_follow_to_missing_page_fails(self):
        actions = [{"op":"select","selector":"#a"},{"op":"follow","kind":"detail"}]
        self.assert_failure("missing_target",run_trace,{"/x.html":"<a id='a' href='none.html'>x</a>"},"/x.html",actions)

    def test_follow_to_external_origin_rejected(self):
        actions = [{"op":"select","selector":"#a"},{"op":"follow","kind":"detail"}]
        self.assert_failure("unsafe_navigation",run_trace,{"/x.html":"<a id='a' href='https://example.com/private'>x</a>"},"/x.html",actions)

    def test_unsafe_url_forms_fail_closed(self):
        for url in ["../parent.html", "a%2fb.html", "https://other.example/a", "javascript:alert(1)", "a.html?x=1", "a.html#frag", "//evil.example/a", "https://[broken/a", "http://fixture.invalid/x.html", " /x.html"]:
            with self.subTest(url=url):
                self.assert_failure("unsafe_navigation", resolve_page, url, "/start.html")

    def test_void_elements_do_not_swallow_following_text(self):
        pages = {"/x.html":"<p id='p'>before<br>after</p>"}
        result = run_trace(pages,"/x.html",[{"op":"select","selector":"#p"},{"op":"extract","field":"value"}])
        self.assertEqual(result["extractions"],{"value":"beforeafter"})

    def test_node_budget(self):
        pages = {"/x.html":"<i></i>" * (MAX_NODES + 1)}
        self.assert_failure("parse_bounds", run_trace, pages,"/x.html",[])

    def test_depth_budget(self):
        pages = {"/x.html":"<div>" * 45 + "x" + "</div>" * 45}
        self.assert_failure("parse_bounds", run_trace, pages,"/x.html",[])

    def test_page_size_budget(self):
        pages = {"/x.html":"x" * (MAX_PAGE_BYTES + 1)}
        self.assert_failure("parse_bounds", run_trace, pages,"/x.html",[])

    def test_page_inventory_budget(self):
        pages = {f"/{i}.html":"<p>x</p>" for i in range(MAX_PAGES + 1)}
        self.assert_failure("parse_bounds",run_trace,pages,"/0.html",[])

    def test_action_budget(self):
        self.assert_failure("invalid_action",run_trace,{"/x.html":"x"},"/x.html",[{}]*(MAX_ACTIONS+1))

    def test_gold_must_match_the_actual_html(self):
        broken = copy.deepcopy(demo_records())
        broken[0]["gold_extractions"] = {"name": "unseen"}
        self.assert_failure("gold_mismatch", evaluate, broken)

    def test_duplicate_ids_rejected(self):
        rows = demo_records()
        self.assert_failure("invalid_record", evaluate, [rows[0], copy.deepcopy(rows[0])])

    def test_source_mutation_does_not_pass_stale_gold(self):
        rows = demo_records()
        rows[0]["pages"]["/tables/index.html"] = rows[0]["pages"]["/tables/index.html"].replace("Ada", "Different")
        self.assert_failure("gold_mismatch", evaluate, rows)

    def test_jsonl_one_command_dataset(self):
        records = demo_records()
        with tempfile.TemporaryDirectory() as td:
            f = Path(td)/"example.jsonl"
            f.write_text("\n".join(json.dumps(r) for r in records)+"\n")
            self.assertEqual(evaluate(read_jsonl(f)), evaluate(records))
            cmd = [sys.executable,str(Path(__file__).with_name("offline_html_trace_executor.py")),"--evaluate",str(f)]
            process = subprocess.run(cmd,check=True,capture_output=True,text=True)
            self.assertEqual(json.loads(process.stdout), evaluate(records))

    def test_jsonl_bad_utf8_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/"invalid.jsonl"
            f.write_bytes(b"\xff")
            self.assert_failure("invalid_record",read_jsonl,f)

    def test_jsonl_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/"real.jsonl"
            f.write_text("{}\n")
            link=Path(td)/"linked.jsonl"
            link.symlink_to(f)
            self.assert_failure("invalid_record",read_jsonl,link)

    def test_cli_demo_exact_bytes_reproducible(self):
        cmd=[sys.executable,str(Path(__file__).with_name("offline_html_trace_executor.py")),"--demo"]
        one=subprocess.run(cmd,capture_output=True,check=True).stdout
        two=subprocess.run(cmd,capture_output=True,check=True).stdout
        self.assertEqual(one,two)
        self.assertEqual(json.loads(one),evaluate(demo_records()))


if __name__ == "__main__":
    unittest.main()
