"""Offline exact-set evaluation for the Chapter 15 synthetic search cohort.

This module NEVER issues HTTP requests, authenticates callers, validates
canonical records or proves installed indexing. Only explicitly supplied
synthetic identities are admitted; expectations come from the experiment plan.
"""
from __future__ import annotations

import json
import sys

SURFACES = ('public', 'authenticated')
PREFIX = 'starintel:person:bookneedle'
MAX_COHORT = 20


def _ids(value: object, label: str) -> set[str]:
    if not isinstance(value, list):
        raise ValueError(f'{label} must be a JSON array')
    if len(value) > MAX_COHORT:
        raise ValueError(f'{label} exceeds the bounded synthetic cohort')
    if any(not isinstance(item, str) or not item.startswith(PREFIX)
           or len(item) > 160 for item in value):
        raise ValueError(f'{label} must contain only synthetic bookneedle identities')
    if len(value) != len(set(value)):
        raise ValueError(f'{label} contains duplicate identities')
    return set(value)


def evaluate(plan: object) -> dict:
    """Compare observed identity sets only against an explicit bounded oracle."""
    if not isinstance(plan, dict) or set(plan) != {'universe', 'expected', 'observed'}:
        raise ValueError('need exactly universe, expected and observed')
    universe = _ids(plan['universe'], 'universe')
    if not universe:
        raise ValueError('synthetic cohort must not be empty')
    expected, observed = plan['expected'], plan['observed']
    if not isinstance(expected, dict) or set(expected) != set(SURFACES):
        raise ValueError('declare expected identities for both surfaces')
    if not isinstance(observed, dict) or set(observed) != set(SURFACES):
        raise ValueError('declare observed identities for both surfaces')
    report = {'claim_status': 'OFFLINE_EXPERIMENT_ONLY',
              'universe_count': len(universe), 'surfaces': {}}
    for surface in SURFACES:
        allowed = _ids(expected[surface], f'expected.{surface}')
        found = _ids(observed[surface], f'observed.{surface}')
        if not allowed <= universe or not found <= universe:
            raise ValueError(f'{surface} contains identities outside the declared cohort')
        tp, fp, fn = allowed & found, found - allowed, allowed - found
        tn = universe - (allowed | found)
        report['surfaces'][surface] = {
            'true_positives': len(tp),
            'false_positives': len(fp),
            'false_negatives': len(fn),
            'true_negatives': len(tn),
            'unexpected': sorted(fp),
            'missing': sorted(fn),
            'precision': len(tp) / len(found) if found else None,
            'recall': len(tp) / len(allowed) if allowed else None,
            'matches_expected': not fp and not fn,
        }
    report['all_expected_matches'] = all(
        item['matches_expected'] for item in report['surfaces'].values())
    return report


def main() -> int:
    try:
        result = evaluate(json.load(sys.stdin))
    except (ValueError, json.JSONDecodeError) as error:
        print(f'input rejected: {error}', file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0 if result['all_expected_matches'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
