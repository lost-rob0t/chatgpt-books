"""BK08: deterministic, offline metamorphic controls for HTML trace execution.

Neutral edits must preserve gold extraction and navigation while changing page bytes.
Collision edits must be reported as selector ambiguity, never guessed as success.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
from html import escape
import json

from offline_html_trace_executor import (
    BoundedParser,
    TraceFailure,
    demo_records,
    run_trace,
    select_one,
)

FAMILY_SPLITS = {
    "tables": "train",
    "cards": "train",
    "pagination": "dev",
    "detail": "test",
    "malformed": "test",
}
DECORATIONS = ("head_comment", "tail_comment", "head_meta", "tail_meta")
VARIANTS = (0, 1, 2)


def neutral_mutation(html: str, decoration: str, nonce: str) -> str:
    """Apply one explicitly structural-neutral HTML decoration."""
    assert decoration in DECORATIONS
    marker = escape(nonce, quote=True)
    if decoration.endswith("comment"):
        fragment = f"<!-- bk08 {marker} -->"
    else:
        fragment = f'<meta data-bk08="{marker}">'
    return fragment + html if decoration.startswith("head") else html + fragment


def derived_records() -> list[dict]:
    """Deterministically build 60 variants and retain their source-family split."""
    cases = []
    for original in demo_records():
        family = original["family"]
        assert family in FAMILY_SPLITS
        path = original["start"]
        for decoration in DECORATIONS:
            for variant in VARIANTS:
                row = copy.deepcopy(original)
                row["id"] = f"{family}_{decoration}_{variant}"
                row["candidate_trace"] = copy.deepcopy(row["gold_trace"])
                row["pages"][path] = neutral_mutation(
                    row["pages"][path], decoration, row["id"]
                )
                row["source_family"] = family
                row["split"] = FAMILY_SPLITS[family]
                cases.append(row)
    return cases


def _collision_fragment(pages: dict[str, str], path: str, selector: str) -> str:
    parser = BoundedParser()
    parser.feed(pages[path])
    parser.close()
    selected = select_one(parser.root, selector)
    attrs = []
    for name in ("id", "class"):
        if name in selected.attrs:
            attrs.append(f' {name}="{escape(selected.attrs[name], quote=True)}"')
    return f"<{selected.tag}{''.join(attrs)}>decoy</{selected.tag}>"


def collision_records() -> list[dict]:
    """Produce one deliberately ambiguous first-selection case per family."""
    result = []
    for original in demo_records():
        row = copy.deepcopy(original)
        row["id"] += "_collision"
        row["candidate_trace"] = copy.deepcopy(row["gold_trace"])
        selector = row["gold_trace"][0]["selector"]
        path = row["start"]
        row["pages"][path] += _collision_fragment(row["pages"], path, selector)
        result.append(row)
    return result


def verify() -> dict:
    """Execute all actual HTML mutations; report only observed outcomes."""
    bases = {row["family"]: row for row in demo_records()}
    counts = {"neutral_pass": 0, "collision_rejected": 0}
    families: dict[str, set[str]] = {}
    digests: set[str] = set()
    for case in derived_records():
        family = case["source_family"]
        families.setdefault(family, set()).add(case["split"])
        original = bases[family]
        baseline = run_trace(original["pages"], original["start"], original["gold_trace"])
        actual = run_trace(case["pages"], case["start"], case["gold_trace"])
        if actual["extractions"] != baseline["extractions"] or actual["visited"] != baseline["visited"]:
            raise AssertionError(f"neutral HTML edit changed gold result: {case['id']}")
        raw = case["pages"][case["start"]].encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        if digest == baseline["page_sha256"][case["start"]] or digest in digests:
            raise AssertionError(f"no unique byte-level perturbation: {case['id']}")
        digests.add(digest)
        counts["neutral_pass"] += 1
    for family, split_set in families.items():
        if split_set != {FAMILY_SPLITS[family]}:
            raise AssertionError(f"source family crosses splits: {family}")
    for case in collision_records():
        try:
            run_trace(case["pages"], case["start"], case["gold_trace"])
        except TraceFailure as exc:
            if exc.code != "selector_ambiguous":
                raise AssertionError(f"collision misclassified: {case['id']}: {exc.code}") from exc
        else:
            raise AssertionError(f"selector collision silently accepted: {case['id']}")
        counts["collision_rejected"] += 1
    return {
        "schema": "bk08.static-html-metamorphic/v1",
        "families": dict(sorted((f, FAMILY_SPLITS[f]) for f in families)),
        "neutral_html_invariants": counts["neutral_pass"],
        "selector_collisions_rejected": counts["collision_rejected"],
        "all_passed": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", required=True)
    parser.parse_args(argv)
    try:
        report = verify()
    except (AssertionError, TraceFailure) as exc:
        print(json.dumps({"all_passed": False, "failure": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
