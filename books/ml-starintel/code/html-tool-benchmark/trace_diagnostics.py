"""BK08 offline gold-vs-predicted action-sequence diagnostics (stdlib only).

This is an independently runnable evaluator, not a model/trainer or HTML scraper.
It never reads URLs or executes a predicted tool action.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

TOOLS = frozenset({"select", "extract", "follow_next", "follow_detail"})
MAX_ACTIONS = 32
MAX_CASES = 5000
MAX_LINE_BYTES = 65536
MAX_FILE_BYTES = MAX_CASES * MAX_LINE_BYTES


def _check_action(action: Any) -> dict:
    if not isinstance(action, dict) or set(action) != {"tool", "args"}:
        raise ValueError("action requires exactly tool and args")
    tool, args = action["tool"], action["args"]
    if tool not in TOOLS or not isinstance(args, dict):
        raise ValueError("invalid tool or arguments")
    expected = {"selector", "field"} if tool == "extract" else {"selector"}
    if set(args) != expected:
        raise ValueError("unexpected action argument keys")
    selector = args["selector"]
    if not isinstance(selector, str) or not selector or len(selector) > 256:
        raise ValueError("invalid selector")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in selector):
        raise ValueError("control character in selector")
    if tool == "extract" and args["field"] not in {"title", "score"}:
        raise ValueError("unsupported extraction field")
    return {"tool": tool, "args": dict(sorted(args.items()))}


def _check_trace(actions: Any) -> list[dict]:
    if not isinstance(actions, list) or len(actions) > MAX_ACTIONS:
        raise ValueError("invalid sequence or action budget")
    return [_check_action(a) for a in actions]


def validate_case(case: Any) -> dict:
    if not isinstance(case, dict) or set(case) != {"id", "gold", "predicted"}:
        raise ValueError("case requires exactly id, gold and predicted")
    case_id = case["id"]
    if (not isinstance(case_id, str) or not 1 <= len(case_id) <= 128
            or not all(ch.isascii() and (ch.isalnum() or ch in "-_./") for ch in case_id)):
        raise ValueError("invalid case ID")
    return {"id": case_id, "gold": _check_trace(case["gold"]),
            "predicted": _check_trace(case["predicted"])}


def align(gold: list[dict], predicted: list[dict]) -> list[tuple[str, int | None, int | None]]:
    """Unit-cost minimum edit alignment; deterministic backward tie precedence.

    Exact equality has zero cost. Insert, delete, substitution all cost one.
    Prefer exact matches, then same-tool argument substitutions, then
    deletions, insertions and finally different-tool substitutions on ties.
    """
    n, m = len(gold), len(predicted)
    if n > MAX_ACTIONS or m > MAX_ACTIONS:
        raise ValueError("action budget exceeded")
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i-1][j]+1, d[i][j-1]+1,
                          d[i-1][j-1]+(gold[i-1] != predicted[j-1]))
    i, j = n, m
    reversed_ops: list[tuple[str, int | None, int | None]] = []
    while i or j:
        if i and j and gold[i-1] == predicted[j-1] and d[i][j] == d[i-1][j-1]:
            reversed_ops.append(("match", i-1, j-1))
            i -= 1
            j -= 1
        elif (i and j and gold[i-1]["tool"] == predicted[j-1]["tool"]
              and d[i][j] == d[i-1][j-1] + 1):
            reversed_ops.append(("substitute_args", i-1, j-1))
            i -= 1
            j -= 1
        elif i and d[i][j] == d[i-1][j] + 1:
            reversed_ops.append(("delete", i-1, None))
            i -= 1
        elif j and d[i][j] == d[i][j-1] + 1:
            reversed_ops.append(("insert", None, j-1))
            j -= 1
        elif i and j and d[i][j] == d[i-1][j-1] + 1:
            reversed_ops.append(("substitute_tool", i-1, j-1))
            i -= 1
            j -= 1
        else:
            raise AssertionError("unreachable alignment state")
    reversed_ops.reverse()
    return reversed_ops


def _fault(op: str, gold: dict | None, pred: dict | None) -> str:
    if op == "match":
        return "none"
    if op == "delete":
        return "missing_action"
    if op == "insert":
        return "extra_action"
    if op == "substitute_tool":
        return "wrong_tool"
    assert gold is not None and pred is not None and op == "substitute_args"
    if gold["args"].get("field") != pred["args"].get("field"):
        return "wrong_field"
    if gold["tool"] in {"follow_next", "follow_detail"}:
        return "wrong_navigation_selector"
    return "wrong_selector"


def diagnose(case: dict) -> dict:
    case = validate_case(case)
    gold, predicted = case["gold"], case["predicted"]
    events = []
    for op, gi, pi in align(gold, predicted):
        ga = gold[gi] if gi is not None else None
        pa = predicted[pi] if pi is not None else None
        events.append({"kind": _fault(op, ga, pa), "gold_index": gi,
                       "predicted_index": pi})
    faults = Counter(e["kind"] for e in events if e["kind"] != "none")
    matches = sum(e["kind"] == "none" for e in events)
    aligned_tool = matches + sum(e["kind"] in {"wrong_field", "wrong_selector",
                                                    "wrong_navigation_selector"} for e in events)
    denom = max(len(gold), len(predicted), 1)
    return {"id": case["id"], "gold_actions": len(gold),
            "predicted_actions": len(predicted), "edit_distance": sum(faults.values()),
            "exact_calls": matches, "matching_tool_actions": aligned_tool,
            "exact_call_accuracy": matches / denom,
            "tool_accuracy": aligned_tool / denom,
            "argument_accuracy": matches / max(aligned_tool, 1),
            "sequence_success": int(not faults),
            "first_fault": next((e for e in events if e["kind"] != "none"), None),
            "fault_counts": dict(sorted(faults.items())), "alignment": events}


def evaluate(cases: list[dict]) -> dict:
    if not cases or len(cases) > MAX_CASES:
        raise ValueError("case count must be 1..5000")
    checked = [validate_case(c) for c in cases]
    ids = [c["id"] for c in checked]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate case ID")
    rows = [diagnose(c) for c in sorted(checked, key=lambda c: c["id"])]
    fault_total: Counter = Counter()
    for row in rows:
        fault_total.update(row["fault_counts"])
    denominator = sum(max(r["gold_actions"], r["predicted_actions"], 1) for r in rows)
    tools = sum(r["matching_tool_actions"] for r in rows)
    return {"schema": "bk08-trace-diagnostics-v1", "examples": len(rows),
            "metrics": {"exact_call": sum(r["exact_calls"] for r in rows)/denominator,
                        "tool_accuracy": tools/denominator,
                        "argument_accuracy": sum(r["exact_calls"] for r in rows)/max(tools, 1),
                        "sequence_success": sum(r["sequence_success"] for r in rows)/len(rows)},
            "fault_counts": dict(sorted(fault_total.items())), "rows": rows}


def read_jsonl(path: Path) -> list[dict]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("input must be a regular file, not a symlink")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("input exceeds file budget")
    cases = []
    with path.open("rb") as stream:
        for line in stream:
            if len(line) > MAX_LINE_BYTES:
                raise ValueError("input line exceeds budget")
            if not line.strip():
                continue
            try:
                cases.append(json.loads(line))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("invalid input JSONL") from exc
            if len(cases) > MAX_CASES:
                raise ValueError("case count exceeds budget")
    return cases


def demo_cases() -> list[dict]:
    row = {"tool": "select", "args": {"selector": "article.card"}}
    title = {"tool": "extract", "args": {"selector": ".title", "field": "title"}}
    score = {"tool": "extract", "args": {"selector": ".score", "field": "score"}}
    nav = {"tool": "follow_next", "args": {"selector": "a[rel=next]"}}
    return [
        {"id": "correct", "gold": [row, title, score], "predicted": [row, title, score]},
        {"id": "missing-field", "gold": [row, title, score], "predicted": [row, score]},
        {"id": "inserted-nav", "gold": [row, title, score], "predicted": [row, nav, title, score]},
        {"id": "wrong-selector", "gold": [row, title, score], "predicted": [row, title, {"tool": "extract", "args": {"selector": ".value", "field": "score"}}]},
        {"id": "wrong-tool", "gold": [row, title], "predicted": [nav, title]},
        {"id": "empty-prediction", "gold": [row, title], "predicted": []},
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", type=Path, help="JSONL with id/gold/predicted")
    src.add_argument("--demo", action="store_true", help="six deterministic synthetic controls")
    parser.add_argument("--output", type=Path, help="optional JSON report path")
    args = parser.parse_args(argv)
    try:
        report = evaluate(demo_cases() if args.demo else read_jsonl(args.input))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"diagnostics: {exc}\n")
    rendered = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output is not None:
        if args.output.is_symlink():
            parser.exit(2, "diagnostics: output may not be a symlink\n")
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
