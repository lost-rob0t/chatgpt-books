"""BK08: fail-closed cross-family static-HTML template leakage audit.

Scores use the published offline oracle; this module supplies no model or
training implementation. Structure signatures deliberately discard values,
text, URLs, and HTML comments while retaining DOM shape and attribute names.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from typing import Any

from offline_html_trace_executor import (
    BoundedParser,
    Element,
    MAX_SAMPLES,
    TraceFailure,
    _valid_record,
    demo_records,
    evaluate,
    read_jsonl,
    run_trace,
)

SPLITS = ("train", "dev", "test")


def template_digest(html: str) -> str:
    """Hash a bounded DOM shape, not literal content or fixture URLs."""
    if not isinstance(html, str):
        raise TraceFailure("invalid_record", "template HTML must be text")
    parser = BoundedParser()
    try:
        parser.feed(html)
        parser.close()
    except (RecursionError, OverflowError) as exc:
        raise TraceFailure("parse_bounds", "template HTML exceeds parser capabilities") from exc
    tokens: list[list[Any]] = []
    pending: list[tuple[Element | str, bool]] = [(parser.root, False)]
    while pending:
        node, closing = pending.pop()
        if isinstance(node, str):
            # HTMLParser emits separate data callbacks around comments and
            # character references. Those fragments form one text-bearing DOM
            # slot until an actual element boundary intervenes. Without this
            # normalization, a comment inserted inside a word evades the
            # cross-family template-leakage check.
            if node.strip() and (not tokens or tokens[-1] != ["text"]):
                tokens.append(["text"])
        elif closing:
            tokens.append(["end"])
        else:
            tokens.append(["open", node.tag, sorted(node.attrs)])
            pending.append((node, True))
            pending.extend((child, False) for child in reversed(node.children))
    payload = json.dumps(tokens, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def audit_and_evaluate(partitions: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Reject family/template overlap before computing any split metrics."""
    if not isinstance(partitions, dict) or set(partitions) != set(SPLITS):
        raise TraceFailure("invalid_record", "expected train, dev, test partitions")
    if any(not isinstance(partitions[name], list) or not partitions[name] for name in SPLITS):
        raise TraceFailure("invalid_record", "every split requires nonempty examples")
    if sum(len(partitions[name]) for name in SPLITS) > MAX_SAMPLES:
        raise TraceFailure("invalid_record", "combined split sample budget exceeded")

    ids: set[str] = set()
    owners: dict[tuple[str, str], tuple[str, str]] = {}
    template_examples: dict[str, set[str]] = defaultdict(set)
    for split in SPLITS:
        for record in sorted(partitions[split], key=lambda row: row.get("id", "") if isinstance(row, dict) and isinstance(row.get("id"), str) else ""):
            id_, family, pages, start, gold, _, gold_extractions, gold_visited = _valid_record(record)
            if id_ in ids:
                raise TraceFailure("split_leakage", f"duplicate example identity: {id_}")
            ids.add(id_)
            authoritative = run_trace(pages, start, gold)
            if authoritative["extractions"] != gold_extractions or authoritative["visited"] != gold_visited:
                raise TraceFailure("gold_mismatch", f"example {id_}: gold disagrees with HTML")
            evidence: list[tuple[str, str]] = [("family", family)]
            for html in pages.values():
                digest = template_digest(html)
                evidence.append(("template", digest))
                template_examples[digest].add(id_)
            for kind, value in evidence:
                key = (kind, value)
                if key in owners and owners[key][0] != split:
                    previous_split, previous_id = owners[key]
                    raise TraceFailure("split_leakage", f"{kind} crosses {previous_split}/{split}: {previous_id}/{id_}")
                owners.setdefault(key, (split, id_))

    per_split = {}
    for split in SPLITS:
        measured = evaluate(partitions[split])
        per_split[split] = {"samples": measured["samples"], "metrics": measured["metrics"]}
    evidence = {
        "schema": "bk08.template-held-out/v2",
        "samples": len(ids),
        "templates": len(template_examples),
        "family_count": len({value for kind, value in owners if kind == "family"}),
        "template_reuse_count": sum(len(group) > 1 for group in template_examples.values()),
        "splits": per_split,
        "template_digests": sorted(template_examples),
    }
    return evidence


def demo_partitions() -> dict[str, list[dict[str, Any]]]:
    """Five public synthetic controls; navigation templates stay together."""
    examples = {row["family"]: row for row in demo_records()}
    return {
        "train": [examples["tables"], examples["pagination"], examples["detail"]],
        "dev": [examples["cards"]],
        "test": [examples["malformed"]],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true", help="audit and score five synthetic controls")
    group.add_argument("--train", help="train JSONL path; --dev and --test also required")
    parser.add_argument("--dev")
    parser.add_argument("--test")
    args = parser.parse_args(argv)
    if args.demo:
        if args.dev or args.test:
            parser.error("--demo cannot combine with split paths")
        partitions = demo_partitions()
    else:
        if not args.dev or not args.test:
            parser.error("--train requires --dev and --test")
        from pathlib import Path
        partitions = {"train": read_jsonl(Path(args.train)), "dev": read_jsonl(Path(args.dev)),
                      "test": read_jsonl(Path(args.test))}
    try:
        output = audit_and_evaluate(partitions)
    except TraceFailure as exc:
        print(json.dumps({"passed": False, "failure": exc.code, "detail": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"passed": True, "audit": output}, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
