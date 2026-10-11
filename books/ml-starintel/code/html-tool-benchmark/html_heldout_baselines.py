"""BK08: audited, fully offline held-out HTML trace baselines.

Only the training partition supplies labels to the ranker. Both predictors
receive a four-field observation without gold actions or gold extractions.
This is a small deterministic teaching baseline, not a learned web model.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import json
import math
from pathlib import Path
from typing import Any

from html_template_split_audit import SPLITS, audit_and_evaluate
from html_trace_perturbations import FAMILY_SPLITS, derived_records
from offline_html_trace_executor import (
    BoundedParser, CLASS_RE, Element, ID_RE, MAX_ACTIONS, NAME_RE,
    TraceFailure, _valid_record, evaluate, read_jsonl, resolve_page, select_one,
)

ORACLE_FIELDS = ("id", "family", "pages", "start", "gold_trace",
                 "candidate_trace", "gold_extractions", "gold_visited")
ORACLE_FIELD_SET = frozenset(ORACLE_FIELDS)
OBSERVATION_FIELDS = ("id", "family", "pages", "start")
OBSERVATION_FIELD_SET = frozenset(OBSERVATION_FIELDS)
# The original family annotation splits pagination vs detail, although BOTH
# contain the same anchor DOM shape; that annotation leaks across dev/test.
# This evaluation freezes a different *audited* template-component allocation.
BENCHMARK_FAMILY_SPLITS = {"tables": "train", "cards": "train", "pagination": "dev",
                           "detail": "dev", "malformed": "test"}


def projected_partitions() -> dict[str, list[dict[str, Any]]]:
    """Project generator-only split metadata out of the strict oracle schema."""
    result: dict[str, list[dict[str, Any]]] = {part: [] for part in SPLITS}
    for row in derived_records():
        family, split = row.get("source_family"), row.get("split")
        if family not in FAMILY_SPLITS or split != FAMILY_SPLITS[family] or row.get("family") != family:
            raise TraceFailure("invalid_record", "synthetic split metadata does not match family")
        canonical = {key: copy.deepcopy(row[key]) for key in ORACLE_FIELDS}
        _valid_record(canonical)
        result[BENCHMARK_FAMILY_SPLITS[family]].append(canonical)
    for part in SPLITS:
        result[part].sort(key=lambda row: row["id"])
    return result


def observation(row: dict[str, Any]) -> dict[str, Any]:
    """Fail closed rather than accidentally passing a gold column to a predictor."""
    if not isinstance(row, dict) or set(row) != ORACLE_FIELD_SET:
        raise TraceFailure("invalid_record", "canonical training/evaluation record required")
    return {key: copy.deepcopy(row[key]) for key in OBSERVATION_FIELDS}


def _visible_candidates(html: str) -> list[Element]:
    parser = BoundedParser()
    parser.feed(html)
    parser.close()
    return _candidate_nodes(parser.root)


def _candidate_nodes(root: Element) -> list[Element]:
    result: list[Element] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node is not root and node.tag not in {"script", "style"}:
            if not any(isinstance(child, Element) for child in node.children) and node.text():
                result.append(node)
        stack.extend(reversed([child for child in node.children if isinstance(child, Element)]))
    return result


def _features(element: Element) -> set[str]:
    """Small, inspectable DOM features; no input text values or gold outputs."""
    return {
        f"tag:{element.tag}",
        "has_id" if element.attrs.get("id") else "no_id",
        "has_class" if element.attrs.get("class") else "no_class",
        "has_href" if element.attrs.get("href") else "no_href",
        "short_text" if len(element.text()) <= 16 else "long_text",
    }


def _selector(node: Element, html: str) -> str:
    """Prefer uniquely resolvable ID, then class, then tag; never guess ambiguity."""
    options: list[str] = []
    ident = node.attrs.get("id", "")
    if ID_RE.fullmatch(ident):
        options.append("#" + ident)
    for klass in node.attrs.get("class", "").split():
        if CLASS_RE.fullmatch(klass):
            options.append(f"{node.tag}.{klass}")
    options.append(node.tag)
    parser = BoundedParser()
    parser.feed(html)
    parser.close()
    for choice in options:
        try:
            selected = select_one(parser.root, choice)
        except TraceFailure:
            continue
        if selected.tag == node.tag and selected.attrs == node.attrs and selected.text() == node.text():
            return choice
    return "#not_unambiguously_addressable"


def _field(train: list[dict[str, Any]]) -> str:
    counts: Counter[str] = Counter()
    for row in train:
        _valid_record(row)
        for action in row["gold_trace"]:
            if isinstance(action, dict) and action.get("op") == "extract" and isinstance(action.get("field"), str):
                if NAME_RE.fullmatch(action["field"]):
                    counts[action["field"]] += 1
    if not counts:
        raise TraceFailure("invalid_record", "no extraction targets in training split")
    return min(counts, key=lambda name: (-counts[name], name))


class TrainOnlyNodeRanker:
    """Laplace-smoothed log-odds DOM-node ranker fitted only on train gold."""

    def __init__(self, train: list[dict[str, Any]]):
        if not train:
            raise TraceFailure("invalid_record", "training rows required")
        self.field = _field(train)
        positives: Counter[str] = Counter()
        negatives: Counter[str] = Counter()
        pos_total = neg_total = 0
        for row in train:
            _valid_record(row)
            # Training supervision is the last gold selection, on the last
            # visited training page. The gold target is NEVER read at test time.
            selects = [action["selector"] for action in row["gold_trace"]
                       if isinstance(action, dict) and action.get("op") == "select"]
            if not selects or not row["gold_visited"]:
                continue
            html = row["pages"][row["gold_visited"][-1]]
            parser = BoundedParser()
            parser.feed(html)
            parser.close()
            target = select_one(parser.root, selects[-1])
            candidates = _candidate_nodes(parser.root)
            if not any(target is node for node in candidates):
                raise TraceFailure("invalid_record", "train gold target is not a visible leaf")
            for candidate in candidates:
                bucket = positives if candidate is target else negatives
                bucket.update(_features(candidate))
                if candidate is target:
                    pos_total += 1
                else:
                    neg_total += 1
        if not pos_total:
            raise TraceFailure("invalid_record", "no supervised train targets")
        vocabulary = set(positives) | set(negatives)
        self.weights = {
            key: math.log((positives[key] + 1) / (pos_total + 2))
                 - math.log((negatives[key] + 1) / (neg_total + 2))
            for key in sorted(vocabulary)
        }
        self.trained_examples = len(train)
        self.trained_families = sorted({row["family"] for row in train})

    def predict(self, view: dict[str, Any]) -> list[dict[str, str]]:
        return _predict(view, self.field, self.weights, follow_links=False)


def _predict(view: dict[str, Any], field: str, weights: dict[str, float] | None,
             *, follow_links: bool) -> list[dict[str, str]]:
    if not isinstance(view, dict) or set(view) != OBSERVATION_FIELD_SET:
        raise TraceFailure("invalid_record", "predictor accepts only unlabeled four-field observation")
    pages, path = view["pages"], view["start"]
    if not isinstance(pages, dict) or path not in pages:
        raise TraceFailure("invalid_record", "unresolvable observation start page")
    trace: list[dict[str, str]] = []
    for _ in range(min(len(pages), MAX_ACTIONS // 3)):
        html = pages[path]
        nodes = _visible_candidates(html)
        if not nodes:
            return trace + [{"op": "select", "selector": "#no_text_target"}]
        if follow_links:
            anchors = [node for node in nodes if node.tag == "a" and node.attrs.get("href")]
            nonlinks = [node for node in nodes if node.tag != "a"]
            if anchors and not nonlinks:
                anchor = anchors[0]
                selector = _selector(anchor, html)
                href = anchor.attrs["href"]
                try:
                    next_path = resolve_page(href, path)
                except TraceFailure:
                    next_path = ""
                if next_path and next_path in pages and next_path != path:
                    trace.extend([{"op": "select", "selector": selector},
                                  {"op": "follow", "kind": "next" if "next" in anchor.text().lower() else "detail"}])
                    path = next_path
                    continue
        if weights is None:
            # Static baseline: a uniquely identified textual leaf, then class,
            # then first DOM-order leaf. No test label or extracted value used.
            node = min(nodes, key=lambda item: (not bool(item.attrs.get("id")),
                                                not bool(item.attrs.get("class")),
                                                item.tag == "a"))
        else:
            node = max(nodes, key=lambda item: sum(weights.get(f, 0.0) for f in _features(item)))
        trace.extend([{"op": "select", "selector": _selector(node, html)},
                      {"op": "extract", "field": field}])
        return trace
    return trace + [{"op": "select", "selector": "#navigation_budget_exhausted"}]


def run_bench(partitions: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Leakage/gold audit FIRST; predictions receive no held-out labels."""
    evidence = audit_and_evaluate(partitions)
    ranker = TrainOnlyNodeRanker(partitions["train"])
    field = _field(partitions["train"])
    scored: dict[str, Any] = {}
    for method in ("static_heuristic", "train_only_node_ranker"):
        split_reports: dict[str, Any] = {}
        for part in SPLITS:
            derived = []
            for source in partitions[part]:
                row = copy.deepcopy(source)
                view = observation(source)
                row["candidate_trace"] = (_predict(view, field, None, follow_links=True)
                                          if method == "static_heuristic" else ranker.predict(view))
                derived.append(row)
            report = evaluate(derived)
            failures = Counter(case["failure"] or "none" for case in report["cases"])
            split_reports[part] = {"samples": report["samples"], "metrics": report["metrics"],
                                   "failure_counts": dict(sorted(failures.items()))}
        scored[method] = split_reports
    return {
        "schema": "bk08.heldout-node-baselines/v1",
        "audit": {key: evidence[key] for key in ("samples", "templates", "family_count", "template_reuse_count")},
        "ranker_fit": {"train_examples": ranker.trained_examples, "train_families": ranker.trained_families,
                       "feature_count": len(ranker.weights)},
        "baselines": scored,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--demo", action="store_true", help="60 grouped synthetic variants")
    options.add_argument("--train", help="train JSONL path; also requires --dev/--test")
    parser.add_argument("--dev")
    parser.add_argument("--test")
    args = parser.parse_args(argv)
    if args.demo:
        if args.dev or args.test:
            parser.error("--demo cannot combine with split files")
        partitions = projected_partitions()
    else:
        if not args.dev or not args.test:
            parser.error("--train requires --dev and --test")
        partitions = {"train": read_jsonl(Path(args.train)), "dev": read_jsonl(Path(args.dev)),
                      "test": read_jsonl(Path(args.test))}
    try:
        report = run_bench(partitions)
    except TraceFailure as exc:
        print(json.dumps({"passed": False, "failure": exc.code, "detail": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"passed": True, "report": report}, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
