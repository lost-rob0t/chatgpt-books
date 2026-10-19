"""Chapter 15: classify exact-head hosted execution evidence without fake green CI.

Consumes GitHub Actions GET .../actions/runs/{id}/jobs JSON exported
through the authorized GitHub App. No network access or credentials.
"""
import argparse
import json
import re
from pathlib import Path


class EvidenceError(ValueError):
    """Run data is insufficient or conflicts with its claimed identity."""


def classify_jobs(payload, expected_head):
    if not isinstance(expected_head, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", expected_head):
        raise EvidenceError("expected_exact_40_hex_head")
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise EvidenceError("malformed_jobs_payload")
    jobs = payload["jobs"]
    if (not jobs or type(payload.get("total_count")) is not int
            or payload["total_count"] != len(jobs)):
        raise EvidenceError("empty_or_partial_job_listing")
    ids = [job.get("id") for job in jobs if isinstance(job, dict)]
    if len(ids) != len(jobs) or any(type(i) is not int or i <= 0 for i in ids):
        raise EvidenceError("invalid_job_identity")
    if len(set(ids)) != len(ids):
        raise EvidenceError("duplicate_job_identity")
    if any(job.get("head_sha") != expected_head for job in jobs):
        raise EvidenceError("head_mismatch")
    if any(type(job.get("run_id")) is not int or job["run_id"] <= 0 for job in jobs):
        raise EvidenceError("invalid_run_identity")
    if len({job.get("run_id") for job in jobs}) != 1:
        raise EvidenceError("mixed_workflow_runs")
    if any(not isinstance(job.get("steps"), list) for job in jobs):
        raise EvidenceError("missing_step_inventory")
    if any((runner is not None and (type(runner) is not int or runner < 0))
           for runner in (job.get("runner_id") for job in jobs)):
        raise EvidenceError("invalid_runner_identity")
    if any(not isinstance(step, dict) or not isinstance(step.get("name"), str)
           or not step["name"] for job in jobs for step in job["steps"]):
        raise EvidenceError("invalid_step_identity")
    if any(job.get("status") not in {"completed", "queued", "in_progress", "waiting", "pending"}
           for job in jobs):
        raise EvidenceError("invalid_job_status")

    counts = {"jobs": len(jobs), "steps": sum(len(j["steps"]) for j in jobs),
              "runner_assigned": sum(type(j.get("runner_id")) is int
                                     and j["runner_id"] > 0 for j in jobs)}
    if any(job["status"] != "completed" for job in jobs):
        outcome = "INCOMPLETE_NOT_VERIFIED"
    elif all(job.get("conclusion") == "failure" and job.get("runner_id") == 0
             and job.get("runner_name") == "" and not job["steps"] for job in jobs):
        outcome = "FAILED_BEFORE_OBSERVED_RUNNER_OR_STEP"
    elif all(job.get("conclusion") == "success" and type(job.get("runner_id")) is int
             and job["runner_id"] > 0 and job["steps"] for job in jobs):
        outcome = "SUCCESSFUL_JOBS_WITH_STEPS_NOT_TEST_ATTESTATION"
    elif any(job.get("conclusion") == "failure" and job["steps"]
             and type(job.get("runner_id")) is int and job["runner_id"] > 0
             for job in jobs):
        outcome = "FAILED_WITH_EXECUTED_STEPS_CAUSE_UNDETERMINED"
    else:
        outcome = "UNRESOLVED_EXECUTION_EVIDENCE"
    return {"run_id": jobs[0]["run_id"], "head_sha": expected_head,
            "classification": outcome, **counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jobs_json", type=Path)
    parser.add_argument("--expect-head", required=True)
    args = parser.parse_args()
    try:
        summary = classify_jobs(json.loads(args.jobs_json.read_text()), args.expect_head)
    except (OSError, json.JSONDecodeError, EvidenceError) as exc:
        parser.error(str(exc))
    print(json.dumps(summary, sort_keys=True))
    # A successful Actions job is not, by itself, independent test attestation.
    return 0 if summary["classification"].startswith("SUCCESSFUL_JOBS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
