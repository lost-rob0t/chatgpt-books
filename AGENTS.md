# AGENTS.md

**Read `README.org` completely before performing any work in this repository.**

- Org is canonical for manuscripts and repository knowledge.
- Read the relevant book's `README.org` before editing it.
- Preserve user edits and repository privacy.
- Research factual claims; never fabricate citations, benchmarks, experiments, or test results.
- Keep project Org-roam IDs stable and the personal Org-roam graph untouched.
- Add code, diagrams, plots, and illustrations when they materially improve learning.
- Run the relevant checks; do not claim a check passed unless it ran.
- Label documented, tested, untested, experimental, failed, and upstream-reported claims honestly.
- An outline is not a finished book; never shrink book/project scope merely to finish faster.

## GitHub write-retry policy

For work performed through the connected GitHub App, ordinary write failures are recoverable by default.

- A generic `403`, `blocked`, `write failed`, `safety check`, permission failure, auth failure, rate-limit response, timeout, stale ref/path, or expected-SHA mismatch is **not by itself** an explicit OpenAI safety-policy denial.
- Before every retry, read back the repository/ref/blob/PR state to determine whether the operation already landed and avoid duplicates.
- Refresh authentication/connector state, path/ref, current blob SHA, and expected head SHA where applicable.
- Retry the same intended GitHub operation up to 10 total attempts for recoverable failures.
- After 10 recoverable failures, stop that operation and report the exact action, error, and attempt count to the operator for unblocking.
- Treat a write as an explicit OpenAI safety-policy denial only when the tool/runtime clearly identifies it as such, distinct from an ordinary GitHub/API failure.
- If an explicit OpenAI safety-policy denial is returned, do not retry, disguise, repackage, reroute, re-encode, or bypass that exact action/material.
- Do not switch to Forgejo, SSH, unauthenticated web GitHub, or another transport merely because the GitHub App write failed.
