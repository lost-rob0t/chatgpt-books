import copy
import unittest

from classify_hosted_ci import EvidenceError, classify_jobs

SHA = "6525b54d78b7d7b07972f1768f9cbb4f093fec19"


def job(job_id, name, run_id=39113611465):
    return {"id": job_id, "name": name, "run_id": run_id, "head_sha": SHA,
            "status": "completed", "conclusion": "failure", "runner_id": 0,
            "runner_name": "", "steps": []}


# Compact projection of actual GitHub App observations on 2026-10-18.
BOOK = {"total_count": 4, "jobs": [
    job(117634754459, "service-backed-trace"),
    job(117634754598, "nix"),
    job(117634754695, "records-and-book"),
    job(117634754774, "actor-runtime-upstream"),
]}
ROOT = {"total_count": 1, "jobs": [job(117634749753, "validate", 39113611458)]}


class HostedEvidenceTests(unittest.TestCase):
    def test_real_book_run_fails_before_any_observed_runner_or_step(self):
        result = classify_jobs(BOOK, SHA)
        self.assertEqual(result["classification"], "FAILED_BEFORE_OBSERVED_RUNNER_OR_STEP")
        self.assertEqual((result["jobs"], result["steps"], result["runner_assigned"]), (4, 0, 0))

    def test_real_root_run_has_same_boundary(self):
        self.assertEqual(classify_jobs(ROOT, SHA)["classification"],
                         "FAILED_BEFORE_OBSERVED_RUNNER_OR_STEP")

    def test_executed_failure_is_different_from_pre_runner_failure(self):
        payload = copy.deepcopy(ROOT)
        payload["jobs"][0].update(runner_id=42, runner_name="test-runner",
                                  steps=[{"name": "tests", "conclusion": "failure"}])
        self.assertEqual(classify_jobs(payload, SHA)["classification"],
                         "FAILED_WITH_EXECUTED_STEPS_CAUSE_UNDETERMINED")

    def test_success_with_steps_is_not_independent_test_attestation(self):
        payload = copy.deepcopy(ROOT)
        payload["jobs"][0].update(conclusion="success", runner_id=42,
                                  runner_name="test-runner", steps=[{"name": "checkout"}])
        self.assertEqual(classify_jobs(payload, SHA)["classification"],
                         "SUCCESSFUL_JOBS_WITH_STEPS_NOT_TEST_ATTESTATION")

    def test_partial_pending_run_is_not_declared_failed(self):
        payload = copy.deepcopy(ROOT)
        payload["jobs"][0].update(status="queued", conclusion=None)
        self.assertEqual(classify_jobs(payload, SHA)["classification"], "INCOMPLETE_NOT_VERIFIED")

    def test_head_mismatch_fails_closed(self):
        with self.assertRaisesRegex(EvidenceError, "head_mismatch"):
            classify_jobs(ROOT, "a" * 40)

    def test_partial_pagination_fails_closed(self):
        payload = copy.deepcopy(BOOK)
        payload["jobs"].pop()
        with self.assertRaisesRegex(EvidenceError, "empty_or_partial"):
            classify_jobs(payload, SHA)

    def test_missing_steps_fails_closed(self):
        payload = copy.deepcopy(ROOT)
        del payload["jobs"][0]["steps"]
        with self.assertRaisesRegex(EvidenceError, "missing_step_inventory"):
            classify_jobs(payload, SHA)

    def test_mixed_run_identity_fails_closed(self):
        payload = copy.deepcopy(BOOK)
        payload["jobs"][0]["run_id"] = 39113611458
        with self.assertRaisesRegex(EvidenceError, "mixed_workflow_runs"):
            classify_jobs(payload, SHA)

    def test_duplicate_job_id_fails_closed(self):
        payload = copy.deepcopy(BOOK)
        payload["jobs"][1]["id"] = payload["jobs"][0]["id"]
        with self.assertRaisesRegex(EvidenceError, "duplicate_job_identity"):
            classify_jobs(payload, SHA)

    def test_bare_failure_does_not_implicate_project_code(self):
        payload = copy.deepcopy(ROOT)
        payload["jobs"][0].update(runner_id=None, runner_name=None)
        self.assertEqual(classify_jobs(payload, SHA)["classification"],
                         "UNRESOLVED_EXECUTION_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
