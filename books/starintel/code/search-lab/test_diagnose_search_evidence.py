"""Offline diagnosis never upgrades search observations into durable facts."""

import json
import subprocess
import sys
from pathlib import Path
import unittest

from diagnose_search_evidence import CHECKS, InvalidEvidence, diagnose

TOOL = Path(__file__).with_name("diagnose_search_evidence.py")


def payload(**checks):
    return {"generation": "historical", "surface": "public", "checks": checks}


class DiagnosisTests(unittest.TestCase):
    def test_absent_hit_without_read_does_not_mean_missing_record(self):
        result = diagnose(payload(target_search_hit=False, write_accepted=True))
        self.assertEqual(result["next_check"], "authorized_by_id_read")
        self.assertNotIn("durable_by_id", result["established_observations"])

    def test_by_id_then_unknown_projection(self):
        self.assertEqual(diagnose(payload(durable_by_id=True, target_search_hit=False))["next_check"],
                         "execute_pinned_index_projection")

    def test_missing_index_field_is_distinct_from_missing_database_record(self):
        got = diagnose(payload(durable_by_id=True, field_emitted=False,
                               target_search_hit=False))
        self.assertEqual(got["next_check"], "choose_supported_search_field")
        self.assertIn("Durable", diagnose(payload(durable_by_id=True))["finding"])

    def test_source_projection_does_not_prove_installed_design(self):
        self.assertEqual(diagnose(payload(durable_by_id=True, field_emitted=True,
                                          target_search_hit=False))["next_check"],
                         "compare_exported_fts_design")

    def test_installed_design_does_not_prove_positive_control(self):
        self.assertEqual(diagnose(payload(durable_by_id=True, field_emitted=True,
                                          installed_design_matched=True,
                                          positive_control_visible=False,
                                          target_search_hit=False))["next_check"],
                         "run_allowed_positive_control")

    def test_exhausted_offline_evidence_cannot_claim_index_lag(self):
        checks = dict.fromkeys(CHECKS, True)
        checks["target_search_hit"] = False
        result = diagnose(payload(**checks))
        self.assertEqual(result["next_check"], "investigate_live_index_query_and_scope")
        self.assertNotIn("lag", result["finding"].lower())

    def test_positive_hit_does_not_prove_readback(self):
        self.assertEqual(diagnose(payload(target_search_hit=True))["next_check"],
                         "authorized_by_id_read")

    def test_positive_hit_and_readback_do_not_prove_canonical_validation(self):
        result = diagnose(payload(target_search_hit=True, durable_by_id=True))
        self.assertEqual(result["next_check"], "validate_document_and_provenance")
        self.assertIn("canonical validity remains unproven", result["finding"])

    def test_different_generations_get_distinct_exact_pins(self):
        old = diagnose(payload())
        merged = diagnose({**payload(), "generation": "merged", "surface": "authenticated"})
        self.assertNotEqual(old["server_pin"], merged["server_pin"])
        self.assertEqual(merged["surface"], "authenticated")

    def test_unknown_not_collapsed_into_false(self):
        result = diagnose(payload(durable_by_id=None, target_search_hit=False))
        self.assertEqual(result["next_check"], "authorized_by_id_read")
        self.assertEqual(result["established_observations"], [])

    def test_reject_forged_boolean_and_unknown_dimension(self):
        for invalid in [payload(durable_by_id=1), payload(target_search_hit="true"),
                        payload(some_new_claim=True), [], {"surface": "public"}]:
            with self.subTest(invalid=invalid), self.assertRaises(InvalidEvidence):
                diagnose(invalid)

    def test_cli_diagnoses_input_from_stdin(self):
        result = subprocess.run([sys.executable, str(TOOL), "-"],
                                input=json.dumps(payload(target_search_hit=False)),
                                text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout)["next_check"], "authorized_by_id_read")

    def test_cli_rejects_invalid_evidence_with_nonzero_exit(self):
        result = subprocess.run([sys.executable, str(TOOL), "-"],
                                input='{"surface":"public","checks":{}}',
                                text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
