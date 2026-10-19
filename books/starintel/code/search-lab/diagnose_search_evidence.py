"""Offline Chapter 15 decision aid; it never executes or authorizes a search.

A diagnosis chooses the next experiment from caller-supplied observations.
It does not infer durable canonical evidence from FTS results or vice versa.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping

SERVER_GENERATIONS = {
    "historical": "ce14c77ccd2f51f543410fdeef3d78fb9978b769",
    "merged": "ca6fdcbdc1f3b8aa344c533a40d298f741a54f25",
}
CHECKS = (
    "write_accepted",
    "durable_by_id",
    "field_emitted",
    "installed_design_matched",
    "positive_control_visible",
    "target_search_hit",
)
SURFACES = frozenset(("public", "authenticated"))


class InvalidEvidence(ValueError):
    """A purported observation is not a supported, explicit observation."""


def diagnose(payload: object) -> dict[str, object]:
    """Return bounded guidance without converting a missing observation to false."""
    if not isinstance(payload, Mapping) or set(payload) != {"generation", "surface", "checks"}:
        raise InvalidEvidence("expected exactly generation, surface and checks")
    generation = payload["generation"]
    surface = payload["surface"]
    checks = payload["checks"]
    if generation not in SERVER_GENERATIONS or surface not in SURFACES:
        raise InvalidEvidence("unsupported source generation or search surface")
    if not isinstance(checks, Mapping) or set(checks) - set(CHECKS):
        raise InvalidEvidence("checks must be a map containing only supported observations")
    if any(value is not None and type(value) is not bool for value in checks.values()):
        raise InvalidEvidence("check values must be true, false or null")
    evidence = {name: checks.get(name) for name in CHECKS}
    established = [name for name in CHECKS if evidence[name] is True]
    # Report the caller's actual input state. An omitted check was never
    # reported; an explicit null is a reported inconclusive observation.
    # These labels do not certify that the caller performed the check.
    observation_states = {
        name: ('not_reported' if name not in checks else
               'reported_inconclusive' if checks[name] is None else
               'reported_true' if checks[name] is True else
               'reported_false')
        for name in CHECKS
    }
    search = evidence["target_search_hit"]
    by_id = evidence["durable_by_id"]

    if search is True:
        if by_id is not True:
            next_check = "authorized_by_id_read"
            finding = "A search hit was observed; durable by-ID read-back is not established."
        else:
            next_check = "validate_document_and_provenance"
            finding = "A hit and by-ID read were observed independently; canonical validity remains unproven."
    elif by_id is not True:
        next_check = "authorized_by_id_read"
        finding = "Missing search visibility cannot establish missing durable storage."
    elif evidence["field_emitted"] is None:
        next_check = "execute_pinned_index_projection"
        finding = "Durable by-ID read is observed; selected index-field coverage is unknown."
    elif evidence["field_emitted"] is False:
        next_check = "choose_supported_search_field"
        finding = "The inspected source projection omitted the sought field."
    elif evidence["installed_design_matched"] is not True:
        next_check = "compare_exported_fts_design"
        finding = "Source projection emits the field, but installed design equivalence is not established."
    elif evidence["positive_control_visible"] is not True:
        next_check = "run_allowed_positive_control"
        finding = "The installed design matches the source; this search context lacks a visible allowed control."
    else:
        next_check = "investigate_live_index_query_and_scope"
        finding = "Checks did not explain the missing hit; live indexing, query and scope remain unproven."

    return {
        "generation": generation,
        "server_pin": SERVER_GENERATIONS[generation],
        "surface": surface,
        "finding": finding,
        "next_check": next_check,
        "established_observations": established,
        "observation_states": observation_states,
        "limits": [
            "Only explicit caller-supplied observations were evaluated.",
            "A positive control does not authorize or validate the target document.",
            "No observation alone proves canonical validation, indexing completeness, or snapshot consistency.",
            "No network, credential, CouchDB, Clouseau, or server call was made.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_json", help="Local JSON evidence file; use '-' for stdin")
    args = parser.parse_args(argv)
    try:
        if args.evidence_json == "-":
            payload = json.load(sys.stdin)
        else:
            with open(args.evidence_json, encoding="utf-8") as handle:
                payload = json.load(handle)
        result = diagnose(payload)
    except (OSError, ValueError, TypeError) as exc:
        print(f"invalid search evidence: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
