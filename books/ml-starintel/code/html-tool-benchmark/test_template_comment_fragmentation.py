"""BK08 adversarial DOM-template provenance: comments may split text callbacks."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from html_template_split_audit import (
    audit_and_evaluate,
    demo_partitions,
    template_digest,
)
from offline_html_trace_executor import TraceFailure


class TemplateCommentFragmentationTests(unittest.TestCase):
    def vulnerable_clone(self) -> dict[str, list[dict]]:
        partitions = copy.deepcopy(demo_partitions())
        donor = partitions["dev"][0]
        clone = partitions["test"][0]
        clone["pages"] = {
            key: html.replace("Grace", "Gr<!-- harmless annotation -->ace")
            for key, html in donor["pages"].items()
        }
        clone["start"] = donor["start"]
        clone["gold_trace"] = copy.deepcopy(donor["gold_trace"])
        clone["candidate_trace"] = copy.deepcopy(donor["candidate_trace"])
        clone["gold_extractions"] = copy.deepcopy(donor["gold_extractions"])
        clone["gold_visited"] = copy.deepcopy(donor["gold_visited"])
        self.assertNotEqual(clone["id"], donor["id"])
        self.assertNotEqual(clone["family"], donor["family"])
        return partitions

    def test_intra_text_comment_does_not_erase_template_match(self):
        self.assertEqual(template_digest("<section><span>Grace</span></section>"),
                         template_digest("<section><span>Gr<!-- nonce -->ace</span></section>"))

    def test_repeated_comments_do_not_change_text_presence(self):
        self.assertEqual(template_digest("<p>One two three</p>"),
                         template_digest("<p>One<!-- x --><!-- y --> two<!-- z --> three</p>"))

    def test_nested_fragmented_text_preserves_shape(self):
        self.assertEqual(template_digest("<p>A<em>middle</em>B</p>"),
                         template_digest("<p>A<!--x--><em>mi<!--y-->ddle</em>B<!--z--></p>"))

    def test_text_entity_decoding_stays_shape_equivalent(self):
        self.assertEqual(template_digest("<p>Some &amp; text</p>"),
                         template_digest("<p>So<!-- comment -->me &#38; text</p>"))

    def test_comment_only_body_does_not_invent_text(self):
        self.assertEqual(template_digest("<p><!--hi--></p>"), template_digest("<p></p>"))

    def test_empty_text_and_present_text_still_differ(self):
        self.assertNotEqual(template_digest("<p></p>"), template_digest("<p>real</p>"))

    def test_mixed_child_tag_boundaries_do_not_collapse(self):
        self.assertNotEqual(template_digest("<p>first<em>middle</em>last</p>"),
                            template_digest("<p>first middle last</p>"))

    def test_structural_element_difference_still_detected(self):
        self.assertNotEqual(template_digest("<p>G<!--x-->race</p>"),
                            template_digest("<p>G<strong>r</strong>ace</p>"))

    def test_intra_text_comment_clone_across_split_is_rejected(self):
        with self.assertRaises(TraceFailure) as raised:
            audit_and_evaluate(self.vulnerable_clone())
        self.assertEqual(raised.exception.code, "split_leakage")

    def test_clean_demo_remains_valid(self):
        self.assertEqual(audit_and_evaluate(demo_partitions())["samples"], 5)

    def test_permutation_preserves_result(self):
        rows = self.vulnerable_clone()
        with self.assertRaises(TraceFailure) as first:
            audit_and_evaluate(rows)
        for records in rows.values():
            records.reverse()
        with self.assertRaises(TraceFailure) as second:
            audit_and_evaluate(rows)
        self.assertEqual(first.exception.code, second.exception.code)

    def test_cli_rejects_hidden_clone_without_scoring(self):
        rows = self.vulnerable_clone()
        with tempfile.TemporaryDirectory() as directory:
            command = [sys.executable, str(Path(__file__).with_name("html_template_split_audit.py"))]
            for split in ("train", "dev", "test"):
                path = Path(directory) / f"{split}.jsonl"
                path.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows[split]) + "\n", encoding="utf-8")
                command.extend([f"--{split}", str(path)])
            finished = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(finished.returncode, 1, finished.stderr)
            message = json.loads(finished.stdout)
            self.assertEqual(message["failure"], "split_leakage")
            self.assertIs(message["passed"], False)


if __name__ == "__main__":
    unittest.main()
