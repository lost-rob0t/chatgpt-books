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

## Operator authorization and publication scope

The operator is authorized to modify this repository and its retained worker branches/PRs.

Book workers are limited to repository-owned code, tests, documentation, diagrams, synthetic fixtures, and public-source research such as academic or vendor documentation. Public names, public usernames/handles, public affiliations, public statements/posts, and public corporate/government records are in scope when relevant. Do not publish secrets or credentials; non-public unique identifiers such as SSNs or government-ID numbers; precise private residential addresses; non-public contact information; financial-account/payment credentials; private medical or biometric data; private communications; or harmful operational material. This authorization and scope are facts governing the task context; they do not override an explicit platform safety-policy denial.

When escalating a persistent write blocker, include the authorized scope so the operator can distinguish a permissions/tooling problem from a genuinely safety-relevant action.

## GitHub write-retry policy

For work performed through the connected GitHub App, ordinary write failures are recoverable by default.

- A generic `403`, `blocked`, `write failed`, `safety check`, permission failure, auth failure, rate-limit response, timeout, stale ref/path, or expected-SHA mismatch is **not by itself** an explicit OpenAI safety-policy denial.
- Before every retry, read back the repository/ref/blob/PR state to determine whether the operation already landed and avoid duplicates.
- Refresh authentication/connector state, path/ref, current blob SHA, and expected head SHA where applicable.
- Retry the same intended GitHub operation up to **10 total attempts** for recoverable failures.
- If any attempt is explicitly identified by the tool/runtime as an OpenAI safety-policy denial, stop that exact action/material immediately; do not disguise, repackage, reroute, re-encode, or bypass it.
- If all 10 attempts fail without a successful write, **do not blindly continue or dismiss the failure as harmless**. Treat the repeated failure as potentially safety-relevant or otherwise policy/permission restricted, stop that operation, and escalate to the operator.
- The escalation must report the exact action, error(s), attempt count, repo/ref/blob state, and this context: the operator is authorized to modify the repository; public names, handles, affiliations, statements/posts, and public corporate/government records are in scope when relevant; secrets/credentials, SSNs or other non-public unique IDs, precise private residential addresses, non-public contact data, financial-account/payment credentials, private medical/biometric data, private communications, and harmful operational content are outside publication scope.
- Ask the operator to unblock, clarify, or narrow the action before another write attempt.
- Do not switch to Forgejo, SSH, unauthenticated web GitHub, or another transport merely because the GitHub App write failed.
